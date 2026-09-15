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


def _run_check(tmp_path, capsys, text, name="diagnostic.swa"):
    source = tmp_path / name
    source.write_text(text, encoding="utf-8")
    code = swa_cli.main(["check", str(source)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _pointer_column(stderr):
    return stderr.rstrip().splitlines()[-1].index("^")


def test_check_valid_source_is_silent(tmp_path, capsys):
    code, stdout, stderr = _run_check(
        tmp_path,
        capsys,
        'acha jina = "Amina"\nandika(jina)\n',
    )

    assert code == 0
    assert stdout == ""
    assert stderr == ""


def test_check_accepts_if_else_if_sample_from_editor(tmp_path, capsys):
    code, stdout, stderr = _run_check(
        tmp_path,
        capsys,
        "acha nchi = 'kenya'\n"
        "\n"
        "ikiwa (nchi == 'kenya'){\n"
        "    andika('one term')\n"
        "}\n"
        "au ikiwa (nchi !='kenya'){\n"
        "    andika('two term')\n"
        "}\n",
        "conditions.swa",
    )

    assert code == 0
    assert stdout == ""
    assert stderr == ""


@pytest.mark.parametrize(
    ("text", "line_number", "column", "detail"),
    [
        (
            "acha nchi = 'kenya'\n\nikiwa (nchi == 'kenya){\n    andika('one term')\n}\n",
            3,
            15,
            "Neno halijafungwa",
        ),
        ('acha ujumbe = "habari\n', 1, 14, "Neno halijafungwa"),
        ("acha x = [1, 2\n", 1, 9, "haijafungwa"),
        ("andika('x'\n", 1, 6, "haijafungwa"),
        ("ikiwa (kweli) {\n    andika('x')\n", 1, 14, "haijafungwa"),
        ("acha x = (1 + 2\n", 1, 9, "haijafungwa"),
        ("acha x = [1, 2)\n", 1, 14, "haifanani"),
        ("acha x = 1 @ 2\n", 1, 11, "haitambuliki"),
    ],
)
def test_check_reports_structural_errors_at_the_causal_character(
    tmp_path, capsys, text, line_number, column, detail
):
    code, _, stderr = _run_check(tmp_path, capsys, text)

    assert code == 1
    assert f"mstari {line_number}" in stderr
    assert detail in stderr
    assert _pointer_column(stderr) == column


def test_check_missing_equals_points_to_the_unexpected_value(tmp_path, capsys):
    code, _, stderr = _run_check(tmp_path, capsys, "acha nchi 'kenya'\n")

    assert code == 1
    assert "Tumia '='" in stderr
    assert "mstari 1" in stderr
    assert _pointer_column(stderr) == 10


def test_structure_scan_ignores_delimiters_inside_strings_and_comments(tmp_path, capsys):
    code, stdout, stderr = _run_check(
        tmp_path,
        capsys,
        "acha ujumbe = '{[( bado ni maandishi )]}'\n"
        "# } ] ) hizi ni comment tu\n"
        "andika(ujumbe)\n",
    )

    assert code == 0
    assert stdout == ""
    assert stderr == ""


def test_check_preserves_v2_source_with_trailing_whitespace(tmp_path, capsys):
    line = "acha x = 1 @ 2   "
    code, _, stderr = _run_check(tmp_path, capsys, line + "\n")

    assert code == 1
    assert line in stderr
    assert _pointer_column(stderr) == 11


def test_check_reports_source_line_and_pointer(tmp_path, capsys):
    code, _, stderr = _run_check(
        tmp_path,
        capsys,
        'acha jina = "Amina"\n@\n',
        "broken.swa",
    )

    assert code == 1
    assert "mstari 2" in stderr
    assert "@" in stderr
    assert "^" in stderr


def test_banner_rows_are_fixed_width():
    lines = swa_cli._banner_lines()
    assert len(lines) == 7
    assert len({len(line) for line in lines}) == 1


def test_brace_counter_ignores_strings_and_comments():
    assert swa_cli._brace_delta('ikiwa (kweli) { # }') == 1
    assert swa_cli._brace_delta('andika("{ sio block }")') == 0
    assert swa_cli._brace_delta("}") == -1
