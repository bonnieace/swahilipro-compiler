class AgentError(Exception):
    def __init__(self, code, exit_code=4, status=None):
        super().__init__(code)
        self.code, self.exit_code, self.status = code, exit_code, status
