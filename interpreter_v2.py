try:
    from .syntax_v2 import *
    from .environment_v2 import Environment, ReturnSignal, BreakSignal, ContinueSignal
    from .function_v2 import UserFunction
except ImportError:
    from syntax_v2 import *
    from environment_v2 import Environment, ReturnSignal, BreakSignal, ContinueSignal
    from function_v2 import UserFunction


class Interpreter:
    def __init__(self, fn, text):
        self.fn = fn
        self.text = text

    def execute_program(self, program, env):
        result = None
        for statement in program.statements:
            result = self.evaluate(statement, env)
        return result

    def runtime_error(self, details):
        return RuntimeErrorSwa(self.fn, self.text, 0, 0, "Kosa la utekelezaji", details)

    def evaluate(self, node, env):
        if isinstance(node, Program):
            return self.execute_program(node, env)
        if isinstance(node, NumberNode):
            return node.value
        if isinstance(node, StringNode):
            return node.value
        if isinstance(node, BoolNode):
            return node.value
        if isinstance(node, ListNode):
            return [self.evaluate(x, env) for x in node.elements]
        if isinstance(node, VarNode):
            try:
                return env.get(node.name)
            except NameError:
                raise self.runtime_error(f"'{node.name}' haijafafanuliwa")
        if isinstance(node, VarDeclNode):
            return env.declare(node.name, self.evaluate(node.value, env))
        if isinstance(node, AssignNode):
            value = self.evaluate(node.value, env)
            try:
                return env.assign(node.name, value)
            except NameError:
                raise self.runtime_error(f"'{node.name}' haijafafanuliwa. Tumia 'acha {node.name} = ...' kwanza")
        if isinstance(node, UnaryNode):
            value = self.evaluate(node.value, env)
            if node.op == "-": return -value
            if node.op == "+": return +value
            if node.op == "sio": return not bool(value)
        if isinstance(node, BinaryNode):
            if node.op == "na":
                left = self.evaluate(node.left, env)
                return bool(left) and bool(self.evaluate(node.right, env))
            if node.op == "au":
                left = self.evaluate(node.left, env)
                return bool(left) or bool(self.evaluate(node.right, env))
            left = self.evaluate(node.left, env)
            right = self.evaluate(node.right, env)
            try:
                if node.op == "+":
                    if isinstance(left, list) or isinstance(right, list):
                        raise TypeError("Tumia ongeza(...) kwa orodha")
                    return left + right
                if node.op == "-": return left - right
                if node.op == "*":
                    if isinstance(left, list) or isinstance(right, list):
                        raise TypeError("'*' haitumiki kuunganisha orodha")
                    return left * right
                if node.op == "/": return left / right
                if node.op == "^": return left ** right
                if node.op == "==": return left == right
                if node.op == "!=": return left != right
                if node.op == "<": return left < right
                if node.op == ">": return left > right
                if node.op == "<=": return left <= right
                if node.op == ">=": return left >= right
            except Exception as exc:
                raise self.runtime_error(str(exc))
        if isinstance(node, RangeNode):
            start = self.evaluate(node.start, env)
            end = self.evaluate(node.end, env)
            step = self.evaluate(node.step, env) if node.step is not None else 1
            if not all(isinstance(v, int) for v in (start, end, step)):
                raise self.runtime_error("Range inahitaji nambari kamili")
            if step == 0:
                raise self.runtime_error("Hatua ya range haiwezi kuwa 0")
            return range(start, end, step)
        if isinstance(node, IndexNode):
            target = self.evaluate(node.target, env)
            index = self.evaluate(node.index, env)
            try:
                return target[index]
            except Exception as exc:
                raise self.runtime_error(str(exc))
        if isinstance(node, CallNode):
            callee = self.evaluate(node.callee, env)
            args = [self.evaluate(arg, env) for arg in node.args]
            if not callable(callee):
                raise self.runtime_error("Thamani hii haiwezi kuitwa kama function")
            try:
                return callee(*args)
            except SwahiliProError:
                raise
            except Exception as exc:
                raise self.runtime_error(str(exc))
        if isinstance(node, FunctionDefNode):
            function = UserFunction(node.name, node.params, node.body, env, node.expression_body, self)
            env.declare(node.name, function)
            return function
        if isinstance(node, ReturnNode):
            raise ReturnSignal(None if node.value is None else self.evaluate(node.value, env))
        if isinstance(node, IfNode):
            for condition, body in node.cases:
                if bool(self.evaluate(condition, env)):
                    return self.execute_program(body, env)
            if node.else_body is not None:
                return self.execute_program(node.else_body, env)
            return None
        if isinstance(node, WhileNode):
            result = None
            while bool(self.evaluate(node.condition, env)):
                try:
                    result = self.execute_program(node.body, env)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return result
        if isinstance(node, ForNode):
            iterable = self.evaluate(node.iterable, env)
            try:
                iterator = iter(iterable)
            except TypeError:
                raise self.runtime_error("'kwa ... katika ...' inahitaji kitu kinachoweza kurudiwa")
            result = None
            env.declare(node.name, None)
            for value in iterator:
                env.assign(node.name, value)
                try:
                    result = self.execute_program(node.body, env)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return result
        if isinstance(node, BreakNode):
            raise BreakSignal()
        if isinstance(node, ContinueNode):
            raise ContinueSignal()
        raise self.runtime_error(f"Node isiyojulikana: {type(node).__name__}")
