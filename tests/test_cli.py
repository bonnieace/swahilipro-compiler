from pathlib import Path

import pytest

import swa_cli


def test_swa_runs_file(tmp_path, capsys):
    source = tmp_path / "hello.swa"
    source.write_text('andika("Habari kutoka swa")\n', encoding="utf-8")

    code = swa_cli.main([str(source)])

    captured = capsys.readouterr()
    assert code == 0
    assert "Habari kutoka swa" in captured.out
    assert captured.err == ""


def test_swa_missing_file_returns_usage_error(capsys):
    code = swa_cli.main(["missing-file.swa"])

    captured = capsys.readouterr()
    assert code == 2
    assert "faili halijapatikana" in captured.err


def test_swa_version(capsys):
    with pytest.raises(SystemExit) as exc:
        swa_cli.main(["--version"])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert f"SwahiliPro {swa_cli.VERSION}" in captured.out


def test_brace_counter_ignores_strings_and_comments():
    assert swa_cli._brace_delta('ikiwa (kweli) { # }') == 1
    assert swa_cli._brace_delta('andika("{ sio block }")') == 0
    assert swa_cli._brace_delta("}") == -1
