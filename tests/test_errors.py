"""Errors must look the same on both engines: same output before the error, same message."""

import io

import pytest

from kite import run
from kite.errors import KiteRuntimeError, KiteSyntaxError

ENGINES = ["tree", "vm"]

RUNTIME_ERRORS = [
    ('print("before");\nprint(1 + "a");', "before\n",
     "runtime error at line 2: operands of '+' must be two numbers or two strings"),
    ("print(missing);", "", "runtime error at line 1: undefined variable 'missing'"),
    ("missing = 1;", "", "runtime error at line 1: undefined variable 'missing'"),
    ("let x = 1 % 0;", "", "runtime error at line 1: division by zero"),
    ("let n = 3; n();", "", "runtime error at line 1: can only call functions"),
    ("fn f(a) {}\nf(1, 2);", "", "runtime error at line 2: f expects 1 argument but got 2"),
    ("let xs = [1];\nprint(xs[1]);", "", "runtime error at line 2: index out of range"),
    ('let xs = [1]; xs["a"] = 2;', "", "runtime error at line 1: list index must be an integer"),
    ('print(-"a");', "", "runtime error at line 1: operand of '-' must be a number"),
    ('print(1 < "a");', "", "runtime error at line 1: operands of '<' must be two numbers or two strings"),
    ("fn loop(n) { return loop(n + 1); }\nloop(0);", "", "runtime error at line 1: stack overflow"),
    ("print(len(3));", "", "runtime error at line 1: len() expects a string or a list"),
]

STATIC_ERRORS = [
    ("return 1;", "error at line 1:1: 'return' outside a function"),
    ("fn f() { let a = 1; let a = 2; }", "error at line 1:25: variable 'a' already declared in this scope"),
    ("fn f(a, b) { a = 1; }\nfn g() { 1 + 1 = 2; }", "error at line 2:16: invalid assignment target"),
]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(("source", "printed", "message"), RUNTIME_ERRORS)
def test_runtime_errors_match_on_both_engines(source, printed, message, engine):
    out = io.StringIO()

    with pytest.raises(KiteRuntimeError) as info:
        run(source, engine=engine, out=out)

    assert str(info.value) == message
    assert out.getvalue() == printed


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(("source", "message"), STATIC_ERRORS)
def test_static_errors_are_found_before_running(source, message, engine):
    out = io.StringIO()

    with pytest.raises(KiteSyntaxError) as info:
        run('print("never");\n' * 0 + source, engine=engine, out=out)

    assert str(info.value) == message
    assert out.getvalue() == ""


@pytest.mark.parametrize("engine", ENGINES)
def test_nothing_runs_if_a_later_line_has_a_syntax_error(engine):
    out = io.StringIO()

    with pytest.raises(KiteSyntaxError):
        run('print("first");\nprint(;', engine=engine, out=out)

    assert out.getvalue() == ""


@pytest.mark.parametrize("engine", ENGINES)
def test_globals_are_allowed_to_be_redeclared(engine):
    out = io.StringIO()

    run("let a = 1; let a = a + 1; print(a);", engine=engine, out=out)

    assert out.getvalue() == "2\n"
