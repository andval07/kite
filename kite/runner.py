"""Front door: source text in, program output out, on either engine."""

from __future__ import annotations

import sys
from typing import TextIO

from kite import runtime as rt
from kite.interpreter import Interpreter
from kite.parser import parse
from kite.resolver import resolve

ENGINES = ("tree", "vm")


class Session:
    """Keeps globals between runs, so the REPL remembers earlier lines."""

    def __init__(self, engine: str = "tree", out: TextIO | None = None) -> None:
        if engine not in ENGINES:
            raise ValueError(f"unknown engine {engine!r}, expected one of {ENGINES}")
        self.engine = engine
        self.globals: dict[str, object] = dict(rt.make_builtins(out or sys.stdout))
        self.interpreter = Interpreter(self.globals)

    def run(self, source: str) -> None:
        program = parse(source)
        resolution = resolve(program)  # all static errors before any output
        if self.engine == "tree":
            self.interpreter.run(program, resolution)
        else:
            from kite.compiler import compile_program
            from kite.vm import VM

            VM(self.globals).run(compile_program(program, resolution))


def run(source: str, engine: str = "tree", out: TextIO | None = None) -> None:
    Session(engine, out).run(source)
