"""Legacy shell entrypoint.

The canonical CLI is now `swa`. Keeping this module lets older launchers continue
to open the same REPL without maintaining a second shell implementation.
"""
from swa_cli import repl


if __name__ == "__main__":
    raise SystemExit(repl())
