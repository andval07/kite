"""Prints bytecode in a readable form, like Python's `dis` module."""

from __future__ import annotations

from kite.bytecode import (
    CONST, DEFINE_GLOBAL, JUMP, JUMP_IF_FALSE, JUMP_IF_FALSE_OR_POP,
    JUMP_IF_TRUE_OR_POP, LOAD_GLOBAL, MAKE_CLOSURE, OPNAMES, SET_GLOBAL,
    STORE_GLOBAL, Code,
)
from kite.runtime import stringify

NO_ARG = frozenset(
    {"NIL", "TRUE", "FALSE", "POP", "ADD", "SUB", "MUL", "DIV", "MOD", "LT",
     "LE", "GT", "GE", "EQ", "NE", "NEG", "NOT", "RETURN", "INDEX_GET",
     "INDEX_SET"}
)
JUMPS = frozenset({JUMP, JUMP_IF_FALSE, JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP})
NAMED = frozenset({LOAD_GLOBAL, STORE_GLOBAL, DEFINE_GLOBAL, SET_GLOBAL})


def disassemble(code: Code) -> str:
    """Return the listing of `code` and of every function nested in it."""
    out: list[str] = []
    _listing(code, out)
    return "\n".join(out) + "\n"


def _listing(code: Code, out: list[str]) -> None:
    title = code.name or "<fn>"
    out.append(f"== {title} (arity {code.arity}, {code.nslots} slots) ==")
    previous_line = None
    for i, (op, arg) in enumerate(code.ops):
        line = code.lines[i]
        line_col = f"{line:>4}" if line != previous_line else "   |"
        previous_line = line
        name = OPNAMES[op]
        text = f"{line_col} {i:>4}  {name}"
        if name not in NO_ARG:
            text = f"{text:<32}{arg}{_comment(code, op, arg)}"
        out.append(text.rstrip())
    for c in code.consts:
        if isinstance(c, Code):
            out.append("")
            _listing(c, out)


def _comment(code: Code, op: int, arg: int) -> str:
    if op == CONST:
        value = code.consts[arg]
        return f" ({stringify([value])[1:-1]})"  # strings shown with quotes
    if op in NAMED:
        return f" ({code.consts[arg]})"
    if op in JUMPS:
        return f" (to {arg})"
    if op == MAKE_CLOSURE:
        return f" (<fn {code.consts[arg].name or ''}>)".replace(" >", ">")
    return ""
