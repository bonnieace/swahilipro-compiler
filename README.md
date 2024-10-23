# Swahili Programming Language Documentation

## Table of Contents
- [1. Variables (Vigezo)](#1-variables-vigezo)
- [2. Arithmetic Operations (Operesheni za Hisabati)](#2-arithmetic-operations-operesheni-za-hisabati)
- [3. Control Structures (Miundo ya Kudhibiti)](#3-control-structures-miundo-ya-kudhibiti)
- [4. Functions (Njia)](#4-functions-njia)
- [5. Logical Operators (Operesheni za Mantiki)](#5-logical-operators-operesheni-za-mantiki)
- [6. Comparison Operators (Operesheni za Kulinganisha)](#6-comparison-operators-operesheni-za-kulinganisha)
- [7. Input and Output (Ingizo na Tokeo)](#7-input-and-output-ingizo-na-tokeo)
- [8. Exponentiation (Karisimu)](#8-exponentiation-karisimu)
- [9. Comments (Maelezo ya Pembeni)](#9-comments-maelezo-ya-pembeni)

## 1. Variables (Vigezo)

Variables are declared using the `var` keyword.

```swahili
var jina = "Habari"
var idadi = 10
```

### String Operations
```swahili
var salamu = "Habari" + " Dunia"
andika(salamu)  # Habari Dunia
```

### Number Operations
```swahili
var x = 5
var y = 10
var jumla = x + y
andika(jumla)  # 15
```

## 2. Arithmetic Operations (Operesheni za Hisabati)

| Operator | Description | Symbol |
|----------|-------------|---------|
| + | Addition | Ongeza |
| - | Subtraction | Toa |
| * | Multiplication | Mara |
| / | Division | Gawa |
| ^ | Exponentiation | Karisimu |

```swahili
var a = 5
var b = 2
var matokeo = a * b
print(matokeo)  # 10
```

## 3. Control Structures (Miundo ya Kudhibiti)

### If Statements (Ikiwa)
```swahili
ikiwa condition basi
    # Code block
ikiwa_nyingine
    # Else block
funga
```

### Else If (Au Ikiwa)
```swahili
ikiwa condition basi
    # First condition
au_ikiwa condition basi
    # Second condition
ikiwa_nyingine
    # Fallback
funga
```

### For Loops (Kwa)
```swahili
kwa var i = start hadi end basi
    # Loop body
funga
```

### While Loops (Wakati)
```swahili
wakati condition basi
    # Loop body
funga
```

## 4. Functions (Njia)

```swahili
njia function_name(parameters) basi
    # Function body
    rudisha value
funga
```

Example:
```swahili
njia ongeza(a, b) basi
    rudisha a + b
funga
```

## 5. Logical Operators (Operesheni za Mantiki)

- `na`: Logical AND
- `au`: Logical OR

```swahili
ikiwa a == 5 na b == 10 basi
    print("Zote ni kweli")
funga
```

## 6. Comparison Operators (Operesheni za Kulinganisha)

| Operator | Description | Symbol |
|----------|-------------|---------|
| == | Equal to | Ni Sawa |
| != | Not equal to | Si Sawa |
| < | Less than | Ndogo Zaidi |
| > | Greater than | Kubwa Zaidi |
| <= | Less than or equal to | Ndogo Zaidi au Sawa |
| >= | Greater than or equal to | Kubwa Zaidi au Sawa |

## 7. Input and Output (Ingizo na Tokeo)

### Output
```swahili
print("Habari Dunia")
```

### Input
```swahili
var jina = ingiza("Jina lako ni nani? ")
andika("Habari, " + jina)
```

## 8. Exponentiation (Karisimu)

```swahili
var matokeo = 2 ^ 3  # 2 to the power of 3
andika(matokeo)  # 8
```

## 9. Comments (Maelezo ya Pembeni)

Comments are created using the `#` symbol:

```swahili
# This is a comment
var nambari = 10  # This stores the number 10
```
