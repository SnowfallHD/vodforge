"""Native ownership and input checks; no temporal pixel acceptance claim."""

import os
import tkinter as tk

import pytest

from yt_downloader.ui_button_contract import ProductButton
from yt_downloader.ui_canvas_actions import CanvasActions
from yt_downloader.ui_transition import WidgetReveal

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native display required",
)


@pytest.mark.parametrize("hidden", ["outside_viewport", "hidden_item", "placed_hint"])
def test_reveal_ignores_excluded_canvas_content_but_waits_for_visible_geometry(hidden):
    root = tk.Tk()
    root.geometry("500x300")
    old = tk.Frame(root)
    old.place(x=0, y=0, width=500, height=300)
    new = tk.Frame(root)
    new.place(x=0, y=0, width=500, height=300)
    canvas = tk.Canvas(new, width=300, height=180, scrollregion=(0, 0, 300, 1000))
    canvas.pack()
    entry = tk.Entry(canvas)
    canvas.create_window(
        10,
        700 if hidden != "hidden_item" else 10,
        window=entry,
        anchor="nw",
        width=150,
        height=25,
        state="hidden" if hidden == "hidden_item" else "normal",
    )
    if hidden == "placed_hint":
        tk.Label(canvas, text="Optional hint").place(in_=entry, x=0, y=0)
    visible = tk.Label(new, text="Must have usable geometry")
    visible.place(x=10, y=200, width=1, height=25)
    root.update()
    old.lift()
    finished = []
    reveal = WidgetReveal(
        new,
        [old],
        current=lambda: True,
        escape=lambda: None,
        finished=lambda: finished.append(True),
    )
    try:
        assert not entry.winfo_ismapped()
        assert visible.winfo_ismapped() and visible.winfo_width() == 1
        reveal.start()
        root.after(80, root.quit)
        root.mainloop()
        assert reveal.active and finished == []
        assert old.winfo_ismapped(), (
            "Genuinely unready visible content must remain covered"
        )
        visible.place_configure(width=240)
        root.after(80, root.quit)
        root.mainloop()
        assert not reveal.active and finished == [True]
        # place geometry is intentionally used by this independent consumer;
        # retirement callback owns final destruction, not this assertion.
        assert new.winfo_ismapped() and visible.winfo_width() == 240
        assert not entry.winfo_ismapped()
    finally:
        reveal.cancel()
        root.destroy()


@pytest.mark.parametrize(
    "ending", ["cancel", "destroy", "superseded", "reveal", "escape"]
)
def test_reveal_owns_callbacks_and_retires_old_gestures(ending):
    root = tk.Tk()
    errors, calls = [], []
    root.report_callback_exception = lambda *args: errors.append(str(args[1]))
    root.geometry("500x300")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)
    nav = ProductButton(root, text="Other view", command=lambda: calls.append("nav"))
    nav.grid(row=0, column=0)
    old = tk.Frame(root)
    old.grid(row=1, column=0, sticky="nsew")
    button = ProductButton(old, text="Old action", command=lambda: calls.append("old"))
    button.pack()
    canvas = tk.Canvas(old, width=200, height=80)
    canvas.pack()
    targets = [((0, 0, 100, 60), lambda: calls.append("canvas"))]
    pointer = CanvasActions(canvas, lambda: targets)
    new = tk.Frame(root)
    new.grid(row=1, column=0, sticky="nsew")
    tk.Label(new, text="New view").pack()
    hidden_branch = tk.Frame(new)
    tk.Label(hidden_branch, text="Intentionally undisclosed detail").pack()

    old.lift()
    root.update()
    original_tags = button.bindtags()
    root.bind("<Escape>", lambda event: calls.append("outer-escape"))
    original_commands = set(root._tclCommands)
    original_frame_commands = set(new._tclCommands or [])
    try:
        button.event_generate("<ButtonPress-1>", x=4, y=4)
        assert button._pressed_command
        canvas.event_generate("<ButtonPress-1>", x=20, y=20)
        assert pointer._pressed is targets[0]
        current = [True]

        def escape():
            calls.append("escape")
            reveal.cancel()

        reveal = WidgetReveal(
            new,
            [old],
            current=lambda: current[0],
            escape=escape,
        )
        owned_commands = tuple(reveal._commands)
        assert pointer._pressed is None
        assert not canvas.find_withtag("pointer-state")
        assert button._pressed_command is None
        assert not button.instate(["pressed"])
        assert nav.bindtags()[0] != reveal._tag
        nav.invoke()
        button.event_generate("<ButtonPress-1>", x=4, y=4)
        button.event_generate("<ButtonRelease-1>", x=4, y=4)
        assert calls == ["nav"]
        # Preserve a binding added by another owner while staging is active.
        button.bindtags((*button.bindtags(), "unrelated-owner"))
        reveal.start(lambda: ending == "reveal")
        if ending == "cancel":
            reveal.cancel()
        elif ending == "destroy":
            new.destroy()
        elif ending == "superseded":
            current[0] = False
        elif ending == "escape":
            button.focus_force()
            button.event_generate("<KeyPress-Escape>")
            assert calls == ["nav", "escape"]

        root.after(80, root.quit)
        root.mainloop()
        assert not reveal.active and reveal.timer is None
        assert button.bindtags() == (*original_tags, "unrelated-owner")
        assert not set(owned_commands).intersection(root._tclCommands)
        assert set(root._tclCommands) == original_commands
        assert all(
            not root.tk.call("info", "commands", name) for name in owned_commands
        )
        if ending != "destroy":
            assert set(new._tclCommands or []) == original_frame_commands
        assert bool(old.winfo_manager()) is (ending != "reveal")
        # A queued completion after retirement cannot hide the old view.
        reveal._attempt()
        assert bool(old.winfo_manager()) is (ending != "reveal")
        reveal.cancel()
        button.event_generate("<ButtonRelease-1>", x=4, y=4)
        canvas.event_generate("<ButtonRelease-1>", x=20, y=20)
        assert calls == (["nav", "escape"] if ending == "escape" else ["nav"])
        assert not errors
    finally:
        root.destroy()
    assert not errors
