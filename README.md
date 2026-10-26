# kite

A small programming language in pure Python (standard library only), with
**two engines**: a tree-walking interpreter and a bytecode compiler with a stack
virtual machine.

Both engines share the lexer, the parser, a static resolver and the runtime
semantics. The test suite runs every program on both engines and checks that
the output and the error messages are identical.

```
fn counter() {
  let n = 0;
  return fn() { n = n + 1; return n; };
}

let next = counter();
next(); next();
print("count:", next());   // count: 3
```

## The language

- Values: `nil`, `true`/`false`, ints, floats, strings, lists, functions.
- `let` variables with block scope, `if` / `else if` / `else`, `while`.
- First-class functions, anonymous `fn(x) { ... }`, recursion, closures.
- Operators: `+ - * / %`, `< <= > >= == !=`, `and` / `or` (short-circuit),
  `not`, unary `-`, indexing `xs[i]` and `xs[i] = v`.
- Builtins: `print`, `len`, `push`, `str`, `clock`.
- Only `nil` and `false` are falsy. `+` on two strings joins them; mixing a
  string and a number is an error (no implicit conversion).
- Static errors (syntax, `return` outside a function, a variable declared twice
  in the same scope) are reported before anything runs.

Errors carry the source position:

```
error at line 2:16: invalid assignment target
runtime error at line 7: division by zero
```

## Usage

```bash
python -m venv .venv && .venv/bin/pip install -e .   # Windows: .venv\Scripts\pip
kite run examples/closures.kite            # bytecode VM (default)
kite run --engine tree examples/sort.kite  # tree-walking interpreter
kite dis examples/fizzbuzz.kite            # print the bytecode
kite                                       # REPL
```

`kite dis` output for `let x = 1; if x { print("hi"); }`:

```
== <script> (arity 0, 0 slots) ==
   1    0  CONST                0 (1)
   |    1  DEFINE_GLOBAL        1 (x)
   2    2  LOAD_GLOBAL          1 (x)
   |    3  JUMP_IF_FALSE        8 (to 8)
   |    4  LOAD_GLOBAL          2 (print)
   |    5  CONST                3 ("hi")
   |    6  CALL                 1
   |    7  POP
   |    8  NIL
   |    9  RETURN
```

## How it works

```
source --lexer--> tokens --parser--> AST --resolver--> scopes, slots, captures
                                                   |
                         +-------------------------+------------------------+
                         |                                                  |
                tree-walking interpreter                  compiler --> bytecode --> stack VM
                (walks the AST, env chain)                  (flat ops, locals in slots, cells)
```

- **Lexer** (`kite/lexer.py`): hand-written, tracks line and column for every
  token.
- **Parser** (`kite/parser.py`): recursive descent with one function per
  precedence level. Assignment is parsed as an expression and the target is
  checked afterwards, so `a[i] = v` and `a = b = 1` work.
- **Resolver** (`kite/resolver.py`): one pass over the AST before running.
  It finds static errors, and for every variable it works out where it lives:
  global, local slot, or captured by a closure. Both engines use this result,
  so they agree on scoping by construction.
- **Runtime** (`kite/runtime.py`): operators, equality, truthiness, printing
  and builtins live here once. Runtime errors are raised without a line; each
  engine adds the line of the node or instruction that failed. This is how the
  two engines give the same error messages.
- **Tree-walking interpreter** (`kite/interpreter.py`): evaluates AST nodes
  recursively, with an environment per block. Simple to read, slower to run.
- **Compiler** (`kite/compiler.py`): turns each function into a `Code` object
  with a flat list of `(opcode, arg)` pairs, a constant pool and a line table.
  Jumps are emitted with a placeholder and patched once the target is known.
  `x = v;` as a statement compiles to one fused store-and-pop instruction.
- **VM** (`kite/vm.py`): one operand stack for all calls, a frame per call with
  a locals array. Local variables are array slots, not dictionary lookups.
- **Closures**: the resolver marks which variables are captured. Only those
  are boxed in a `Cell`; everything else stays a plain slot. A closure stores
  the cells it needs. A captured variable declared inside a loop gets a new
  cell on every iteration, so each closure sees its own value (the classic
  JavaScript `var`-in-a-loop bug does not happen). Variables captured from two
  levels up are passed through the middle function.

## Benchmarks

`python benchmarks/bench.py --repeat 7` on my laptop (Python 3.12.10, Windows),
median wall time, engines run alternately:

| program | tree (s) | vm (s) | speed-up |
|---|---:|---:|---:|
| fib(25) | 0.800 | 0.359 | 2.2x |
| loop 1M | 1.731 | 1.415 | 1.2x |
| loop 1M, locals | 2.376 | 1.258 | 1.9x |
| closures 200k | 0.680 | 0.470 | 1.4x |
| list sort 300 | 0.088 | 0.088 | 1.0x |
| string concat 20k | 0.040 | 0.035 | 1.1x |

What the numbers say:

- The VM wins most on function calls (`fib`) and on code that uses local
  variables, because a call is a list slice instead of a new environment, and
  a local read is an array index instead of a walk up the scope chain.
- On code that works on global variables the gap is small: both engines do a
  dictionary lookup per access.
- The VM dispatches with a Python `if`/`elif` chain, ordered by how often each
  opcode runs. My first version had the global store near the bottom of the
  chain, and the global loop was slower on the VM than on the tree engine
  (0.9x). Reordering and the fused store-and-pop gave 1.2x.
- Both engines are interpreted by CPython, so neither is fast in absolute
  terms. The point is the comparison between the two designs.

## Tests

```bash
pip install pytest pytest-cov
pytest --cov=kite
```

128 tests, 98% line coverage:

- lexer and parser, including precedence written as s-expressions
- every end-to-end program and every example file, on both engines
- runtime errors on both engines: same message, same line, same output printed
  before the error
- static errors with exact line and column
- compiler internals: plain locals use slots, captured variables use cells,
  free variables pass through middle functions, disassembler output
- the REPL session and the command line

## Limits (on purpose)

- No classes, maps, `for` loops, `break` / `continue`, or modules.
- Recursion is limited to 1000 calls on both engines ("stack overflow").
- Lists compare by identity.

## Layout

```
kite/
  lexer.py        tokens with line and column
  parser.py       recursive descent -> AST (nodes.py)
  resolver.py     static scopes, slots, captured variables
  runtime.py      shared semantics and builtins
  interpreter.py  engine 1: tree-walking
  bytecode.py     opcodes, Code, Cell, Closure
  compiler.py     engine 2: AST -> bytecode
  vm.py           engine 2: stack VM
  disasm.py       bytecode listing
  runner.py       Session: parse, resolve, run on an engine
  cli.py          run / dis / REPL
examples/         sample programs
benchmarks/       bench.py and the last results
tests/            pytest suite
```
