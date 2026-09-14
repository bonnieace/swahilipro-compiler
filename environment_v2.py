class Environment:
    def __init__(self, parent=None):
        self.parent = parent
        self.values = {}

    def declare(self, name, value):
        self.values[name] = value
        return value

    def get(self, name):
        if name in self.values:
            return self.values[name]
        if self.parent:
            return self.parent.get(name)
        raise NameError(name)

    def assign(self, name, value):
        if name in self.values:
            self.values[name] = value
            return value
        if self.parent:
            try:
                return self.parent.assign(name, value)
            except NameError:
                pass
        raise NameError(name)


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass
