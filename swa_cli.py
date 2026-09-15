"""Command-line interface for SwahiliPro.

Canonical usage:
    swa hello.swa
    swa
    swa repl
    swa -v
    swa -help

The `swahilipro` command is an equivalent alias for `swa`.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

import swahilipro

VERSION = "2.0.0-dev"

BANNER_WORD = "SWAHILIPRO"
BANNER_GLYPHS = {
    "S": ("#####", "#    ", "#    ", "#####", "    #", "    #", "#####"),
    "W": ("#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "R": ("#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
}

YELLOW = "\033[93m"
RESET = "\033[0m"
HELP_FLAGS = {"-h", "--help", "-help"}
COMMAND_NAMES = {"swa", "swahilipro"}


def _command_name() -> str:
    name = Path(sys.argv[0]).stem.lower()
    return name if name in COMMAND_NAMES else "swa"


def _banner_lines() -> tuple[str, ...]:
    rows = len(BANNER_GLYPHS["S"])
    return tuple(
        "  ".join(BANNER_GLYPHS[letter][row] for letter in BANNER_WORD)
        for row in range(rows)
    )


def _print_error(error) -> None:
    message = error.as_string() if hasattr(error, "as_string") else str(error)
    print(message, file=sys.stderr)


def _terminal_supports_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _print_banner(*, animate: bool | None = None) -> None:
    """Print a fixed-width SwahiliPro banner without the old alignment drift."""
    use_color = _terminal_supports_color()
    prefix = YELLOW if use_color else ""
    suffix = RESET if use_color else ""
    should_animate = sys.stdout.isatty() if animate is None else animate

    for line in _banner_lines():
        print(f"{prefix}{line}{suffix}")
        if should_animate:
            time.sleep(0.045)


def execute_source(filename: str, source: str, *, echo_result: bool = False) -> int:
    result, error = swahilipro.run(filename, source)
    if error:
        _print_error(error)
        return 1
    if echo_result and result is not None:
        print(result)
    return 0


def check_source(filename: str, source: str) -> int:
    error = swahilipro.check(filename, source)
    if error:
        _print_error(error)
        return 1
    return 0


def _read_source(filename: str, *, command: str) -> tuple[str | None, str | None]:
    if filename == "-":
        return "<stdin>", sys.stdin.read()

    path = Path(filename).expanduser()
    if not path.exists():
        print(f"{command}: faili halijapatikana: {filename}", file=sys.stderr)
        return None, None
    if not path.is_file():
        print(f"{command}: si faili: {filename}", file=sys.stderr)
        return None, None

    try:
        return str(path), path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{command}: imeshindwa kusoma '{filename}': {exc}", file=sys.stderr)
        return None, None


def run_file(filename: str, *, command: str | None = None) -> int:
    command = command or _command_name()
    resolved, source = _read_source(filename, command=command)
    if resolved is None or source is None:
        return 2
    return execute_source(resolved, source)


def check_file(filename: str, *, command: str | None = None) -> int:
    command = command or _command_name()
    resolved, source = _read_source(filename, command=command)
    if resolved is None or source is None:
        return 2
    return check_source(resolved, source)


def _brace_delta(line: str) -> int:
    """Count block braces while ignoring quoted strings and # comments."""
    delta = 0
    quote = None
    escaped = False

    for char in line:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote is not None:
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
            continue
        if char == "#":
            break
        if char == "{":
            delta += 1
        elif char == "}":
            delta -= 1

    return delta


def repl(*, command: str | None = None) -> int:
    command = command or _command_name()
    _print_banner()
    print(f"SwahiliPro {VERSION}")
    print("Andika 'toka' kuondoka. Ctrl+C husitisha mstari wa sasa.")

    buffer: list[str] = []
    depth = 0

    while True:
        prompt = "... " if buffer else f"{command}> "
        try:
            line = input(prompt)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            buffer.clear()
            depth = 0
            continue

        if not buffer and line.strip().lower() in {"toka", "exit", "quit"}:
            return 0

        buffer.append(line)
        depth += _brace_delta(line)

        if depth > 0:
            continue
        if depth < 0:
            print(f"{command}: '}}' ya ziada imepatikana", file=sys.stderr)
            buffer.clear()
            depth = 0
            continue

        source = "\n".join(buffer).strip()
        buffer.clear()
        if not source:
            continue
        execute_source("<repl>", source, echo_result=True)


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    command = prog or _command_name()
    parser = argparse.ArgumentParser(
        prog=command,
        add_help=False,
        description="SwahiliPro compiler and runtime",
        epilog=(
            f"Mifano: {command} hello.swa | {command} | {command} repl | "
            f"{command} -v | {command} -help | {command} check hello.swa"
        ),
    )
    parser.add_argument(
        "-h",
        "--help",
        "-help",
        action="help",
        help="Onyesha msaada huu na utoke.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"SwahiliPro {VERSION}",
        help="Onyesha toleo la SwahiliPro na utoke.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Faili la .swa la kuendesha. Tumia 'repl' kufungua REPL.",
    )
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    command = prog or _command_name()
    arguments = list(sys.argv[1:] if argv is None else argv)

    if any(flag in HELP_FLAGS for flag in arguments):
        _print_banner(animate=False)

    if arguments and arguments[0].lower() == "check":
        if len(arguments) != 2:
            print(f"Tumia: {command} check <faili.swa|->", file=sys.stderr)
            return 2
        return check_file(arguments[1], command=command)

    args = build_parser(prog=command).parse_args(arguments)
    if args.target is None or args.target.lower() == "repl":
        return repl(command=command)
    return run_file(args.target, command=command)


if __name__ == "__main__":
    raise SystemExit(main())
