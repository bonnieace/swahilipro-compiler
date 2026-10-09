# SwahiliPro

SwahiliPro is a Swahili-first programming language designed to feel familiar to people who have seen modern languages while keeping readable language constructs in Swahili.

This branch introduces the **SwahiliPro v2 syntax**. The main design rule is simple:

> Keep universal programming structure familiar; use Swahili for the human-readable parts.

## CLI

The canonical command is `swa`.

```bash
swa hello.swa
swa
swa repl
swa --version
swa --help
```

- `swa hello.swa` runs a SwahiliPro source file.
- `swa` opens the interactive REPL.
- `swa repl` explicitly opens the REPL.
- `swa --version` prints the installed SwahiliPro version.

The release pipeline builds standalone Windows, macOS and Linux binaries with PyInstaller. End users therefore do **not** need Python or pip installed to run the CLI.

## Quick example

```swahili
mraba(x) => x * x

wastani(a, b, c) {
    acha jumla = a + b + c
    rudisha jumla / 3
}

acha jina = "Amina"
acha umri = 17

ikiwa (umri >= 18) {
    andika(jina + ": mtu mzima")
}
au ikiwa (umri >= 13) {
    andika(jina + ": kijana")
}
vinginevyo {
    andika(jina + ": mtoto")
}

kwa i katika 1..5 {
    andika(mraba(i))
}
```

## Variables

Declare a variable with `acha`:

```swahili
acha jina = "Amina"
acha umri = 24
acha bei = 150
```

After declaration, assign normally:

```swahili
umri = 25
```

## Functions

SwahiliPro v2 does not require a function-definition keyword.

### Block function

```swahili
jumlisha(a, b) {
    rudisha a + b
}
```

### Expression function

```swahili
jumlisha(a, b) => a + b
```

Calling a function remains conventional:

```swahili
acha jibu = jumlisha(5, 10)
```

## Conditions

Canonical v2 style uses parentheses around conditions and braces around blocks:

```swahili
ikiwa (alama >= 80) {
    andika("Bora")
}
au ikiwa (alama >= 70) {
    andika("Vizuri")
}
vinginevyo {
    andika("Endelea kujitahidi")
}
```

Single-line blocks are valid:

```swahili
ikiwa (umri >= 18) { andika("Mtu mzima") }
```

## Boolean logic

```swahili
kweli
uongo
na
au
sio
```

Example:

```swahili
ikiwa (ana_kitambulisho na sio amezuiwa) {
    andika("Ruhusiwa")
}
```

## Loops

### Iterate over a collection

```swahili
acha majina = ["Amina", "Juma", "Neema"]

kwa jina katika majina {
    andika(jina)
}
```

### Ranges

```swahili
kwa i katika 1..5 {
    andika(i)
}
```

`1..5` follows the existing SwahiliPro loop behavior: the start is included and the end is excluded, so it produces `1, 2, 3, 4`.

A stepped range is also supported:

```swahili
kwa i katika 0..10..2 {
    andika(i)
}
```

### While

```swahili
wakati (salio > 0) {
    salio = salio - 1
}
```

### Loop control

```swahili
kwa i katika 1..100 {
    ikiwa (i == 5) { endelea }
    ikiwa (i == 20) { vunja }
    andika(i)
}
```

## Lists

Lists now use conventional indexing:

```swahili
acha majina = ["Amina", "Juma", "Neema"]

andika(majina[0])
ongeza(majina, "Bonnie")
ondoa(majina, 1)
andika(urefu(majina))
```

Nested indexing works as expected:

```swahili
acha wanafunzi = [
    ["Amina", 20],
    ["Juma", 22]
]

andika(wanafunzi[0][0])
```

Arithmetic symbols retain their normal meanings. List operations should use explicit built-ins instead of overloading `/`, `-`, or `*` with list-specific behavior.

## Core built-ins

| Function | Purpose |
|---|---|
| `andika(value)` | Print output |
| `ingiza(prompt)` | Read text input |
| `ingiza_namba(prompt)` | Read numeric input |
| `urefu(value)` | Get length |
| `ongeza(orodha, value)` | Append to a list |
| `ondoa(orodha, index)` | Remove and return a list item |
| `ni_namba(value)` | Check for a number |
| `ni_neno(value)` | Check for a string |
| `ni_orodha(value)` | Check for a list |
| `ni_function(value)` | Check whether a value is callable |
| `endesha(file)` | Run a SwahiliPro source file |

## Operators

SwahiliPro keeps familiar programming operators:

```text
+  -  *  /  ^
== != < > <= >=
=  ( ) [ ] { } ,
```

Comments continue to use `#`:

```swahili
# Hii ni comment
acha bei = 150
```

## v1 compatibility

The v2 runtime includes a migration layer for common v1 programs. Existing forms such as these remain accepted during the migration window:

```text
VAR
NJIA
IKIWA ... BASI
AU_IKIWA
IKIWA_NYINGINE
WAKATI ... BASI
KWA ... HADI ... BASI
FUNGA
```

The canonical syntax for all new code is lowercase v2 syntax.

| v1 | v2 |
|---|---|
| `VAR jina = ...` | `acha jina = ...` |
| `NJIA ongeza(a,b) -> ...` | `ongeza(a,b) => ...` |
| `NJIA ongeza(a,b) ... FUNGA` | `ongeza(a,b) { ... }` |
| `IKIWA x BASI ... FUNGA` | `ikiwa (x) { ... }` |
| `AU_IKIWA` | `au ikiwa` |
| `IKIWA_NYINGINE` | `vinginevyo` |
| `WAKATI x BASI` | `wakati (x) {` |
| `KWA i = 0 HADI 10 BASI` | `kwa i katika 0..10 {` |
| `CONTINUE` | `endelea` |
| `FUNGA` | `}` |

Legacy runtime names including `ANDIKA`, `BONYEZA`, `UREFU`, `UNGANISHA`, `POP`, `KWELI`, and `UONGO` are also retained as temporary aliases.

## Distribution direction

The standalone `swa` binary is the shared runtime artifact for the CLI and editor integrations. The VS Code extension should bundle the matching platform binary, while pip remains an optional developer/legacy channel rather than an end-user requirement.

## Design direction

SwahiliPro v2 intentionally avoids translating punctuation or inventing Swahili replacements for concepts programmers already recognize. The language should require as little explanation as possible while still reading naturally in Swahili.


## Account and AI chat preview

The optional CLI account/chat integration is documented in
[CLI accounts and text chat](docs/cli-accounts.md). It requires the companion
Next.js backend and an OS keychain. Existing SwahiliPro execution and syntax checks
remain offline. Start with `swa configure --api-origin https://YOUR-DEPLOYED-HOST`,
then `swa login`, `swa models`, and `swa chat --model MODEL_ID`.
