"""Native lifetime contracts; no download, production telemetry, or user state."""

import os
import tkinter as tk
from tkinter import ttk

import pytest

from yt_downloader.ui_chrome import RoundedFieldBorder
from yt_downloader.ui_theme import THEME
from yt_downloader.ui_widgets import ChoiceDropdown, PixelScrollTable

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


@pytest.fixture
def surface():
    root = tk.Tk()
    root.geometry("600x400")
    value = tk.StringVar(root, "MP4")
    dropdown = ChoiceDropdown(
        root, textvariable=value, values=("MP4", "MP3", "Original audio")
    )
    dropdown.pack()
    root.update()
    root.focus_force()
    root.update()
    yield root, dropdown
    root.destroy()


@pytest.mark.parametrize("kind", ["label", "button", "entry"])
def test_outside_click_dismisses_even_when_target_breaks_dispatch(surface, kind):
    root, field = surface
    target = {"label": tk.Label, "button": ttk.Button, "entry": tk.Entry}[kind](root)
    target.pack()
    target.bind("<ButtonPress-1>", lambda _e: "break")
    root.update()
    original = target.bindtags()
    field.open_popover()
    root.update()
    target.event_generate("<ButtonPress-1>", x=2, y=2)
    root.update()
    assert field._popover is None
    assert target.bindtags() == original


@pytest.mark.parametrize(
    "action", ["escape", "hide_anchor", "hide_window", "other_window", "destroy_anchor"]
)
def test_surface_lifetime_follows_owner(surface, action):
    root, field = surface
    field.open_popover()
    root.update()
    popup = field._popover
    assert popup is not None
    # Structural proof: no independent OS window can survive app deactivation.
    assert popup.winfo_toplevel() is root
    assert int(field.cget("highlightthickness")) == 0
    if action == "escape":
        popup.winfo_children()[0].event_generate("<Escape>")
    elif action == "hide_anchor":
        field.pack_forget()
    elif action == "hide_window":
        root.withdraw()
    elif action == "other_window":
        other = tk.Toplevel(root)
        other.update()
        other.focus_force()
    else:
        field.destroy()
    root.update()
    assert field._popover is None
    assert not popup.winfo_exists()


def test_repeated_open_close_does_not_leak_bindings_or_tcl_commands(surface):
    root, field = surface
    original_tags = field.bindtags()
    commands = set(root.tk.call("info", "commands"))
    for _ in range(12):
        field.open_popover()
        root.update()
        field._close_popover()
        root.update()
    assert field.bindtags() == original_tags
    assert set(root.tk.call("info", "commands")) == commands


@pytest.mark.parametrize("size", [(300, 38), (480, 120)])
def test_rounded_chrome_covers_shell_padding_without_square_edges(surface, size):
    root, _field = surface
    shell = tk.Frame(root, width=size[0], height=size[1], bg=THEME["surface"])
    shell.pack()
    chrome = RoundedFieldBorder(shell)
    root.update()
    assert chrome.canvas.winfo_x() == 0
    assert chrome.canvas.winfo_y() == 0
    assert chrome.canvas.winfo_width() == shell.winfo_width()
    assert chrome.canvas.winfo_height() == shell.winfo_height()


def test_table_focus_preserves_neutral_outline(surface):
    root, _field = surface
    table = PixelScrollTable(root, columns=("title",))
    table.pack()
    table.focus_force()
    root.update()
    assert (
        table.cget("highlightcolor")
        == table.cget("highlightbackground")
        == THEME["border"]
    )


def test_canvas_and_ttk_field_adapters_share_identical_chrome(surface):
    from PIL import ImageTk

    from yt_downloader.ui_chrome import ProductChromeOwner, field_border_image

    root, _field = surface
    shell = tk.Frame(root, width=28, height=28)
    shell.pack()
    chrome = RoundedFieldBorder(shell)
    root.update()
    owner = ProductChromeOwner(root)
    owner.request(ttk.Style(root))
    expected = field_border_image(28, 28).tobytes()
    assert ImageTk.getimage(chrome._image).tobytes() == expected
    assert ImageTk.getimage(owner.images["field"]).tobytes() == expected
    assert ImageTk.getimage(owner.images["field_focus"]).tobytes() == expected
