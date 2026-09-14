"""SwahiliPro compiler/interpreter public API.

SwahiliPro v2 uses brace-based blocks and lowercase, Swahili-first syntax while
retaining a compatibility translator for common v1 programs.
"""
try:
    from .compat_v2 import GLOBAL_ENV, make_global_env, migrate_legacy_syntax, run
except ImportError:
    from compat_v2 import GLOBAL_ENV, make_global_env, migrate_legacy_syntax, run

# Backward-compatible public name from the v1 interpreter.
global_symbol_table = GLOBAL_ENV

__all__ = [
    "GLOBAL_ENV",
    "global_symbol_table",
    "make_global_env",
    "migrate_legacy_syntax",
    "run",
]
