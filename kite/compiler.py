"""Engine 2, part 1: compiles the AST into bytecode for the stack VM."""

from __future__ import annotations

from kite import nodes as n
from kite.bytecode import (
    BINARY_OPS, BUILD_LIST, CALL, CONST, DEFINE_GLOBAL, DEFINE_LOCAL, FALSE,
    INDEX_GET, INDEX_SET, JUMP, JUMP_IF_FALSE, JUMP_IF_FALSE_OR_POP,
    JUMP_IF_TRUE_OR_POP, LOAD_CELL, LOAD_FREE, LOAD_GLOBAL, LOAD_LOCAL,
    MAKE_CELL, MAKE_CLOSURE, NEG, NIL, NOT, POP, RETURN, SET_GLOBAL, STORE_CELL,
    STORE_FREE, STORE_GLOBAL, STORE_LOCAL, TRUE, Code,
)
from kite.resolver import Binding, FunctionInfo, Resolution

LOADS = {"global": LOAD_GLOBAL, "local": LOAD_LOCAL, "cell": LOAD_CELL,
         "free": LOAD_FREE}
STORES = {"global": STORE_GLOBAL, "local": STORE_LOCAL, "cell": STORE_CELL,
          "free": STORE_FREE}


def compile_program(program: n.Program, resolution: Resolution) -> Code:
    info = resolution.functions[program]
    compiler = _FunctionCompiler(resolution, info, Code("<script>", 0, info.nslots))
    for stmt in program.body:
        compiler.stmt(stmt)
    last_line = program.body[-1].line if program.body else 1
    compiler.emit(NIL, 0, last_line)
    compiler.emit(RETURN, 0, last_line)
    return compiler.code


class _FunctionCompiler:
    def __init__(self, res: Resolution, info: FunctionInfo, code: Code) -> None:
        self.res = res
        self.info = info
        self.code = code

    # ---- emitting ----------------------------------------------------------

    def emit(self, op: int, arg: int, line: int) -> int:
        self.code.ops.append((op, arg))
        self.code.lines.append(line)
        return len(self.code.ops) - 1

    def const(self, value: object) -> int:
        # Reuse the slot of an equal constant. The type check keeps 1, 1.0
        # and true apart, since Python thinks they are equal.
        if not isinstance(value, Code):
            for i, c in enumerate(self.code.consts):
                if type(c) is type(value) and c == value:
                    return i
        self.code.consts.append(value)
        return len(self.code.consts) - 1

    def jump(self, op: int, line: int) -> int:
        return self.emit(op, -1, line)  # target patched later

    def patch(self, at: int) -> None:
        op, _ = self.code.ops[at]
        self.code.ops[at] = (op, len(self.code.ops))

    # ---- variables ---------------------------------------------------------

    def access(self, binding: Binding | None) -> tuple[str, int]:
        """Where a variable lives, seen from the function being compiled."""
        if binding is None:
            return "global", -1
        if binding.owner is self.info.state:
            kind = "cell" if binding in self.res.captured else "local"
            return kind, binding.slot
        return "free", self.info.frees.index(binding)

    def load(self, node: n.Variable) -> None:
        kind, arg = self.access(self.res.bindings.get(node))
        if kind == "global":
            arg = self.const(node.name)
        self.emit(LOADS[kind], arg, node.line)

    def define(self, decl: object, name: str, line: int) -> None:
        """Pops the value on top of the stack into a new variable."""
        binding = self.res.bindings.get(decl)
        if binding is None:
            self.emit(DEFINE_GLOBAL, self.const(name), line)
        elif binding in self.res.captured:
            self.emit(MAKE_CELL, binding.slot, line)  # a fresh cell every time
        else:
            self.emit(DEFINE_LOCAL, binding.slot, line)

    # ---- statements --------------------------------------------------------

    def stmt(self, s: object) -> None:
        match s:
            case n.ExprStmt(expr=n.Assign() as e):
                self.assign_stmt(e)
            case n.ExprStmt(expr=e, line=line):
                self.expr(e)
                self.emit(POP, 0, line)
            case n.Let(name=name, value=value, line=line):
                self.expr(value)
                self.define(s, name, line)
            case n.FnDecl():
                self.fn_decl(s)
            case n.Block(body=body):
                for inner in body:
                    self.stmt(inner)
            case n.If(condition=c, then=then, otherwise=otherwise, line=line):
                self.expr(c)
                to_else = self.jump(JUMP_IF_FALSE, line)
                self.stmt(then)
                if otherwise is None:
                    self.patch(to_else)
                else:
                    to_end = self.jump(JUMP, line)
                    self.patch(to_else)
                    self.stmt(otherwise)
                    self.patch(to_end)
            case n.While(condition=c, body=body, line=line):
                start = len(self.code.ops)
                self.expr(c)
                to_end = self.jump(JUMP_IF_FALSE, line)
                self.stmt(body)
                self.emit(JUMP, start, line)
                self.patch(to_end)
            case n.Return(value=value, line=line):
                if value is None:
                    self.emit(NIL, 0, line)
                else:
                    self.expr(value)
                self.emit(RETURN, 0, line)
            case _:
                raise TypeError(f"unknown statement {s!r}")

    def assign_stmt(self, e: n.Assign) -> None:
        """`x = v;` as a statement: store and drop the value in one op.

        An assignment is an expression, so it normally leaves its value on
        the stack and the statement pops it. Loops are full of these, so
        fusing the pair saves one dispatch per assignment.
        """
        self.expr(e.value)
        kind, arg = self.access(self.res.bindings.get(e))
        if kind == "local":
            self.emit(DEFINE_LOCAL, arg, e.line)  # the slot already exists
        elif kind == "global":
            self.emit(SET_GLOBAL, self.const(e.name), e.line)
        else:
            self.emit(STORES[kind], arg, e.line)
            self.emit(POP, 0, e.line)

    def fn_decl(self, s: n.FnDecl) -> None:
        binding = self.res.bindings.get(s)
        if binding is not None and binding in self.res.captured:
            # The function may capture itself (recursion), so its cell must
            # exist before the closure is made: make an empty cell, build the
            # closure, then put the closure in the cell.
            self.emit(NIL, 0, s.line)
            self.emit(MAKE_CELL, binding.slot, s.line)
            self.function(s.function)
            self.emit(STORE_CELL, binding.slot, s.line)
            self.emit(POP, 0, s.line)
        else:
            self.function(s.function)
            self.define(s, s.name, s.line)

    def function(self, f: n.FunctionExpr) -> None:
        info = self.res.functions[f]
        code = Code(f.name, len(f.params), info.nslots)
        inner = _FunctionCompiler(self.res, info, code)
        for binding in info.params:
            if binding in self.res.captured:
                # Arguments arrive as plain values: move them into cells.
                inner.emit(LOAD_LOCAL, binding.slot, f.line)
                inner.emit(MAKE_CELL, binding.slot, f.line)
        for stmt in f.body:
            inner.stmt(stmt)
        inner.emit(NIL, 0, f.line)
        inner.emit(RETURN, 0, f.line)
        code.captures = [self.access(b) for b in info.frees]
        self.emit(MAKE_CLOSURE, self.const(code), f.line)

    # ---- expressions -------------------------------------------------------

    def expr(self, e: object) -> None:
        match e:
            case n.Literal(value=None, line=line):
                self.emit(NIL, 0, line)
            case n.Literal(value=True, line=line):
                self.emit(TRUE, 0, line)
            case n.Literal(value=False, line=line):
                self.emit(FALSE, 0, line)
            case n.Literal(value=value, line=line):
                self.emit(CONST, self.const(value), line)
            case n.Variable():
                self.load(e)
            case n.Assign(name=name, value=value, line=line):
                self.expr(value)
                kind, arg = self.access(self.res.bindings.get(e))
                if kind == "global":
                    arg = self.const(name)
                self.emit(STORES[kind], arg, line)
            case n.Unary(op=op, operand=operand, line=line):
                self.expr(operand)
                self.emit(NEG if op == "-" else NOT, 0, line)
            case n.Binary(op=op, left=left, right=right, line=line):
                self.expr(left)
                self.expr(right)
                self.emit(BINARY_OPS[op], 0, line)
            case n.Logical(op=op, left=left, right=right, line=line):
                self.expr(left)
                jump_op = JUMP_IF_TRUE_OR_POP if op == "or" else JUMP_IF_FALSE_OR_POP
                to_end = self.jump(jump_op, line)
                self.expr(right)
                self.patch(to_end)
            case n.Call(callee=callee, args=args, line=line):
                self.expr(callee)
                for a in args:
                    self.expr(a)
                self.emit(CALL, len(args), line)
            case n.Index(target=t, index=i, line=line):
                self.expr(t)
                self.expr(i)
                self.emit(INDEX_GET, 0, line)
            case n.SetIndex(target=t, index=i, value=v, line=line):
                self.expr(t)
                self.expr(i)
                self.expr(v)
                self.emit(INDEX_SET, 0, line)
            case n.ListLiteral(items=items, line=line):
                for item in items:
                    self.expr(item)
                self.emit(BUILD_LIST, len(items), line)
            case n.FunctionExpr():
                self.function(e)
            case _:
                raise TypeError(f"unknown expression {e!r}")
