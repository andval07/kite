"""Engine 2, part 2: a stack virtual machine that runs the compiler's bytecode.

One operand stack is shared by all calls. Each call gets a frame with its own
locals array. The main loop keeps the current frame in Python local
variables, because local access is the fastest thing CPython does.
"""

from __future__ import annotations

from kite import runtime as rt
from kite.bytecode import (
    ADD, BUILD_LIST, CALL, CONST, DEFINE_GLOBAL, DEFINE_LOCAL, DIV, EQ, FALSE,
    GE, GT, INDEX_GET, INDEX_SET, JUMP, JUMP_IF_FALSE, JUMP_IF_FALSE_OR_POP,
    JUMP_IF_TRUE_OR_POP, LE, LOAD_CELL, LOAD_FREE, LOAD_GLOBAL, LOAD_LOCAL, LT,
    MAKE_CELL, MAKE_CLOSURE, MOD, MUL, NE, NEG, NIL, NOT, OP_SYMBOLS, POP,
    RETURN, SET_GLOBAL, STORE_CELL, STORE_FREE, STORE_GLOBAL, STORE_LOCAL, SUB, TRUE, Cell,
    Closure, Code,
)
from kite.errors import KiteRuntimeError


class VM:
    def __init__(self, globals_: dict[str, object]) -> None:
        self.globals = globals_

    def run(self, script: Code) -> object:
        code = script
        ops, consts = code.ops, code.consts
        local = [None] * code.nslots
        frees: tuple[Cell, ...] = ()
        ip = 0
        stack: list[object] = []
        push, pop = stack.append, stack.pop
        frames: list[tuple] = []  # saved callers: (code, local, frees, ip)
        globals_ = self.globals
        truthy = rt.truthy

        try:
            while True:
                op, arg = ops[ip]
                ip += 1

                # Ordered by how often each op runs: a Python if-chain pays
                # one comparison for every branch above the one it takes.
                if op == LOAD_LOCAL:
                    push(local[arg])
                elif op == LOAD_GLOBAL:
                    try:
                        push(globals_[consts[arg]])
                    except KeyError:
                        raise KiteRuntimeError(
                            f"undefined variable '{consts[arg]}'"
                        ) from None
                elif op == CONST:
                    push(consts[arg])
                elif ADD <= op <= NE:
                    b = pop()
                    a = stack[-1]
                    if type(a) is int and type(b) is int:  # fast path
                        if op == ADD:
                            stack[-1] = a + b
                            continue
                        if op == SUB:
                            stack[-1] = a - b
                            continue
                        if op == LT:
                            stack[-1] = a < b
                            continue
                    stack[-1] = rt.binary_op(OP_SYMBOLS[op], a, b)
                elif op == DEFINE_LOCAL:
                    local[arg] = pop()
                elif op == SET_GLOBAL:
                    name = consts[arg]
                    if name not in globals_:
                        raise KiteRuntimeError(f"undefined variable '{name}'")
                    globals_[name] = pop()
                elif op == JUMP_IF_FALSE:
                    v = pop()
                    if v is None or v is False:
                        ip = arg
                elif op == JUMP:
                    ip = arg
                elif op == POP:
                    pop()
                elif op == CALL:
                    callee = stack[-arg - 1]
                    if type(callee) is Closure:
                        fn = callee.code
                        rt.check_arity(fn.name, fn.arity, arg)
                        # frames holds every caller, the script included,
                        # so this allows the same depth as the interpreter.
                        if len(frames) >= rt.MAX_CALL_DEPTH:
                            raise KiteRuntimeError("stack overflow")
                        frames.append((code, local, frees, ip))
                        local = stack[len(stack) - arg:]
                        local.extend([None] * (fn.nslots - arg))
                        del stack[len(stack) - arg - 1:]
                        code, ops, consts = fn, fn.ops, fn.consts
                        frees = callee.frees
                        ip = 0
                    elif type(callee) is rt.Builtin:
                        args = stack[len(stack) - arg:]
                        result = rt.call_builtin(callee, args)
                        del stack[len(stack) - arg - 1:]
                        push(result)
                    else:
                        raise KiteRuntimeError("can only call functions")
                elif op == RETURN:
                    if not frames:
                        return pop()
                    code, local, frees, ip = frames.pop()
                    ops, consts = code.ops, code.consts
                elif op == STORE_LOCAL:
                    local[arg] = stack[-1]
                elif op == LOAD_CELL:
                    push(local[arg].value)
                elif op == STORE_CELL:
                    local[arg].value = stack[-1]
                elif op == MAKE_CELL:
                    local[arg] = Cell(pop())
                elif op == LOAD_FREE:
                    push(frees[arg].value)
                elif op == STORE_FREE:
                    frees[arg].value = stack[-1]
                elif op == NIL:
                    push(None)
                elif op == TRUE:
                    push(True)
                elif op == FALSE:
                    push(False)
                elif op == STORE_GLOBAL:
                    name = consts[arg]
                    if name not in globals_:
                        raise KiteRuntimeError(f"undefined variable '{name}'")
                    globals_[name] = stack[-1]
                elif op == DEFINE_GLOBAL:
                    globals_[consts[arg]] = pop()
                elif op == JUMP_IF_FALSE_OR_POP:
                    if truthy(stack[-1]):
                        pop()
                    else:
                        ip = arg
                elif op == JUMP_IF_TRUE_OR_POP:
                    if truthy(stack[-1]):
                        ip = arg
                    else:
                        pop()
                elif op == NEG:
                    stack[-1] = rt.unary_op("-", stack[-1])
                elif op == NOT:
                    stack[-1] = not truthy(stack[-1])
                elif op == MAKE_CLOSURE:
                    fn = consts[arg]
                    captured = tuple(
                        local[i] if kind == "cell" else frees[i]
                        for kind, i in fn.captures
                    )
                    push(Closure(fn, captured))
                elif op == BUILD_LIST:
                    items = stack[len(stack) - arg:]
                    del stack[len(stack) - arg:]
                    push(items)
                elif op == INDEX_GET:
                    index = pop()
                    stack[-1] = rt.index_get(stack[-1], index)
                elif op == INDEX_SET:
                    value = pop()
                    index = pop()
                    stack[-1] = rt.index_set(stack[-1], index, value)
                else:
                    raise RuntimeError(f"bad opcode {op}")
        except KiteRuntimeError as err:
            raise err.at(code.lines[ip - 1]) from None
