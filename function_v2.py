try:
    from .environment_v2 import Environment, ReturnSignal, BreakSignal, ContinueSignal
except ImportError:
    from environment_v2 import Environment, ReturnSignal, BreakSignal, ContinueSignal


class UserFunction:
    def __init__(self, name, params, body, closure, expression_body, interpreter):
        self.name = name
        self.params = params
        self.body = body
        self.closure = closure
        self.expression_body = expression_body
        self.interpreter = interpreter

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError(f"{self.name} inahitaji arguments {len(self.params)}, imepewa {len(args)}")
        env = Environment(self.closure)
        for name, value in zip(self.params, args):
            env.declare(name, value)
        try:
            if self.expression_body:
                return self.interpreter.evaluate(self.body, env)
            self.interpreter.execute_program(self.body, env)
        except ReturnSignal as signal:
            return signal.value
        except (BreakSignal, ContinueSignal):
            raise self.interpreter.runtime_error("'vunja' na 'endelea' haziwezi kuvuka mpaka wa function")
        return None

    def __repr__(self):
        return f"<function {self.name}>"
