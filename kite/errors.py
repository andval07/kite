"""The two kinds of error a Kite program can raise."""

from __future__ import annotations


class KiteError(Exception):
    """Base class, so callers can catch every Kite error at once."""


class KiteSyntaxError(KiteError):
    """Found before the program runs: lexer, parser or resolver."""

    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"error at line {line}:{col}: {message}")
        self.message = message
        self.line = line
        self.col = col


class KiteRuntimeError(KiteError):
    """Found while the program runs.

    The shared runtime raises it without a line, because it does not know where
    it was called from. Each engine then calls `at(line)` with the line of the
    node or instruction it was executing, so both engines print the same text.
    """

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line

    def at(self, line: int) -> KiteRuntimeError:
        if self.line is None:
            self.line = line
        return self

    def __str__(self) -> str:
        if self.line is None:
            return f"runtime error: {self.message}"
        return f"runtime error at line {self.line}: {self.message}"
