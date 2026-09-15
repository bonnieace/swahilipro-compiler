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
    assert "swa: faili halijapatikana" in captured.err


def test_swahilipro_alias_uses_its_command_name(capsys):
    code = swa_cli.main(["missing-file.swa"], prog="swahilipro")

    captured = capsys.readouterr()
    assert code == 2
    assert "swahilipro: faili halijapatikana" in captured.err


@pytest.mark.parametrize("flag", ["-v", "--version"])
def test_version_flags(flag, capsys):
    with pytest.raises(SystemExit) as exc:
        swa_cli.main([flag])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert f"SwahiliPro {swa_cli.VERSION}" in captured.out


@pytest.mark.parametrize("flag", ["-h", "--help", "-help"])
def test_help_flags_show_branded_help(flag, capsys):
    with pytest.raises(SystemExit) as exc:
        swa_cli.main([flag], prog="swahilipro")

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "usage: swahilipro" in captured.out
    assert "#####" in captured.out


def test_check_valid_source_is_silent(tmp_path, capsys):
    source = tmp_path / "valid.swa"
    source.write_text('acha jina = "Amina"\nandika(jina)\n', encoding="utf-8")

    code = swa_cli.main(["check", str(source)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_check_accepts_if_else_if_sample_from_editor(tmp_path, capsys):
    source = tmp_path / "conditions.swa"
    source.write_text(
        "acha nchi = 'kenya'\n"
        "\n"
        "ikiwa (nchi == 'kenya'){\n"
        "    andika('one term')\n"
        "}\n"
        "au ikiwa (nchi !='kenya'){\n"
        "    andika('two term')\n"
        "}\n",
        encoding="utf-8",
    )

    code = swa_cli.main(["check", str(source)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_check_reports_source_line_and_pointer(tmp_path, capsys):
    source = tmp_path / "broken.swa"
    source.write_text('acha jina = "Amina"\n@\n', encoding="utf-8")

    code = swa_cli.main(["check", str(source)])

    captured = capsys.readouterr()
    assert code == 1
    assert "mstari 2" in captured.err
    assert "@" in captured.err
    assert "^" in captured.err


def test_banner_rows_are_fixed_width():
    lines = swa_cli._banner_lines()
    assert len(lines) == 7
    assert len({len(line) for line in lines}) == 1


def test_brace_counter_ignores_strings_and_comments():
    assert swa_cli._brace_delta('ikiwa (kweli) { # }') == 1
    assert swa_cli._brace_delta('andika("{ sio block }")') == 0
    assert swa_cli._brace_delta("}") == -1
