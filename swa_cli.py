"""Command-line interface for SwahiliPro.

Canonical usage:
    swa hello.swa
    swa
    swa repl
    swa --version
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

import swahilipro

VERSION = "2.0.0-dev"

BANNER_LINES = (
    "   ____  " + "  _    _ " + "   ____   " + "_      " + " _  " + " _    " + " _  ",
    " / ___|  " + " | |  | |" + "  / __ \\ " + "| |     " + "| | " + "| |   " + "| | ",
    "| |___   " + " | |  | |" + " / / _` |" + "| |___  " + "| | " + "| |   " + "| | ",
    " \\___ \\ " + " | |/\\| |" + "| | (_| |" + "|  __ | " + "| | " + "| |   " + "| | ",
    "  ___)|  " + " \\  /\\  /" + " \\ \\__,_|" + "| | | | " + "| | " + "| |__ " + "| | ",
    " |____/  " + "  \\/  \\/ " + "  \\____/ " + "|_| |_| " + "|_| " + "|____|" + "|_| ",
)

YELLOW = "\033[93m"
RESET = "\033[0m"


def _print_error(error) -> None:
    message = error.as_string() if hasattr(error, "as_string") else str(error)
    print(message, file=sys.stderr)


def _terminal_supports_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _print_banner() -> None:
    """Restore the original SwahiliPro shell identity for the canonical REPL."""
    use_color = _terminal_supports_color()
    prefix = YELLOW if use_color else ""
    suffix = RESET if use_color else ""
    animate = sys.stdout.isatty()

    for line in BANNER_LINES:
        print(f"{prefix}{line}{suffix}")
        if animate:
            time.sleep(0.06)


def execute_source(filename: str, source: str, *, echo_result: bool = False) -> int:
    result, error = swahilipro.run(filename, source)
    if error:
        _print_error(error)
        return 1
    if echo_result and result is not None:
        print(result)
    return 0


def run_file(filename: str) -> int:
    path = Path(filename).expanduser()
    if not path.exists():
        print(f"swa: faili halijapatikana: {filename}", file=sys.stderr)
        return 2
    if not path.is_file():
        print(f"swa: si faili: {filename}", file=sys.stderr)
        return 2

    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"swa: imeshindwa kusoma '{filename}': {exc}", file=sys.stderr)
        return 2

    return execute_source(str(path), source)


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


def repl() -> int:
    _print_banner()
    print(f"SwahiliPro {VERSION}")
    print("Andika 'toka' kuondoka. Ctrl+C husitisha mstari wa sasa.")

    buffer: list[str] = []
    depth = 0

    while True:
        prompt = "... " if buffer else "swa> "
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
            print("swa: '}' ya ziada imepatikana", file=sys.stderr)
            buffer.clear()
            depth = 0
            continue

        source = "\n".join(buffer).strip()
        buffer.clear()
        if not source:
            continue
        execute_source("<repl>", source, echo_result=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swa",
        description="SwahiliPro compiler and runtime",
        epilog="Mifano: swa hello.swa | swa | swa repl | swa --version",
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Faili la .swa la kuendesha. Tumia 'repl' kufungua REPL.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"SwahiliPro {VERSION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.target is None or args.target.lower() == "repl":
        return repl()
    return run_file(args.target)


if __name__ == "__main__":
    raise SystemExit(main())
