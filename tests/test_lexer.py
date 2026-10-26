import pytest

from kite.errors import KiteSyntaxError
from kite.lexer import tokenize


def kinds(source):
    return [t.kind for t in tokenize(source)]


def test_punctuation_keywords_and_identifiers():
    assert kinds("let x = fn(a) { return a <= 2; };") == [
        "let", "IDENT", "=", "fn", "(", "IDENT", ")", "{",
        "return", "IDENT", "<=", "NUMBER", ";", "}", ";", "EOF",
    ]


def test_numbers_are_int_or_float():
    values = [t.value for t in tokenize("42 3.5 7")[:-1]]

    assert values == [42, 3.5, 7]
    assert isinstance(values[0], int) and isinstance(values[1], float)


def test_string_escapes():
    (token, _) = tokenize(r'"a\tb\n\"q\" \\"')

    assert token.kind == "STRING"
    assert token.value == 'a\tb\n"q" \\'


def test_comments_are_skipped_and_lines_are_counted():
    tokens = tokenize("// header\nlet a = 1; // trailing\n\nprint(a);")

    assert [(t.text, t.line) for t in tokens[:2]] == [("let", 2), ("a", 2)]
    assert tokens[5].text == "print" and tokens[5].line == 4


def test_columns_point_at_token_start():
    tokens = tokenize("let  value")

    assert (tokens[1].line, tokens[1].col) == (1, 6)


def test_unterminated_string_fails():
    with pytest.raises(KiteSyntaxError, match="unterminated string"):
        tokenize('print("oops);')


def test_unexpected_character_fails_with_position():
    with pytest.raises(KiteSyntaxError, match=r"line 2:3: unexpected character '@'"):
        tokenize("x;\nx @ y;")
