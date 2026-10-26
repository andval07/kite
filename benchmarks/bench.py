"""Times the same Kite programs on both engines and prints a Markdown table.

    python benchmarks/bench.py [--repeat N]

Each program runs N times per engine, alternating tree and vm; the table
shows the median wall time.
Output is thrown away so printing does not affect the numbers.
"""

from __future__ import annotations

import argparse
import io
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kite import run  # noqa: E402

PROGRAMS = {
    "fib(25)": """
        fn fib(n) { if n < 2 { return n; } return fib(n - 1) + fib(n - 2); }
        print(fib(25));
    """,
    "loop 1M": """
        let i = 0; let total = 0;
        while i < 1000000 { total = total + i; i = i + 1; }
        print(total);
    """,
    "loop 1M, locals": """
        fn sum(n) {
          let i = 0; let total = 0;
          while i < n { total = total + i; i = i + 1; }
          return total;
        }
        print(sum(1000000));
    """,
    "closures 200k": """
        fn make_adder(k) { return fn(x) { return x + k; }; }
        let add = make_adder(3);
        let i = 0; let total = 0;
        while i < 200000 { total = add(total); i = i + 1; }
        print(total);
    """,
    "list sort 300": """
        let xs = []; let i = 0;
        while i < 300 { push(xs, (i * 7919) % 300); i = i + 1; }
        let a = 1;
        while a < len(xs) {
          let x = xs[a]; let j = a - 1;
          while j >= 0 and x < xs[j] { xs[j + 1] = xs[j]; j = j - 1; }
          xs[j + 1] = x;
          a = a + 1;
        }
        print(xs[0], xs[299]);
    """,
    "string concat 20k": """
        let s = ""; let i = 0;
        while i < 20000 { s = s + "x"; i = i + 1; }
        print(len(s));
    """,
}


def time_once(source: str, engine: str) -> float:
    start = time.perf_counter()
    run(source, engine=engine, out=io.StringIO())
    return time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    repeat = parser.parse_args().repeat

    print(f"Python {platform.python_version()} on {platform.system()}, "
          f"median of {repeat} runs\n")
    print("| program | tree (s) | vm (s) | speed-up |")
    print("|---|---:|---:|---:|")
    for name, source in PROGRAMS.items():
        times: dict[str, list[float]] = {"tree": [], "vm": []}
        for _ in range(repeat):
            # Alternate the engines so a busy machine slows both alike.
            for engine in times:
                times[engine].append(time_once(source, engine))
        medians = {engine: statistics.median(t) for engine, t in times.items()}
        print(f"| {name} | {medians['tree']:.3f} | {medians['vm']:.3f} "
              f"| {medians['tree'] / medians['vm']:.1f}x |")


if __name__ == "__main__":
    main()
