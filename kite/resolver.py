"""Static scope analysis, run once before either engine.

For every use of a name it decides, before the program runs, which declaration
the name refers to. Both engines read the result:

- the tree-walking interpreter reads `depths`: how many scopes to walk up;
- the compiler reads `bindings`, `captured` and `functions` to choose between
  global, local slot, cell (a local some closure captured) and free variable
  (a captured variable that belongs to an enclosing function).

It also reports the errors that do not need running: `return` outside a
function and a name declared twice in the same scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kite import nodes as n
from kite.errors import KiteSyntaxError


class FunctionState:
    """One function being resolved (the top-level script counts as one)."""

    def __init__(self, parent: FunctionState | None, is_script: bool) -> None:
        self.parent = parent
        self.is_script = is_script
        self.nslots = 0
        self.frees: list[Binding] = []  # captured from outside, in order


@dataclass(frozen=True, eq=False)
class Binding:
    """One declared local variable."""

    name: str
    slot: int
    owner: FunctionState


@dataclass(frozen=True)
class FunctionInfo:
    params: tuple[Binding, ...]
    nslots: int
    frees: tuple[Binding, ...]
    state: FunctionState  # owner of this function's own locals


@dataclass
class Resolution:
    depths: dict[object, int] = field(default_factory=dict)
    bindings: dict[object, Binding] = field(default_factory=dict)
    captured: set[Binding] = field(default_factory=set)
    functions: dict[object, FunctionInfo] = field(default_factory=dict)


def resolve(program: n.Program) -> Resolution:
    return _Resolver().run(program)


class _Resolver:
    def __init__(self) -> None:
        self.result = Resolution()
        self.scopes: list[dict[str, Binding]] = []
        self.function = FunctionState(None, is_script=True)

    def run(self, program: n.Program) -> Resolution:
        for stmt in program.body:
            self._stmt(stmt)
        self.result.functions[program] = FunctionInfo(
            (), self.function.nslots, (), self.function
        )
        return self.result

    # ---- scopes ------------------------------------------------------------

    def _declare(self, name: str, decl: object, line: int, col: int) -> None:
        if not self.scopes:
            return  # top level: a global, redeclaring is allowed
        scope = self.scopes[-1]
        if name in scope:
            raise KiteSyntaxError(
                f"variable '{name}' already declared in this scope", line, col
            )
        binding = Binding(name, self.function.nslots, self.function)
        self.function.nslots += 1
        scope[name] = binding
        self.result.bindings[decl] = binding

    def _use(self, name: str, node: object) -> None:
        for hops, scope in enumerate(reversed(self.scopes)):
            binding = scope.get(name)
            if binding is None:
                continue
            self.result.depths[node] = hops
            self.result.bindings[node] = binding
            if binding.owner is not self.function:
                self._capture(binding)
            return
        # not found: a global, looked up by name at run time

    def _capture(self, binding: Binding) -> None:
        """Mark a variable as captured and pass it down through every
        function between its owner and the one that uses it."""
        self.result.captured.add(binding)
        fn = self.function
        while fn is not binding.owner:
            if binding not in fn.frees:
                fn.frees.append(binding)
            fn = fn.parent

    # ---- statements --------------------------------------------------------

    def _stmt(self, s: object) -> None:
        match s:
            case n.ExprStmt(expr=e):
                self._expr(e)
            case n.Let(name=name, value=value, line=line, col=col):
                self._expr(value)  # before declaring: `let x = x + 1` reads the outer x
                self._declare(name, s, line, col)
            case n.FnDecl(name=name, function=f, line=line, col=col):
                self._declare(name, s, line, col)  # before the body: recursion works
                self._function(f)
            case n.Block(body=body):
                self.scopes.append({})
                for inner in body:
                    self._stmt(inner)
                self.scopes.pop()
            case n.If(condition=c, then=t, otherwise=o):
                self._expr(c)
                self._stmt(t)
                if o is not None:
                    self._stmt(o)
            case n.While(condition=c, body=b):
                self._expr(c)
                self._stmt(b)
            case n.Return(value=v, line=line, col=col):
                if self.function.is_script:
                    raise KiteSyntaxError("'return' outside a function", line, col)
                if v is not None:
                    self._expr(v)
            case _:
                raise TypeError(f"unknown statement {s!r}")

    def _function(self, f: n.FunctionExpr) -> None:
        enclosing = self.function
        self.function = FunctionState(enclosing, is_script=False)
        self.scopes.append({})
        for p in f.params:
            self._declare(p.name, p, p.line, p.col)
        for stmt in f.body:
            self._stmt(stmt)
        self.scopes.pop()
        params = tuple(self.result.bindings[p] for p in f.params)
        self.result.functions[f] = FunctionInfo(
            params, self.function.nslots, tuple(self.function.frees), self.function
        )
        self.function = enclosing

    # ---- expressions -------------------------------------------------------

    def _expr(self, e: object) -> None:
        match e:
            case n.Literal():
                pass
            case n.Variable(name=name):
                self._use(name, e)
            case n.Assign(name=name, value=value):
                self._expr(value)
                self._use(name, e)
            case n.Unary(operand=o):
                self._expr(o)
            case n.Binary(left=l, right=r) | n.Logical(left=l, right=r):
                self._expr(l)
                self._expr(r)
            case n.Call(callee=callee, args=args):
                self._expr(callee)
                for a in args:
                    self._expr(a)
            case n.Index(target=t, index=i):
                self._expr(t)
                self._expr(i)
            case n.SetIndex(target=t, index=i, value=v):
                self._expr(t)
                self._expr(i)
                self._expr(v)
            case n.ListLiteral(items=items):
                for item in items:
                    self._expr(item)
            case n.FunctionExpr():
                self._function(e)
            case _:
                raise TypeError(f"unknown expression {e!r}")
