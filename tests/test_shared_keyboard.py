"""One keypress belongs to the nearest visible scope, including teardown."""

from types import SimpleNamespace

from tests.test_shared_input import View
from yt_downloader.ui_widgets import KeyboardScope


class Widget(View):
    def __init__(self, master=None, kind="Frame"):
        super().__init__(master)
        self.kind, self.visible, self.grab = kind, True, None

    def winfo_ismapped(self):
        return self.visible

    def winfo_class(self):
        return self.kind

    def grab_current(self):
        return self.grab


def key(root, widget, sequence):
    for callback in tuple(root.bindings[sequence].values()):
        if callback(SimpleNamespace(widget=widget)) == "break":
            return "break"


def test_nested_escape_closes_only_current_scope_and_never_cascades():
    root, calls = Widget(), []
    page = Widget(root)
    inner = Widget(page)
    KeyboardScope(page, {"<Escape>": lambda: calls.append("page")})
    child = KeyboardScope(
        inner, {"<Escape>": lambda: (calls.append("editor"), child.close())}
    )
    assert key(root, inner, "<Escape>") == "break"
    assert calls == ["editor"]
    assert key(root, page, "<Escape>") == "break"
    assert calls == ["editor", "page"]


def test_editing_keys_remain_local_and_popup_enter_is_explicit():
    root, calls = Widget(), []
    entry = Widget(root, "TEntry")
    scope = KeyboardScope(root, {"<space>": lambda: calls.append("play")})
    key(root, entry, "<space>")
    assert not calls
    scope.close()
    KeyboardScope(
        root, {"<Return>": lambda: calls.append("save")}, editing=("<Return>",)
    )
    key(root, entry, "<Return>")
    assert calls == ["save"]


def test_hidden_scope_and_other_modal_grab_cannot_steal_key():
    root, calls = Widget(), []
    page = Widget(root)
    KeyboardScope(page, {"<Escape>": lambda: calls.append("page")})
    page.visible = False
    key(root, page, "<Escape>")
    page.visible = True
    page.grab = Widget()
    key(root, page, "<Escape>")
    assert not calls


def test_scope_teardown_preserves_unrelated_binding():
    root = Widget()
    token = root.bind("<Escape>", lambda event: None)
    scope = KeyboardScope(root, {"<Escape>": lambda: None})
    scope.close()
    assert list(root.bindings["<Escape>"]) == [token]
