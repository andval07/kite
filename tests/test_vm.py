"""Tests that look inside the compiler and the VM, plus the REPL session."""

import io

import pytest

from kite import Session, run
from kite.bytecode import LOAD_LOCAL, MAKE_CELL, OPNAMES, Code
from kite.compiler import compile_program
from kite.disasm import disassemble
from kite.errors import KiteRuntimeError
from kite.parser import parse
from kite.resolver import resolve


def compile_source(source):
    program = parse(source)
    return compile_program(program, resolve(program))


def opnames(code):
    return [OPNAMES[op] for op, _ in code.ops]


def nested(code, name):
    return next(
        c for c in code.consts if isinstance(c, Code) and c.name == name
    )


def test_plain_locals_use_slots_not_cells():
    script = compile_source("fn f(a) { let b = a + 1; return b; }")
    f = nested(script, "f")

    assert opnames(f) == [
        "LOAD_LOCAL", "CONST", "ADD", "DEFINE_LOCAL",
        "LOAD_LOCAL", "RETURN", "NIL", "RETURN",
    ]
    assert MAKE_CELL not in [op for op, _ in f.ops]


def test_captured_variables_become_cells():
    script = compile_source(
        "fn counter(start) { let n = 0; return fn() { n = n + start; return n; }; }"
    )
    counter = nested(script, "counter")
    inner = nested(counter, None)

    # the parameter is captured, so the prologue moves it into a cell
    assert counter.ops[:2] == [(LOAD_LOCAL, 0), (MAKE_CELL, 0)]
    assert "MAKE_CELL" in opnames(counter)[2:]  # let n: a fresh cell
    assert inner.captures == [("cell", 1), ("cell", 0)]
    assert opnames(inner)[:4] == ["LOAD_FREE", "LOAD_FREE", "ADD", "STORE_FREE"]


def test_free_variables_pass_through_middle_functions():
    script = compile_source(
        "fn a() { let x = 1; fn b() { fn c() { return x; } return c; } return b; }"
    )
    b = nested(nested(script, "a"), "b")
    c = nested(b, "c")

    assert b.captures == [("cell", 0)]  # b takes x from a's cell
    assert c.captures == [("free", 0)]  # c takes it from b's free list


def test_disassembler_listing():
    listing = disassemble(compile_source('let x = 1;\nif x { print("hi"); }'))

    assert listing.splitlines() == [
        "== <script> (arity 0, 0 slots) ==",
        "   1    0  CONST                0 (1)",
        "   |    1  DEFINE_GLOBAL        1 (x)",
        "   2    2  LOAD_GLOBAL          1 (x)",
        "   |    3  JUMP_IF_FALSE        8 (to 8)",
        "   |    4  LOAD_GLOBAL          2 (print)",
        '   |    5  CONST                3 ("hi")',
        "   |    6  CALL                 1",
        "   |    7  POP",
        "   |    8  NIL",
        "   |    9  RETURN",
    ]


@pytest.mark.parametrize("engine", ["tree", "vm"])
def test_deep_recursion_below_the_limit_works(engine):
    out = io.StringIO()

    run(
        "fn down(n) { if n == 0 { return 0; } return 1 + down(n - 1); } print(down(999));",
        engine=engine,
        out=out,
    )

    assert out.getvalue() == "999\n"


@pytest.mark.parametrize("engine", ["tree", "vm"])
def test_session_keeps_globals_between_runs(engine):
    out = io.StringIO()
    session = Session(engine, out)

    session.run("let total = 10; fn add(n) { total = total + n; }")
    session.run("add(5); print(total);")

    assert out.getvalue() == "15\n"


@pytest.mark.parametrize("engine", ["tree", "vm"])
def test_session_survives_a_runtime_error(engine):
    out = io.StringIO()
    session = Session(engine, out)
    session.run("let a = 1;")

    with pytest.raises(KiteRuntimeError):
        session.run("print(a / 0);")
    session.run("print(a);")

    assert out.getvalue() == "1\n"


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError, match="unknown engine"):
        Session("jit")
