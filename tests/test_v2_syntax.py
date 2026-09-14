import io
from contextlib import redirect_stdout

import swahilipro as swa
import compat_v2


def fresh_env():
    compat_v2.GLOBAL_ENV = compat_v2.make_global_env()
    swa.GLOBAL_ENV = compat_v2.GLOBAL_ENV


def execute(source):
    result, error = swa.run("<test>", source)
    assert error is None, error.as_string() if error else ""
    return result


def test_variables_and_assignment():
    fresh_env()
    execute('acha jina = "Amina"\nacha umri = 24\numri = 25')
    assert compat_v2.GLOBAL_ENV.get("jina") == "Amina"
    assert compat_v2.GLOBAL_ENV.get("umri") == 25


def test_full_and_arrow_functions():
    fresh_env()
    execute('''
jumlisha(a, b) => a + b
zidisha(a, b) {
    rudisha a * b
}
acha a = jumlisha(2, 3)
acha b = zidisha(4, 5)
''')
    assert compat_v2.GLOBAL_ENV.get("a") == 5
    assert compat_v2.GLOBAL_ENV.get("b") == 20


def test_if_else_if_else_with_parentheses():
    fresh_env()
    execute('''
acha umri = 17
ikiwa (umri >= 18) { acha kundi = "mtu mzima" }
au ikiwa (umri >= 13) { acha kundi = "kijana" }
vinginevyo { acha kundi = "mtoto" }
''')
    assert compat_v2.GLOBAL_ENV.get("kundi") == "kijana"


def test_ranges_iteration_and_indexing():
    fresh_env()
    execute('''
acha total = 0
kwa i katika 1..5 {
    total = total + i
}
acha majina = ["Amina", "Juma"]
ongeza(majina, "Neema")
acha pili = majina[1]
''')
    assert compat_v2.GLOBAL_ENV.get("total") == 10
    assert compat_v2.GLOBAL_ENV.get("majina") == ["Amina", "Juma", "Neema"]
    assert compat_v2.GLOBAL_ENV.get("pili") == "Juma"


def test_while_continue_break():
    fresh_env()
    execute('''
acha i = 0
acha total = 0
wakati (i < 6) {
    i = i + 1
    ikiwa (i == 2) { endelea }
    ikiwa (i == 5) { vunja }
    total = total + i
}
''')
    assert compat_v2.GLOBAL_ENV.get("total") == 8


def test_legacy_v1_translation():
    fresh_env()
    execute('''
VAR x = 2
NJIA ongeza(a, b) -> a + b
IKIWA x == 2 BASI
    VAR y = ongeza(x, 3)
IKIWA_NYINGINE
    VAR y = 0
FUNGA
''')
    assert compat_v2.GLOBAL_ENV.get("y") == 5


def test_lowercase_boolean_words_and_print():
    fresh_env()
    output = io.StringIO()
    with redirect_stdout(output):
        execute('ikiwa (kweli na sio uongo) { andika("sawa") }')
    assert output.getvalue().strip() == "sawa"
