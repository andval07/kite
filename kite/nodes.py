"""AST nodes.

Nodes are frozen, and compare by identity (eq=False), so the resolver can use
them as dictionary keys: two `x` in different places are different uses.
"""

from __future__ import annotations

from dataclasses import dataclass

node = dataclass(frozen=True, eq=False)


# ---- expressions -----------------------------------------------------------

@node
class Literal:
    value: object
    line: int


@node
class Variable:
    name: str
    line: int
    col: int


@node
class Assign:
    name: str
    value: object
    line: int
    col: int


@node
class Unary:
    op: str
    operand: object
    line: int


@node
class Binary:
    op: str
    left: object
    right: object
    line: int


@node
class Logical:
    op: str  # "and" / "or"
    left: object
    right: object
    line: int


@node
class Call:
    callee: object
    args: tuple
    line: int


@node
class Index:
    target: object
    index: object
    line: int


@node
class SetIndex:
    target: object
    index: object
    value: object
    line: int


@node
class ListLiteral:
    items: tuple
    line: int


@node
class FunctionExpr:
    name: str | None
    params: tuple  # of Variable, so each parameter keeps its position
    body: tuple
    line: int


# ---- statements ------------------------------------------------------------

@node
class ExprStmt:
    expr: object
    line: int


@node
class Let:
    name: str
    value: object
    line: int
    col: int


@node
class FnDecl:
    name: str
    function: FunctionExpr
    line: int
    col: int


@node
class Block:
    body: tuple
    line: int


@node
class If:
    condition: object
    then: Block
    otherwise: object  # Block, If or None
    line: int


@node
class While:
    condition: object
    body: Block
    line: int


@node
class Return:
    value: object  # None means "return nil"
    line: int
    col: int


@node
class Program:
    body: tuple
    line: int = 1


# ---- printing, used by the parser tests ------------------------------------

def to_sexpr(n: object) -> str:
    match n:
        case Literal(value=None):
            return "nil"
        case Literal(value=bool() as b):
            return "true" if b else "false"
        case Literal(value=str() as s):
            return '"' + s + '"'
        case Literal(value=v):
            return repr(v)
        case Variable(name=name):
            return name
        case Assign(name=name, value=value):
            return f"(= {name} {to_sexpr(value)})"
        case Unary(op=op, operand=operand):
            return f"({op} {to_sexpr(operand)})"
        case Binary(op=op, left=l, right=r) | Logical(op=op, left=l, right=r):
            return f"({op} {to_sexpr(l)} {to_sexpr(r)})"
        case Call(callee=callee, args=args):
            return _sexpr("call", callee, *args)
        case Index(target=t, index=i):
            return _sexpr("index", t, i)
        case SetIndex(target=t, index=i, value=v):
            return _sexpr("set-index", t, i, v)
        case ListLiteral(items=items):
            return _sexpr("list", *items)
        case FunctionExpr(name=name, params=params, body=body):
            names = " ".join(p.name for p in params)
            return _sexpr(f"fn {name or '_'} ({names})", *body)
        case ExprStmt(expr=e):
            return to_sexpr(e)
        case Let(name=name, value=value):
            return f"(let {name} {to_sexpr(value)})"
        case FnDecl(function=f):
            return to_sexpr(f)
        case Block(body=body):
            return _sexpr("block", *body)
        case If(condition=c, then=t, otherwise=o):
            return _sexpr("if", c, t, *([o] if o is not None else []))
        case While(condition=c, body=b):
            return _sexpr("while", c, b)
        case Return(value=v):
            return _sexpr("return", *([v] if v is not None else []))
        case Program(body=body):
            return "\n".join(to_sexpr(s) for s in body)
    raise TypeError(f"not a node: {n!r}")


def _sexpr(head: str, *parts: object) -> str:
    return "(" + " ".join([head, *(to_sexpr(p) for p in parts)]) + ")"
