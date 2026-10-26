"""Value semantics shared by both engines.

Everything that decides what a Kite operation means lives here, so the
interpreter and the VM cannot drift apart. Functions here raise
KiteRuntimeError without a line; the engine adds it.

Kite values are plain Python objects: None (nil), bool, int, float, str,
list, plus the function objects of each engine and Builtin.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from kite.errors import KiteRuntimeError

MAX_CALL_DEPTH = 1000


@dataclass(frozen=True)
class Builtin:
    name: str
    arity: int | None  # None means any number of arguments
    fn: Callable[..., object]


def is_number(v: object) -> bool:
    # type() and not isinstance(): in Python, True is an int. In Kite it is not.
    return type(v) is int or type(v) is float


def truthy(v: object) -> bool:
    return v is not None and v is not False


def values_equal(a: object, b: object) -> bool:
    if is_number(a) and is_number(b):
        return a == b  # 1 == 1.0
    if type(a) is not type(b):
        return False  # 1 != true, 0 != nil
    if type(a) is list:
        return a is b  # lists are compared by identity
    return a == b


def _numbers(op: str, a: object, b: object) -> None:
    if not (is_number(a) and is_number(b)):
        raise KiteRuntimeError(f"operands of '{op}' must be two numbers")


def _comparable(op: str, a: object, b: object) -> None:
    if (is_number(a) and is_number(b)) or (type(a) is str and type(b) is str):
        return
    raise KiteRuntimeError(f"operands of '{op}' must be two numbers or two strings")


def binary_op(op: str, a: object, b: object) -> object:
    if op == "+":
        _comparable("+", a, b)
        return a + b
    if op == "==":
        return values_equal(a, b)
    if op == "!=":
        return not values_equal(a, b)
    if op in ("<", "<=", ">", ">="):
        _comparable(op, a, b)
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        return a >= b
    _numbers(op, a, b)
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if b == 0:
        raise KiteRuntimeError("division by zero")
    if op == "/":
        return a / b
    if op == "%":
        return a % b
    raise KiteRuntimeError(f"unknown operator '{op}'")


def unary_op(op: str, v: object) -> object:
    if op == "not":
        return not truthy(v)
    if not is_number(v):
        raise KiteRuntimeError("operand of '-' must be a number")
    return -v


def _check_index(target: list | str, index: object) -> int:
    if type(index) is not int:
        raise KiteRuntimeError("list index must be an integer")
    if not 0 <= index < len(target):
        raise KiteRuntimeError("index out of range")
    return index


def index_get(target: object, index: object) -> object:
    if type(target) is list or type(target) is str:
        return target[_check_index(target, index)]
    raise KiteRuntimeError("can only index lists and strings")


def index_set(target: object, index: object, value: object) -> object:
    if type(target) is not list:
        raise KiteRuntimeError("can only assign items of a list")
    target[_check_index(target, index)] = value
    return value


def check_arity(name: str | None, expected: int, got: int) -> None:
    if expected != got:
        plural = "" if expected == 1 else "s"
        raise KiteRuntimeError(
            f"{name or 'function'} expects {expected} argument{plural} but got {got}"
        )


def stringify(v: object) -> str:
    return _stringify(v, quote=False, seen=set())


def _stringify(v: object, quote: bool, seen: set[int]) -> str:
    if v is None:
        return "nil"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if type(v) is str:
        return f'"{v}"' if quote else v
    if type(v) is list:
        if id(v) in seen:
            return "[...]"  # a list that contains itself
        inner = seen | {id(v)}
        return "[" + ", ".join(_stringify(x, True, inner) for x in v) + "]"
    if isinstance(v, Builtin):
        return f"<builtin {v.name}>"
    if is_number(v):
        return repr(v)
    name = getattr(v, "name", None)
    return f"<fn {name}>" if name else "<fn>"


def make_builtins(out: TextIO) -> dict[str, Builtin]:
    def kite_print(*args: object) -> None:
        out.write(" ".join(stringify(a) for a in args) + "\n")

    def kite_len(v: object) -> int:
        if type(v) is str or type(v) is list:
            return len(v)
        raise KiteRuntimeError("len() expects a string or a list")

    def kite_push(xs: object, v: object) -> None:
        if type(xs) is not list:
            raise KiteRuntimeError("push() expects a list")
        xs.append(v)

    builtins = [
        Builtin("print", None, kite_print),
        Builtin("len", 1, kite_len),
        Builtin("push", 2, kite_push),
        Builtin("str", 1, stringify),
        Builtin("clock", 0, time.perf_counter),
    ]
    return {b.name: b for b in builtins}


def call_builtin(b: Builtin, args: list[object]) -> object:
    if b.arity is not None:
        check_arity(b.name, b.arity, len(args))
    return b.fn(*args)
