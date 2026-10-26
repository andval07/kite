"""Turns source text into a list of tokens."""

from __future__ import annotations

from dataclasses import dataclass

from kite.errors import KiteSyntaxError

KEYWORDS = frozenset(
    {"let", "fn", "if", "else", "while", "return", "and", "or", "not",
     "true", "false", "nil"}
)
TWO_CHAR = frozenset({"==", "!=", "<=", ">="})
ONE_CHAR = frozenset("+-*/%=<>(){}[],;")
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


@dataclass(frozen=True)
class Token:
    kind: str  # NUMBER, STRING, IDENT, EOF, or the text of a keyword/symbol
    text: str
    value: object
    line: int
    col: int


def tokenize(source: str) -> list[Token]:
    return _Lexer(source).run()


class _Lexer:
    def __init__(self, source: str) -> None:
        self.src = source
        self.pos = 0
        self.line = 1
        self.line_start = 0
        self.tokens: list[Token] = []

    def run(self) -> list[Token]:
        while True:
            self._skip_space_and_comments()
            if self.pos >= len(self.src):
                self.tokens.append(Token("EOF", "", None, self.line, self._col()))
                return self.tokens
            self._token()

    def _col(self, pos: int | None = None) -> int:
        return (self.pos if pos is None else pos) - self.line_start + 1

    def _peek(self, ahead: int = 0) -> str:
        i = self.pos + ahead
        return self.src[i] if i < len(self.src) else ""

    def _newline(self) -> None:
        self.line += 1
        self.line_start = self.pos + 1

    def _skip_space_and_comments(self) -> None:
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == "\n":
                self._newline()
                self.pos += 1
            elif ch in " \t\r":
                self.pos += 1
            elif ch == "/" and self._peek(1) == "/":
                while self.pos < len(self.src) and self.src[self.pos] != "\n":
                    self.pos += 1
            else:
                return

    def _add(self, kind: str, start: int, value: object = None) -> None:
        text = self.src[start:self.pos]
        self.tokens.append(Token(kind, text, value, self.line, self._col(start)))

    def _token(self) -> None:
        start = self.pos
        ch = self.src[start]
        if ch.isdigit():
            self._number(start)
        elif ch.isalpha() or ch == "_":
            while self._peek().isalnum() or self._peek() == "_":
                self.pos += 1
            text = self.src[start:self.pos]
            self._add(text if text in KEYWORDS else "IDENT", start)
        elif ch == '"':
            self._string(start)
        elif self.src[start:start + 2] in TWO_CHAR:
            self.pos += 2
            self._add(self.src[start:self.pos], start)
        elif ch in ONE_CHAR:
            self.pos += 1
            self._add(ch, start)
        else:
            raise KiteSyntaxError(
                f"unexpected character {ch!r}", self.line, self._col()
            )

    def _number(self, start: int) -> None:
        while self._peek().isdigit():
            self.pos += 1
        if self._peek() == "." and self._peek(1).isdigit():
            self.pos += 1
            while self._peek().isdigit():
                self.pos += 1
            self._add("NUMBER", start, float(self.src[start:self.pos]))
        else:
            self._add("NUMBER", start, int(self.src[start:self.pos]))

    def _string(self, start: int) -> None:
        line, col = self.line, self._col()
        self.pos += 1  # opening quote
        chars: list[str] = []
        while True:
            ch = self._peek()
            if ch == "" or ch == "\n":
                raise KiteSyntaxError("unterminated string", line, col)
            if ch == '"':
                break
            if ch == "\\":
                escaped = self._peek(1)
                if escaped not in ESCAPES:
                    raise KiteSyntaxError(
                        f"unknown escape '\\{escaped}'", self.line, self._col()
                    )
                chars.append(ESCAPES[escaped])
                self.pos += 2
            else:
                chars.append(ch)
                self.pos += 1
        self.pos += 1  # closing quote
        text = self.src[start:self.pos]
        self.tokens.append(Token("STRING", text, "".join(chars), line, col))
