"""Engine 1: a tree-walking interpreter. It evaluates the AST directly."""

from __future__ import annotations

import sys

from kite import nodes as n
from kite import runtime as rt
from kite.errors import KiteRuntimeError
from kite.resolver import Resolution

# Each Kite call uses several Python frames (call -> block -> statement ->
# expression -> ...), so Python's default limit of 1000 is too low.
PYTHON_RECURSION_LIMIT = 30_000


class Environment:
    """One scope at run time: a block body or a function call."""

    __slots__ = ("values", "parent")

    def __init__(self, parent: Environment | None) -> None:
        self.values: dict[str, object] = {}
        self.parent = parent

    def ancestor(self, depth: int) -> Environment:
        env = self
        for _ in range(depth):
            env = env.parent
        return env


class Function:
    __slots__ = ("decl", "closure")

    def __init__(self, decl: n.FunctionExpr, closure: Environment | None) -> None:
        self.decl = decl
        self.closure = closure

    @property
    def name(self) -> str | None:
        return self.decl.name


class _Return(Exception):
    """Unwinds the Python stack from a `return` back to the call."""

    def __init__(self, value: object) -> None:
        self.value = value


class Interpreter:
    def __init__(self, globals_: dict[str, object]) -> None:
        self.globals = globals_
        self.depths: dict[object, int] = {}
        self.call_depth = 0
        self._stmt_table = {
            n.ExprStmt: self._expr_stmt,
            n.Let: self._let,
            n.FnDecl: self._fn_decl,
            n.Block: self._block,
            n.If: self._if,
            n.While: self._while,
            n.Return: self._return,
        }
        self._expr_table = {
            n.Literal: lambda e, env: e.value,
            n.Variable: self._variable,
            n.Assign: self._assign,
            n.Unary: self._unary,
            n.Binary: self._binary,
            n.Logical: self._logical,
            n.Call: self._call,
            n.Index: self._index,
            n.SetIndex: self._set_index,
            n.ListLiteral: lambda e, env: [self.eval(i, env) for i in e.items],
            n.FunctionExpr: lambda e, env: Function(e, env),
        }

    def run(self, program: n.Program, resolution: Resolution) -> None:
        # Keep the depths of earlier runs: in the REPL a function defined on
        # one line is called on a later one, and its body was resolved then.
        self.depths.update(resolution.depths)
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, PYTHON_RECURSION_LIMIT))
        try:
            for stmt in program.body:
                self.execute(stmt, None)
        finally:
            sys.setrecursionlimit(old_limit)

    # ---- statements --------------------------------------------------------

    def execute(self, stmt: object, env: Environment | None) -> None:
        self._stmt_table[type(stmt)](stmt, env)

    def _define(self, name: str, value: object, env: Environment | None) -> None:
        if env is None:
            self.globals[name] = value
        else:
            env.values[name] = value

    def _expr_stmt(self, s: n.ExprStmt, env: Environment | None) -> None:
        self.eval(s.expr, env)

    def _let(self, s: n.Let, env: Environment | None) -> None:
        self._define(s.name, self.eval(s.value, env), env)

    def _fn_decl(self, s: n.FnDecl, env: Environment | None) -> None:
        self._define(s.name, Function(s.function, env), env)

    def _block(self, s: n.Block, env: Environment | None) -> None:
        inner = Environment(env)  # new scope each time: each loop turn too
        for stmt in s.body:
            self.execute(stmt, inner)

    def _if(self, s: n.If, env: Environment | None) -> None:
        if rt.truthy(self.eval(s.condition, env)):
            self._block(s.then, env)
        elif s.otherwise is not None:
            self.execute(s.otherwise, env)

    def _while(self, s: n.While, env: Environment | None) -> None:
        while rt.truthy(self.eval(s.condition, env)):
            self._block(s.body, env)

    def _return(self, s: n.Return, env: Environment | None) -> None:
        value = None if s.value is None else self.eval(s.value, env)
        raise _Return(value)

    # ---- expressions -------------------------------------------------------

    def eval(self, e: object, env: Environment | None) -> object:
        try:
            return self._expr_table[type(e)](e, env)
        except KiteRuntimeError as err:
            raise err.at(e.line)

    def _variable(self, e: n.Variable, env: Environment | None) -> object:
        depth = self.depths.get(e)
        if depth is not None:
            return env.ancestor(depth).values[e.name]
        try:
            return self.globals[e.name]
        except KeyError:
            raise KiteRuntimeError(f"undefined variable '{e.name}'") from None

    def _assign(self, e: n.Assign, env: Environment | None) -> object:
        value = self.eval(e.value, env)
        depth = self.depths.get(e)
        if depth is not None:
            env.ancestor(depth).values[e.name] = value
        elif e.name in self.globals:
            self.globals[e.name] = value
        else:
            raise KiteRuntimeError(f"undefined variable '{e.name}'")
        return value

    def _unary(self, e: n.Unary, env: Environment | None) -> object:
        return rt.unary_op(e.op, self.eval(e.operand, env))

    def _binary(self, e: n.Binary, env: Environment | None) -> object:
        left = self.eval(e.left, env)
        right = self.eval(e.right, env)
        return rt.binary_op(e.op, left, right)

    def _logical(self, e: n.Logical, env: Environment | None) -> object:
        left = self.eval(e.left, env)
        if (e.op == "or") == rt.truthy(left):
            return left  # short circuit: returns the operand, not a bool
        return self.eval(e.right, env)

    def _index(self, e: n.Index, env: Environment | None) -> object:
        return rt.index_get(self.eval(e.target, env), self.eval(e.index, env))

    def _set_index(self, e: n.SetIndex, env: Environment | None) -> object:
        target = self.eval(e.target, env)
        index = self.eval(e.index, env)
        return rt.index_set(target, index, self.eval(e.value, env))

    def _call(self, e: n.Call, env: Environment | None) -> object:
        callee = self.eval(e.callee, env)
        args = [self.eval(a, env) for a in e.args]
        if isinstance(callee, rt.Builtin):
            return rt.call_builtin(callee, args)
        if not isinstance(callee, Function):
            raise KiteRuntimeError("can only call functions")
        return self.call_function(callee, args)

    def call_function(self, fn: Function, args: list[object]) -> object:
        decl = fn.decl
        rt.check_arity(decl.name, len(decl.params), len(args))
        if self.call_depth >= rt.MAX_CALL_DEPTH:
            raise KiteRuntimeError("stack overflow")
        env = Environment(fn.closure)
        for param, arg in zip(decl.params, args):
            env.values[param.name] = arg
        self.call_depth += 1
        try:
            for stmt in decl.body:
                self.execute(stmt, env)
        except _Return as ret:
            return ret.value
        finally:
            self.call_depth -= 1
        return None
