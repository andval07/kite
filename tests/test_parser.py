import pytest

from kite.errors import KiteSyntaxError
from kite.nodes import to_sexpr
from kite.parser import parse


def expr(source):
    """Parse a single expression statement and return it as an s-expression."""
    (stmt,) = parse(source + ";").body
    return to_sexpr(stmt)


@pytest.mark.parametrize(
    ("source", "tree"),
    [
        ("1 + 2 * 3", "(+ 1 (* 2 3))"),
        ("(1 + 2) * 3", "(* (+ 1 2) 3)"),
        ("1 - 2 - 3", "(- (- 1 2) 3)"),
        ("a = b = 1", "(= a (= b 1))"),
        ("-x * y", "(* (- x) y)"),
        ("not a == b", "(== (not a) b)"),
        ("a or b and c", "(or a (and b c))"),
        ("1 < 2 == true", "(== (< 1 2) true)"),
        ("f(1, x)[2]", "(index (call f 1 x) 2)"),
        ("xs[0] = nil", "(set-index xs 0 nil)"),
        ('[1, "a", []]', '(list 1 "a" (list))'),
        ("fn(a, b) { return a; }", "(fn _ (a b) (return a))"),
    ],
)
def test_expression_precedence_and_shape(source, tree):
    assert expr(source) == tree


def test_statements():
    program = parse(
        """
        let x = 1;
        fn inc(n) { return n + 1; }
        if x < 2 { x = inc(x); } else if x { x = 0; } else { }
        while x > 0 { x = x - 1; }
        """
    )

    assert [to_sexpr(s) for s in program.body] == [
        "(let x 1)",
        "(fn inc (n) (return (+ n 1)))",
        "(if (< x 2) (block (= x (call inc x))) (if x (block (= x 0)) (block)))",
        "(while (> x 0) (block (= x (- x 1))))",
    ]


def test_nodes_remember_their_line():
    program = parse("let a = 1;\n\nprint(a);")

    assert [s.line for s in program.body] == [1, 3]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("print(1)", r"line 1:9: expected ';' after expression"),
        ("1 = 2;", r"line 1:3: invalid assignment target"),
        ("let = 3;", r"line 1:5: expected variable name"),
        ("if x { print(1);", r"expected '}'"),
        ("fn f(a, a) {}", r"duplicate parameter 'a'"),
        ("print(1 +);", r"line 1:10: expected an expression"),
    ],
)
def test_syntax_errors(source, message):
    with pytest.raises(KiteSyntaxError, match=message):
        parse(source)
