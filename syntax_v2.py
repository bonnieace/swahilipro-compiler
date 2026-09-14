from dataclasses import dataclass


# -----------------------------
# Errors
# -----------------------------
class SwahiliProError(Exception):
    def __init__(self, fn, text, line, col, name, details):
        super().__init__(details)
        self.fn = fn
        self.text = text
        self.line = line
        self.col = col
        self.error_name = name
        self.details = details

    def as_string(self):
        lines = self.text.splitlines() or [""]
        source = lines[self.line] if 0 <= self.line < len(lines) else ""
        pointer = " " * max(self.col, 0) + "^"
        return (
            f"{self.error_name}: {self.details}\n"
            f"Faili {self.fn}, mstari {self.line + 1}\n\n"
            f"{source}\n{pointer}"
        )


class ParseError(SwahiliProError):
    pass


class RuntimeErrorSwa(SwahiliProError):
    pass


# -----------------------------
# Lexer
# -----------------------------
@dataclass
class Token:
    type: str
    value: object = None
    line: int = 0
    col: int = 0

    def __repr__(self):
        return f"{self.type}:{self.value}" if self.value is not None else self.type


KEYWORDS = {
    "acha", "na", "au", "ikiwa", "vinginevyo", "kwa", "katika",
    "wakati", "rudisha", "vunja", "endelea", "sio", "kweli", "uongo",
}

KEYWORD_ALIASES = {
    "var": "acha",
    "ikiwa_nyingine": "vinginevyo",
    "continue": "endelea",
    "not": "sio",
}


class Lexer:
    def __init__(self, fn, text):
        self.fn = fn
        self.text = text
        self.i = 0
        self.line = 0
        self.col = 0

    def current(self):
        return self.text[self.i] if self.i < len(self.text) else None

    def peek(self, n=1):
        j = self.i + n
        return self.text[j] if j < len(self.text) else None

    def advance(self):
        ch = self.current()
        if ch is None:
            return
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 0
        else:
            self.col += 1

    def token(self, type_, value=None, line=None, col=None):
        return Token(type_, value, self.line if line is None else line, self.col if col is None else col)

    def make_tokens(self):
        tokens = []
        while self.current() is not None:
            ch = self.current()
            if ch in " \t\r":
                self.advance()
                continue
            if ch == "#":
                while self.current() not in (None, "\n"):
                    self.advance()
                continue
            if ch in "\n;":
                tokens.append(self.token("NEWLINE"))
                self.advance()
                continue
            if ch.isdigit():
                tokens.append(self.make_number())
                continue
            if ch.isalpha() or ch == "_":
                tokens.append(self.make_identifier())
                continue
            if ch in ('"', "'"):
                tokens.append(self.make_string())
                continue

            line, col = self.line, self.col
            two = (ch or "") + (self.peek() or "")
            if two == "=>":
                tokens.append(Token("ARROW", "=>", line, col)); self.advance(); self.advance(); continue
            if two == "->":
                tokens.append(Token("ARROW", "->", line, col)); self.advance(); self.advance(); continue
            if two == "==":
                tokens.append(Token("EQEQ", "==", line, col)); self.advance(); self.advance(); continue
            if two == "!=":
                tokens.append(Token("NE", "!=", line, col)); self.advance(); self.advance(); continue
            if two == "<=":
                tokens.append(Token("LTE", "<=", line, col)); self.advance(); self.advance(); continue
            if two == ">=":
                tokens.append(Token("GTE", ">=", line, col)); self.advance(); self.advance(); continue
            if two == "..":
                tokens.append(Token("RANGE", "..", line, col)); self.advance(); self.advance(); continue

            singles = {
                "+": "PLUS", "-": "MINUS", "*": "MUL", "/": "DIV", "^": "POW",
                "=": "EQ", "<": "LT", ">": "GT", "(": "LPAREN", ")": "RPAREN",
                "{": "LBRACE", "}": "RBRACE", "[": "LBRACKET", "]": "RBRACKET",
                ",": "COMMA",
            }
            if ch in singles:
                tokens.append(Token(singles[ch], ch, line, col))
                self.advance()
                continue

            raise ParseError(self.fn, self.text, line, col, "Sintaksia isiokubalika", f"Alama '{ch}' haitambuliki")

        tokens.append(Token("EOF", None, self.line, self.col))
        return tokens

    def make_number(self):
        line, col = self.line, self.col
        buf = []
        dot_seen = False
        while self.current() is not None:
            ch = self.current()
            if ch.isdigit():
                buf.append(ch); self.advance(); continue
            if ch == "." and self.peek() != "." and not dot_seen:
                dot_seen = True; buf.append(ch); self.advance(); continue
            break
        raw = "".join(buf)
        return Token("NUMBER", float(raw) if dot_seen else int(raw), line, col)

    def make_identifier(self):
        line, col = self.line, self.col
        buf = []
        while self.current() is not None and (self.current().isalnum() or self.current() == "_"):
            buf.append(self.current()); self.advance()
        raw = "".join(buf)
        lowered = raw.lower()
        lowered = KEYWORD_ALIASES.get(lowered, lowered)
        if lowered in KEYWORDS:
            return Token("KEYWORD", lowered, line, col)
        return Token("IDENT", raw, line, col)

    def make_string(self):
        line, col = self.line, self.col
        quote = self.current()
        self.advance()
        buf = []
        escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}
        while self.current() is not None and self.current() != quote:
            if self.current() == "\\":
                self.advance()
                if self.current() is None:
                    break
                buf.append(escapes.get(self.current(), self.current()))
                self.advance()
            else:
                buf.append(self.current())
                self.advance()
        if self.current() != quote:
            raise ParseError(self.fn, self.text, line, col, "Sintaksia isiokubalika", "Neno halijafungwa")
        self.advance()
        return Token("STRING", "".join(buf), line, col)


# -----------------------------
# AST
# -----------------------------
@dataclass
class Program: statements: list
@dataclass
class NumberNode: value: object
@dataclass
class StringNode: value: str
@dataclass
class BoolNode: value: bool
@dataclass
class ListNode: elements: list
@dataclass
class VarNode: name: str
@dataclass
class VarDeclNode: name: str; value: object
@dataclass
class AssignNode: name: str; value: object
@dataclass
class BinaryNode: left: object; op: str; right: object
@dataclass
class UnaryNode: op: str; value: object
@dataclass
class CallNode: callee: object; args: list
@dataclass
class IndexNode: target: object; index: object
@dataclass
class FunctionDefNode: name: str; params: list; body: object; expression_body: bool = False
@dataclass
class ReturnNode: value: object
@dataclass
class IfNode: cases: list; else_body: object = None
@dataclass
class WhileNode: condition: object; body: object
@dataclass
class ForNode: name: str; iterable: object; body: object
@dataclass
class BreakNode: pass
@dataclass
class ContinueNode: pass
@dataclass
class RangeNode: start: object; end: object; step: object = None


# -----------------------------
# Parser
# -----------------------------
class Parser:
    def __init__(self, fn, text, tokens):
        self.fn = fn
        self.text = text
        self.tokens = tokens
        self.i = 0

    @property
    def tok(self):
        return self.tokens[self.i]

    def peek(self, n=1):
        j = min(self.i + n, len(self.tokens) - 1)
        return self.tokens[j]

    def advance(self):
        t = self.tok
        if self.i < len(self.tokens) - 1:
            self.i += 1
        return t

    def error(self, tok, details):
        raise ParseError(self.fn, self.text, tok.line, tok.col, "Sintaksia isiokubalika", details)

    def match(self, type_, value=None):
        if self.tok.type != type_:
            return False
        if value is not None and self.tok.value != value:
            return False
        self.advance()
        return True

    def expect(self, type_, value=None, message=None):
        if self.tok.type == type_ and (value is None or self.tok.value == value):
            return self.advance()
        self.error(self.tok, message or f"Kilichotarajiwa: {value or type_}")

    def skip_newlines(self):
        while self.tok.type == "NEWLINE":
            self.advance()

    def parse(self):
        self.skip_newlines()
        statements = self.parse_statement_list(stop="EOF")
        return Program(statements)

    def parse_statement_list(self, stop):
        out = []
        self.skip_newlines()
        while self.tok.type != stop and self.tok.type != "EOF":
            out.append(self.parse_statement())
            if self.tok.type == "NEWLINE":
                self.skip_newlines()
            elif self.tok.type in (stop, "EOF"):
                break
            elif self.tok.type == "KEYWORD" and self.tok.value in ("au", "vinginevyo"):
                break
            else:
                self.error(self.tok, "Tenganisha kauli kwa mstari mpya au ';'")
        return out

    def parse_statement(self):
        if self.tok.type == "KEYWORD":
            kw = self.tok.value
            if kw == "acha": return self.parse_var_decl()
            if kw == "ikiwa": return self.parse_if()
            if kw == "wakati": return self.parse_while()
            if kw == "kwa": return self.parse_for()
            if kw == "rudisha": return self.parse_return()
            if kw == "vunja": self.advance(); return BreakNode()
            if kw == "endelea": self.advance(); return ContinueNode()

        if self.looks_like_function_def():
            return self.parse_function_def()

        if self.tok.type == "IDENT" and self.peek().type == "EQ":
            name = self.advance().value
            self.advance()
            return AssignNode(name, self.parse_expression())

        return self.parse_expression()

    def looks_like_function_def(self):
        if self.tok.type != "IDENT" or self.peek().type != "LPAREN":
            return False
        j = self.i + 2
        if self.tokens[j].type == "RPAREN":
            j += 1
        else:
            while True:
                if self.tokens[j].type != "IDENT":
                    return False
                j += 1
                if self.tokens[j].type == "COMMA":
                    j += 1
                    continue
                if self.tokens[j].type == "RPAREN":
                    j += 1
                    break
                return False
        while self.tokens[j].type == "NEWLINE":
            j += 1
        return self.tokens[j].type in ("LBRACE", "ARROW")

    def parse_var_decl(self):
        self.expect("KEYWORD", "acha")
        name = self.expect("IDENT", message="Baada ya 'acha' tumia jina la variable").value
        self.expect("EQ", message="Tumia '=' baada ya jina la variable")
        return VarDeclNode(name, self.parse_expression())

    def parse_function_def(self):
        name = self.expect("IDENT").value
        self.expect("LPAREN")
        params = []
        if self.tok.type != "RPAREN":
            while True:
                params.append(self.expect("IDENT", message="Parameter lazima iwe jina").value)
                if not self.match("COMMA"):
                    break
        self.expect("RPAREN", message="Funga parameters kwa ')'")
        self.skip_newlines()
        if self.match("ARROW"):
            return FunctionDefNode(name, params, self.parse_expression(), True)
        return FunctionDefNode(name, params, self.parse_block(), False)

    def parse_condition(self):
        if self.match("LPAREN"):
            expr = self.parse_expression()
            self.expect("RPAREN", message="Funga condition kwa ')'")
            return expr
        # accepted for migration compatibility; docs use parentheses
        return self.parse_expression()

    def parse_if(self):
        self.expect("KEYWORD", "ikiwa")
        condition = self.parse_condition()
        body = self.parse_block()
        cases = [(condition, body)]
        else_body = None

        # Newlines between a closing brace and `au ikiwa` / `vinginevyo` belong
        # to the conditional chain. If there is no continuation, leave them for
        # the surrounding statement list to consume.
        while True:
            checkpoint = self.i
            self.skip_newlines()
            if self.tok.type == "KEYWORD" and self.tok.value == "au":
                self.advance()
                self.expect("KEYWORD", "ikiwa", "Baada ya 'au' tumia 'ikiwa'")
                condition = self.parse_condition()
                body = self.parse_block()
                cases.append((condition, body))
                continue
            if self.tok.type == "KEYWORD" and self.tok.value == "vinginevyo":
                self.advance()
                else_body = self.parse_block()
                break
            self.i = checkpoint
            break
        return IfNode(cases, else_body)

    def parse_while(self):
        self.expect("KEYWORD", "wakati")
        condition = self.parse_condition()
        return WhileNode(condition, self.parse_block())

    def parse_for(self):
        self.expect("KEYWORD", "kwa")
        name = self.expect("IDENT", message="Baada ya 'kwa' tumia jina la variable").value
        self.expect("KEYWORD", "katika", "Tumia 'katika' kwenye loop: kwa x katika orodha { ... }")
        iterable = self.parse_expression()
        return ForNode(name, iterable, self.parse_block())

    def parse_return(self):
        self.expect("KEYWORD", "rudisha")
        if self.tok.type in ("NEWLINE", "RBRACE", "EOF"):
            return ReturnNode(None)
        return ReturnNode(self.parse_expression())

    def parse_block(self):
        self.skip_newlines()
        self.expect("LBRACE", message="Tumia '{' kuanza block")
        self.skip_newlines()
        statements = self.parse_statement_list(stop="RBRACE")
        self.expect("RBRACE", message="Tumia '}' kufunga block")
        return Program(statements)

    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.tok.type == "KEYWORD" and self.tok.value == "au":
            self.advance(); node = BinaryNode(node, "au", self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_comparison()
        while self.tok.type == "KEYWORD" and self.tok.value == "na":
            self.advance(); node = BinaryNode(node, "na", self.parse_comparison())
        return node

    def parse_comparison(self):
        node = self.parse_range()
        ops = {"EQEQ": "==", "NE": "!=", "LT": "<", "GT": ">", "LTE": "<=", "GTE": ">="}
        while self.tok.type in ops:
            op = ops[self.advance().type]
            node = BinaryNode(node, op, self.parse_range())
        return node

    def parse_range(self):
        node = self.parse_arith()
        if self.match("RANGE"):
            end = self.parse_arith()
            step = None
            if self.match("RANGE"):
                step = self.parse_arith()
            node = RangeNode(node, end, step)
        return node

    def parse_arith(self):
        node = self.parse_term()
        while self.tok.type in ("PLUS", "MINUS"):
            op = self.advance().value
            node = BinaryNode(node, op, self.parse_term())
        return node

    def parse_term(self):
        node = self.parse_power()
        while self.tok.type in ("MUL", "DIV"):
            op = self.advance().value
            node = BinaryNode(node, op, self.parse_power())
        return node

    def parse_power(self):
        node = self.parse_unary()
        if self.tok.type == "POW":
            self.advance()
            node = BinaryNode(node, "^", self.parse_power())
        return node

    def parse_unary(self):
        if self.tok.type in ("PLUS", "MINUS"):
            op = self.advance().value
            return UnaryNode(op, self.parse_unary())
        if self.tok.type == "KEYWORD" and self.tok.value == "sio":
            self.advance()
            return UnaryNode("sio", self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            if self.match("LPAREN"):
                args = []
                if self.tok.type != "RPAREN":
                    while True:
                        args.append(self.parse_expression())
                        if not self.match("COMMA"):
                            break
                self.expect("RPAREN", message="Funga arguments kwa ')'")
                node = CallNode(node, args)
                continue
            if self.match("LBRACKET"):
                idx = self.parse_expression()
                self.expect("RBRACKET", message="Funga index kwa ']'")
                node = IndexNode(node, idx)
                continue
            break
        return node

    def parse_primary(self):
        t = self.tok
        if t.type == "NUMBER": self.advance(); return NumberNode(t.value)
        if t.type == "STRING": self.advance(); return StringNode(t.value)
        if t.type == "IDENT": self.advance(); return VarNode(t.value)
        if t.type == "KEYWORD" and t.value in ("kweli", "uongo"):
            self.advance(); return BoolNode(t.value == "kweli")
        if self.match("LPAREN"):
            node = self.parse_expression()
            self.expect("RPAREN", message="Funga expression kwa ')'")
            return node
        if self.match("LBRACKET"):
            items = []
            if self.tok.type != "RBRACKET":
                while True:
                    items.append(self.parse_expression())
                    if not self.match("COMMA"):
                        break
            self.expect("RBRACKET", message="Funga orodha kwa ']'")
            return ListNode(items)
        self.error(t, "Expression haijakamilika")
