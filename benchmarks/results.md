Python 3.12.10 on Windows, median of 7 runs

| program | tree (s) | vm (s) | speed-up |
|---|---:|---:|---:|
| fib(25) | 0.800 | 0.359 | 2.2x |
| loop 1M | 1.731 | 1.415 | 1.2x |
| loop 1M, locals | 2.376 | 1.258 | 1.9x |
| closures 200k | 0.680 | 0.470 | 1.4x |
| list sort 300 | 0.088 | 0.088 | 1.0x |
| string concat 20k | 0.040 | 0.035 | 1.1x |
