import math
import os
import re

try:
    from .syntax_v2 import Lexer, Parser, SwahiliProError, RuntimeErrorSwa
    from .environment_v2 import Environment, ReturnSignal, BreakSignal, ContinueSignal
    from .interpreter_v2 import Interpreter
except ImportError:
    from syntax_v2 import Lexer, Parser, SwahiliProError, RuntimeErrorSwa
    from environment_v2 import Environment, ReturnSignal, BreakSignal, ContinueSignal
    from interpreter_v2 import Interpreter


def _andika(*values):
    print(*values)
    return None


def _andika_mstari_mpya(value):
    return str(value)


def _futa():
    os.system("cls" if os.name == "nt" else "clear")
    return None


def _endesha(fn):
    if not isinstance(fn, str):
        raise TypeError("endesha inahitaji jina la faili")
    with open(fn, "r", encoding="utf-8") as handle:
        source = handle.read()
    _, error = run(fn, source)
    if error:
        raise error
    return None


def _ingiza(prompt=""):
    return input(prompt)


def _ingiza_namba(prompt=""):
    raw = input(prompt)
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"'{raw}' si namba")


def _urefu(value):
    return len(value)


def _ongeza(orodha, value):
    if not isinstance(orodha, list):
        raise TypeError("argument ya kwanza ya ongeza lazima iwe orodha")
    orodha.append(value)
    return None


def _ondoa(orodha, index):
    if not isinstance(orodha, list):
        raise TypeError("argument ya kwanza ya ondoa lazima iwe orodha")
    return orodha.pop(index)


def _extend(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        raise TypeError("extend inahitaji orodha mbili")
    a.extend(b)
    return None


def make_global_env():
    env = Environment()
    values = {
        "kweli": True, "uongo": False, "PI": math.pi,
        "andika": _andika, "andika_mstari_mpya": _andika_mstari_mpya,
        "ingiza": _ingiza, "ingiza_namba": _ingiza_namba, "futa": _futa, "endesha": _endesha,
        "urefu": _urefu, "ongeza": _ongeza, "ondoa": _ondoa, "extend": _extend,
        "ni_namba": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "ni_neno": lambda v: isinstance(v, str),
        "ni_orodha": lambda v: isinstance(v, list),
        "ni_function": callable,
    }
    for name, value in values.items():
        env.declare(name, value)

    aliases = {
        "KWELI": True, "UONGO": False,
        "ANDIKA": _andika, "print": _andika, "ANDIKA_MSTARI_MPYA": _andika_mstari_mpya,
        "BONYEZA": _ingiza, "BONYEZA_NAM": _ingiza_namba, "FUTA": _futa, "CLS": _futa,
        "swa": _endesha,
        "UREFU": _urefu, "UNGANISHA": _ongeza, "POP": _ondoa, "EXTEND": _extend,
        "NI_NAMBARI": values["ni_namba"], "NI_NENO": values["ni_neno"],
        "NI_ORODHA": values["ni_orodha"], "NI_NJIA": values["ni_function"],
    }
    for name, value in aliases.items():
        env.declare(name, value)
    return env


def migrate_legacy_syntax(text):
    """Translate common v1 syntax into the brace-based v2 grammar."""
    out = []
    for raw_line in text.splitlines():
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        s = raw_line.strip()
        if not s:
            out.append(raw_line)
            continue

        s = re.sub(r"^VAR\b", "acha", s, flags=re.I)

        match = re.match(r"^NJIA\s+([A-Za-z_]\w*\s*\([^)]*\))\s*(?:BASI)?\s*->\s*(.+)$", s, re.I)
        if match:
            out.append(indent + f"{match.group(1)} => {match.group(2)}")
            continue
        match = re.match(r"^NJIA\s+([A-Za-z_]\w*\s*\([^)]*\))\s*(?:BASI)?\s*$", s, re.I)
        if match:
            out.append(indent + f"{match.group(1)} {{")
            continue

        match = re.match(r"^AU_IKIWA\s+(.+?)\s+BASI\s*$", s, re.I)
        if match:
            out.append(indent + f"}} au ikiwa ({match.group(1)}) {{")
            continue
        if re.match(r"^IKIWA_NYINGINE\s*$", s, re.I):
            out.append(indent + "} vinginevyo {")
            continue
        match = re.match(r"^IKIWA\s+(.+?)\s+BASI\s*$", s, re.I)
        if match:
            out.append(indent + f"ikiwa ({match.group(1)}) {{")
            continue

        match = re.match(r"^WAKATI\s+(.+?)\s+BASI\s*$", s, re.I)
        if match:
            out.append(indent + f"wakati ({match.group(1)}) {{")
            continue
        match = re.match(
            r"^KWA\s+(?:VAR\s+)?([A-Za-z_]\w*)\s*=\s*(.+?)\s+HADI\s+(.+?)(?:\s+STEP\s+(.+?))?\s+BASI\s*$",
            s, re.I
        )
        if match:
            range_expr = f"{match.group(2)}..{match.group(3)}"
            if match.group(4):
                range_expr += f"..{match.group(4)}"
            out.append(indent + f"kwa {match.group(1)} katika {range_expr} {{")
            continue

        if re.match(r"^FUNGA\s*$", s, re.I):
            out.append(indent + "}")
            continue

        out.append(indent + s)
    return "\n".join(out)


GLOBAL_ENV = make_global_env()


def run(fn, text):
    source = migrate_legacy_syntax(text)
    try:
        tokens = Lexer(fn, source).make_tokens()
        ast = Parser(fn, source, tokens).parse()
        interpreter = Interpreter(fn, source)
        result = interpreter.execute_program(ast, GLOBAL_ENV)
        return result, None
    except SwahiliProError as error:
        return None, error
    except (ReturnSignal, BreakSignal, ContinueSignal):
        error = RuntimeErrorSwa(fn, source, 0, 0, "Kosa la utekelezaji", "Kauli hii imetumika nje ya sehemu yake")
        return None, error
    except Exception as exc:
        error = RuntimeErrorSwa(fn, source, 0, 0, "Kosa la utekelezaji", str(exc))
        return None, error
