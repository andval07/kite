"""End-to-end programs. Every program runs on both engines and must print the same thing."""

import io
from pathlib import Path

import pytest

from kite import run

ENGINES = ["tree", "vm"]

PROGRAMS = {
    "arithmetic": (
        "print(1 + 2 * 3, (1 + 2) * 3, 7 % 3, 7 / 2, -2 * 3);",
        "7 9 1 3.5 -6\n",
    ),
    "floats_and_ints": (
        "print(0.1 + 0.2, 6 / 3, 2.5 * 2);",
        "0.30000000000000004 2.0 5.0\n",
    ),
    "strings": (
        'let s = "kite"; print(s + "!", len(s), str(42) + "x", "a\\tb");',
        "kite! 4 42x a\tb\n",
    ),
    "if_else_chain": (
        """
        fn grade(n) {
            if n >= 90 { return "A"; } else if n >= 70 { return "B"; } else { return "C"; }
        }
        print(grade(95), grade(70), grade(10));
        """,
        "A B C\n",
    ),
    "while_sum": (
        "let i = 0; let total = 0; while i <= 100 { total = total + i; i = i + 1; } print(total);",
        "5050\n",
    ),
    "recursion": (
        "fn fib(n) { if n < 2 { return n; } return fib(n - 1) + fib(n - 2); } print(fib(15));",
        "610\n",
    ),
    "counter_closures": (
        """
        fn make_counter() {
            let count = 0;
            return fn() { count = count + 1; return count; };
        }
        let a = make_counter();
        let b = make_counter();
        a();
        print(a(), b(), b() - 1);
        """,
        "2 1 1\n",
    ),
    "capture_per_iteration": (
        """
        let fns = [];
        let i = 0;
        while i < 3 {
            let j = i;
            push(fns, fn() { return j; });
            i = i + 1;
        }
        print(fns[0](), fns[1](), fns[2]());
        """,
        "0 1 2\n",
    ),
    "shared_cell": (
        """
        fn pair() {
            let value = 0;
            let get = fn() { return value; };
            let set = fn(v) { value = v; };
            return [get, set];
        }
        let p = pair();
        p[1](7);
        print(p[0]());
        """,
        "7\n",
    ),
    "nested_closure_three_levels": (
        """
        fn outer() {
            let x = "out";
            fn middle() {
                fn inner() { return x + "!"; }
                return inner;
            }
            return middle();
        }
        print(outer()());
        """,
        "out!\n",
    ),
    "local_recursive_function": (
        """
        fn run() {
            fn fact(n) { if n <= 1 { return 1; } return n * fact(n - 1); }
            return fact(10);
        }
        print(run());
        """,
        "3628800\n",
    ),
    "captured_parameter": (
        """
        fn adder(n) { return fn(x) { return x + n; }; }
        let add5 = adder(5);
        print(add5(1), adder(10)(1));
        """,
        "6 11\n",
    ),
    "lists": (
        """
        let xs = [1, "a", [true, nil]];
        xs[0] = xs[0] + 1;
        push(xs, 3.5);
        print(xs, len(xs), xs[2][0]);
        """,
        '[2, "a", [true, nil], 3.5] 4 true\n',
    ),
    "short_circuit": (
        'fn crash() { return 1 / 0; } print(nil or "default", false and crash(), 0 or 1);',
        "default false 0\n",
    ),
    "equality": (
        'print(1 == 1.0, 1 == true, "a" == "a", nil == nil, [1] == [1], 1 != 2);',
        "true false true true false true\n",
    ),
    "truthiness": (
        'if 0 { print("zero is truthy"); } if "" { print("empty too"); } print(not nil, not 0);',
        "zero is truthy\nempty too\ntrue false\n",
    ),
    "mutual_recursion_of_globals": (
        """
        fn is_even(n) { if n == 0 { return true; } return is_odd(n - 1); }
        fn is_odd(n) { if n == 0 { return false; } return is_even(n - 1); }
        print(is_even(10), is_odd(7));
        """,
        "true true\n",
    ),
    "higher_order": (
        """
        fn map(xs, f) {
            let out = [];
            let i = 0;
            while i < len(xs) { push(out, f(xs[i])); i = i + 1; }
            return out;
        }
        print(map([1, 2, 3], fn(x) { return x * x; }));
        """,
        "[1, 4, 9]\n",
    ),
    "implicit_nil_return": (
        "fn nothing() { } fn early() { return; } print(nothing(), early());",
        "nil nil\n",
    ),
    "assignment_is_an_expression": (
        "let a = 0; let b = 0; a = b = 5; print(a, b, (a = 1) + 1);",
        "5 5 2\n",
    ),
    "shadowing_in_blocks": (
        'let x = "global"; { let x = "block"; print(x); } print(x);',
        "block\nglobal\n",
    ),
    "let_initializer_sees_outer_variable": (
        "fn f() { let x = 1; { let x = x + 1; print(x); } print(x); } f();",
        "2\n1\n",
    ),
    "functions_print_their_name": (
        "fn hello() {} print(hello, fn() {}, print);",
        "<fn hello> <fn> <builtin print>\n",
    ),
}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("name", PROGRAMS)
def test_program_output(name, engine):
    source, expected = PROGRAMS[name]
    out = io.StringIO()

    run(source, engine=engine, out=out)

    assert out.getvalue() == expected


EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.kite"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_examples_give_the_same_output_on_both_engines(path):
    source = path.read_text(encoding="utf-8")
    outputs = []
    for engine in ENGINES:
        out = io.StringIO()
        run(source, engine=engine, out=out)
        outputs.append(out.getvalue())

    assert outputs[0] == outputs[1] != ""
