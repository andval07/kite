"""Bytecode format shared by the compiler, the VM and the disassembler.

Every instruction is a pair (opcode, argument). Instructions that need no
argument carry 0. Opcodes are small ints so the VM can compare them fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field

OPNAMES = (
    "CONST", "NIL", "TRUE", "FALSE", "POP",
    "LOAD_LOCAL", "STORE_LOCAL", "DEFINE_LOCAL",
    "MAKE_CELL", "LOAD_CELL", "STORE_CELL",
    "LOAD_FREE", "STORE_FREE",
    "LOAD_GLOBAL", "STORE_GLOBAL", "DEFINE_GLOBAL", "SET_GLOBAL",
    "ADD", "SUB", "MUL", "DIV", "MOD",
    "LT", "LE", "GT", "GE", "EQ", "NE", "NEG", "NOT",
    "JUMP", "JUMP_IF_FALSE", "JUMP_IF_FALSE_OR_POP", "JUMP_IF_TRUE_OR_POP",
    "CALL", "RETURN", "MAKE_CLOSURE", "BUILD_LIST", "INDEX_GET", "INDEX_SET",
)
(
    CONST, NIL, TRUE, FALSE, POP,
    LOAD_LOCAL, STORE_LOCAL, DEFINE_LOCAL,
    MAKE_CELL, LOAD_CELL, STORE_CELL,
    LOAD_FREE, STORE_FREE,
    LOAD_GLOBAL, STORE_GLOBAL, DEFINE_GLOBAL, SET_GLOBAL,
    ADD, SUB, MUL, DIV, MOD,
    LT, LE, GT, GE, EQ, NE, NEG, NOT,
    JUMP, JUMP_IF_FALSE, JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP,
    CALL, RETURN, MAKE_CLOSURE, BUILD_LIST, INDEX_GET, INDEX_SET,
) = range(len(OPNAMES))

BINARY_OPS = {
    "+": ADD, "-": SUB, "*": MUL, "/": DIV, "%": MOD,
    "<": LT, "<=": LE, ">": GT, ">=": GE, "==": EQ, "!=": NE,
}
# Opcode -> Kite operator, for the slow path that calls the shared runtime.
OP_SYMBOLS = {code: symbol for symbol, code in BINARY_OPS.items()}


@dataclass
class Code:
    """A compiled function (or the top-level script)."""

    name: str | None
    arity: int
    nslots: int  # size of the locals array
    ops: list[tuple[int, int]] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)  # source line of each op
    consts: list[object] = field(default_factory=list)
    # How MAKE_CLOSURE finds each free variable in the frame that creates the
    # closure: ("cell", slot) is a cell in its locals, ("free", i) is one of
    # its own free variables.
    captures: list[tuple[str, int]] = field(default_factory=list)


class Cell:
    """A box that holds a captured variable, shared by every closure using it."""

    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value


class Closure:
    __slots__ = ("code", "frees")

    def __init__(self, code: Code, frees: tuple[Cell, ...]) -> None:
        self.code = code
        self.frees = frees

    @property
    def name(self) -> str | None:
        return self.code.name
