"""Run-menu commands cannot migrate to a successor run while a popup is open."""


class Menu:
    def __init__(self, *args, **kwargs):
        self.commands = {}

    def add_command(self, *, label, command):
        self.commands[label] = command

    def add_separator(self):
        pass

    def tk_popup(self, *_args):
        pass

    def grab_release(self):
        pass
