"""Command line: `kite run`, `kite dis` and the REPL."""

from __future__ import annotations

import argparse
import sys

from kite.errors import KiteError
from kite.runner import ENGINES, Session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kite", description="The Kite language.")
    commands = parser.add_subparsers(dest="command")

    run_cmd = commands.add_parser("run", help="run a .kite file")
    run_cmd.add_argument("file")
    run_cmd.add_argument("--engine", choices=ENGINES, default="vm")

    dis_cmd = commands.add_parser("dis", help="print the bytecode of a .kite file")
    dis_cmd.add_argument("file")

    repl_cmd = commands.add_parser("repl", help="interactive prompt (default)")
    repl_cmd.add_argument("--engine", choices=ENGINES, default="vm")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_file(args.file, args.engine)
    if args.command == "dis":
        return _disassemble_file(args.file)
    return _repl(getattr(args, "engine", "vm"))


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as err:
        print(f"kite: cannot read {path}: {err.strerror}", file=sys.stderr)
        return None


def _run_file(path: str, engine: str) -> int:
    source = _read(path)
    if source is None:
        return 2
    try:
        Session(engine).run(source)
    except KiteError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


def _disassemble_file(path: str) -> int:
    from kite.compiler import compile_program
    from kite.disasm import disassemble
    from kite.parser import parse
    from kite.resolver import resolve

    source = _read(path)
    if source is None:
        return 2
    try:
        program = parse(source)
        code = compile_program(program, resolve(program))
    except KiteError as err:
        print(err, file=sys.stderr)
        return 1
    print(disassemble(code), end="")
    return 0


def _repl(engine: str) -> int:
    session = Session(engine)
    print(f"kite ({engine} engine). Ctrl-D or Ctrl-Z to quit.")
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            continue
        if not line.strip():
            continue
        if not line.rstrip().endswith((";", "}")):
            line += ";"  # let the user type `1 + 2` without the semicolon
        try:
            session.run(line)
        except KiteError as err:
            print(err)


if __name__ == "__main__":
    sys.exit(main())
