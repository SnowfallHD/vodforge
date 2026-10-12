"""Simple value holders for data-boundary test fixtures."""


class Variable:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value
