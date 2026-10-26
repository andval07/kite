"""Tests for the command line front end."""

from kite.cli import main


def write(tmp_path, source):
    path = tmp_path / "prog.kite"
    path.write_text(source, encoding="utf-8")
    return str(path)


def test_run_prints_program_output(tmp_path, capsys):
    path = write(tmp_path, 'print("hi", 1 + 2);')

    code = main(["run", path])

    assert code == 0
    assert capsys.readouterr().out == "hi 3\n"


def test_run_with_tree_engine(tmp_path, capsys):
    path = write(tmp_path, "print(2 * 21);")

    assert main(["run", "--engine", "tree", path]) == 0
    assert capsys.readouterr().out == "42\n"


def test_runtime_error_goes_to_stderr_with_exit_code_1(tmp_path, capsys):
    path = write(tmp_path, "print(1);\nprint(1 / 0);")

    code = main(["run", path])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "1\n"
    assert captured.err == "runtime error at line 2: division by zero\n"


def test_missing_file_exits_with_2(tmp_path, capsys):
    code = main(["run", str(tmp_path / "nope.kite")])

    assert code == 2
    assert "cannot read" in capsys.readouterr().err


def test_dis_prints_bytecode(tmp_path, capsys):
    path = write(tmp_path, "fn f(a) { return a; }")

    assert main(["dis", path]) == 0
    out = capsys.readouterr().out
    assert "== <script> (arity 0, 0 slots) ==" in out
    assert "== f (arity 1, 1 slots) ==" in out


def test_dis_reports_syntax_errors(tmp_path, capsys):
    path = write(tmp_path, "let = 1;")

    assert main(["dis", path]) == 1
    assert "expected variable name" in capsys.readouterr().err


def test_repl_remembers_lines_and_survives_errors(monkeypatch, capsys):
    lines = iter(["let a = 2", "a / 0", "", "print(a * 3)"])

    def fake_input(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)

    assert main(["repl"]) == 0
    out = capsys.readouterr().out
    assert "runtime error at line 1: division by zero" in out
    assert "6\n" in out
