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


def test_inline_choice_sizes_to_selection_and_retains_shared_dismissal(surface):
    root, _ = surface
    value = tk.StringVar(root, "MP4")
    field = ChoiceDropdown(
        root, textvariable=value, values=("MP4", "Original audio"), inline=True
    )
    field.pack()
    root.update()
    compact_width = field.winfo_width()
    value.set("Original audio")
    root.update()
    assert field.winfo_width() > compact_width
    assert field._chrome is None
    field._field.event_generate("<ButtonPress-1>", x=4, y=4)
    root.update()
    assert field._popover is not None
    root.event_generate("<ButtonPress-1>", x=1, y=1)
    root.update()
    assert field._popover is None


def test_local_preview_reserves_full_area_and_output_uses_shared_callback(
    surface, tmp_path
):
    from yt_downloader.local_audio_video_ui import LocalAudioVideoDialog
    from yt_downloader.ui_styles import apply_product_styles

    root, _ = surface
    apply_product_styles(root)
    shared_output = tk.StringVar(root, str(tmp_path))
    destination = tmp_path / "selected"
    calls = []

    def choose():
        calls.append(True)
        shared_output.set(str(destination))
        return destination

    dialog = LocalAudioVideoDialog(
        root,
        converter=None,
        output_dir=tmp_path,
        profile_variable=tk.StringVar(root, "1080p Standard (Recommended)"),
        on_complete=lambda result: None,
        on_closed=lambda: None,
        choose_output=choose,
    )
    dialog.popup.deiconify()
    dialog.popup.geometry("700x560")
    root.update()
    assert dialog.preview.cget("text") == "Image preview"
    assert dialog.preview.master.winfo_width() == 168
    assert dialog.preview.master.winfo_height() == 94
    dialog.destination_button.invoke()
    assert dialog.output_dir == destination
    assert dialog.destination_var.get() == shared_output.get()
    dialog._worker = object()
    dialog._choose_output()
    assert len(calls) == 1
    dialog._worker = None
    dialog._destroy()


@pytest.mark.parametrize("target", ["_field", "_chevron", "padding"])
@pytest.mark.parametrize("secondary", [False, True])
def test_first_click_opens_after_focus_moves_to_another_field(
    surface, target, secondary
):
    root, _original = surface
    owner = tk.Toplevel(root) if secondary else root
    field = ChoiceDropdown(
        owner, textvariable=tk.StringVar(owner, "MP4"), values=("MP4", "MP3")
    )
    field.pack()
    other = tk.Entry(owner)
    other.pack()
    root.update()
    other.focus_force()
    root.update()
    clicked = field._chrome.canvas if target == "padding" else getattr(field, target)
    clicked.event_generate("<ButtonPress-1>", x=4, y=4)
    clicked.event_generate("<ButtonRelease-1>", x=4, y=4)
    root.update()
    assert field._popover is not None
    assert field.focus_get() is field._popover.winfo_children()[0]


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


@pytest.mark.parametrize("kind", ["search", "choice"])
@pytest.mark.parametrize("width", [200, 480])
@pytest.mark.parametrize("text", ["", "Long input text " * 12])
def test_real_field_contents_never_cover_border_edges(surface, kind, width, text):
    from yt_downloader.library_search_ui import LibrarySearchField

    root, _field = surface
    value = tk.StringVar(root, text)
    if kind == "search":
        field = LibrarySearchField(root, variable=value)
    else:
        field = ChoiceDropdown(
            root, textvariable=value, values=("Travel",), state="normal"
        )
    field.place(x=30, y=120, width=width, height=40)
    root.update()
    for focused in (False, True):
        (field if focused else root).focus_force()
        root.update()
        w, h = field.winfo_width(), field.winfo_height()
        # Check straight strokes AND curved corners against actual stacked
        # widgets, not only equality of uncomposited background images.
        for x, y in (
            (w // 2, 1),
            (w // 2, h - 2),
            (1, h // 2),
            (w - 2, h // 2),
            (3, 3),
            (3, h - 4),
            (w - 4, 3),
            (w - 4, h - 4),
        ):
            painted = root.winfo_containing(
                field.winfo_rootx() + x, field.winfo_rooty() + y
            )
            assert painted is field._chrome.canvas, (kind, focused, x, y, painted)


@pytest.mark.parametrize("geometry", ["520x430", "700x560"])
def test_notes_edges_remain_visible_in_actual_annotation_dialog(surface, geometry):
    from yt_downloader.library_annotation_ui import LibraryAnnotationDialog
    from yt_downloader.library_annotations import LibraryAnnotation
    from yt_downloader.ui_styles import apply_product_styles

    root, _field = surface
    apply_product_styles(root)
    dialog = LibraryAnnotationDialog(
        root,
        title="Example",
        annotation=LibraryAnnotation(note="A long note. " * 100),
        categories=("Travel",),
        on_save=lambda _: False,
    )
    dialog.popup.geometry(geometry)
    dialog.popup.deiconify()
    dialog.note.focus_force()
    root.update()
    chrome = dialog._note_chrome
    shell = chrome.field
    w, h = shell.winfo_width(), shell.winfo_height()
    for x, y in ((w // 2, 1), (w // 2, h - 2), (1, h // 2), (w - 2, h // 2)):
        assert (
            root.winfo_containing(shell.winfo_rootx() + x, shell.winfo_rooty() + y)
            is chrome.canvas
        )
    dialog.popup.destroy()
