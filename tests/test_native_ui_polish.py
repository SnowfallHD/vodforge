"""Opt-in real Tcl/Tk checks; run with VODFORGE_NATIVE_UI_TESTS=1."""

import os
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from yt_downloader.activity_ui import (
    ActivityLogText,
    ActivitySummary,
    terminal_activity_line,
)
from yt_downloader.detail_ui import FactsText, OutputDetailsDialog
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_widgets import ChoiceDropdown, ProductEntry, SegmentedSelector

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="requires native Tcl/Tk"
)


@pytest.fixture
def root():
    window = tk.Tk()
    window.withdraw()
    apply_product_styles(window)
    yield window
    window.destroy()


@pytest.mark.parametrize("geometry", ["700x540", "820x720"])
def test_settings_pro_is_compact_visible_and_seen_only_when_shown(root, geometry):
    from yt_downloader.focus_settings import FocusSettingsDialog
    from yt_downloader.ui_widgets import ActionDialogSurface

    seen, clicked = [], []
    popup = tk.Toplevel(root)
    popup.withdraw()
    popup.geometry(geometry)
    dialog = FocusSettingsDialog.__new__(FocusSettingsDialog)
    dialog._closed = False
    dialog.actions = SimpleNamespace(
        record_cloud_cta_seen=lambda: seen.append(True),
        open_cloud_early_access=lambda: clicked.append(True),
    )
    dialog.dialog_surface = ActionDialogSurface(popup, allow_body_scroll=True)
    dialog._build_heading(dialog.dialog_surface.body)
    dialog._record_visible_pro()
    assert not seen
    popup.deiconify()
    root.update()
    dialog._record_visible_pro()
    assert seen == [True]
    button = dialog.pro_button
    assert button.cget("text") == "VODForge PRO"
    assert button.cget("image")
    assert dialog._pro_wordmark.width() > 80
    assert button.winfo_width() < 220
    button.invoke()
    assert clicked == [True]
    dialog._record_visible_pro()
    assert seen == [True]
    popup.destroy()


def test_activity_missing_icons_preserves_visible_tokens(root, monkeypatch):
    from yt_downloader import activity_ui

    monkeypatch.setattr(activity_ui, "_tinted_ui_icon", lambda *_args, **_kwargs: None)
    text = ActivityLogText(root)
    text.request("[success] Done\n[info] Ready")
    text.apply_theme()
    assert text.get("1.0", "end-1c") == "[success] Done\n[info] Ready"
    assert not text.tag_ranges("log-hidden")


def test_real_facts_keep_all_values_and_noop(root):
    text = FactsText(root)
    source = "\n".join(f"Fact {n}: exact value {n}" for n in range(80))
    assert text.request(source)
    assert text.raw_snapshot == source
    rendered = text.get("1.0", "end-1c")
    for n in range(80):
        assert f"Fact {n}\texact value {n}" in rendered
    before = text.get("1.0", "end")
    assert text.request(source) is False
    assert text.get("1.0", "end") == before
    assert str(text.cget("state")) == "disabled"


def test_log_decoration_is_character_exact_and_clear_invalidates(root):
    text = ActivityLogText(root)
    source = "09:12:30  [info] unicode →\n09:12:31 [warning] C:\\a path\\b\n"
    text.request(source)
    assert text.get("1.0", "end-1c") == source
    text.configure(state="normal")
    text.delete("1.0", "end")
    assert text.request(source)
    assert text.get("1.0", "end-1c") == source
    text.configure(state="normal")
    text.insert("end", "09:12:32 [error] appended")
    assert text.get("1.0", "end-1c") == source + "09:12:32 [error] appended"


@pytest.mark.parametrize("compact", [False, True])
def test_activity_theme_refresh_retains_document_and_noop(root, compact):
    from yt_downloader.ui_theme import THEME

    text = ActivityLogText(root, compact=compact)
    source = (
        "09:12:30 [info] Started\n09:12:31 [warning] Warning\n09:12:32 [error] Error"
    )
    text.request(source)
    original = THEME["accent"]
    try:
        THEME["accent"] = "#35aabb"
        text.apply_theme()
        assert text.tag_cget("log-level", "foreground") == "#35aabb"
        assert text.tag_cget("log-warning", "foreground") == THEME["warning"]
        assert text.tag_cget("log-error", "foreground") == THEME["danger"]
        assert text.get("1.0", "end-1c") == source
        assert text.request(source) is False
    finally:
        THEME["accent"] = original


def test_explicit_terminal_activity_and_summary(root):
    assert (
        terminal_activity_line("Failed", "Saved something earlier")
        == "[error] Saved something earlier"
    )
    assert terminal_activity_line("Completed", "Finished") == "[success] Finished"
    text = ActivityLogText(root)
    source = "14:30:08 [success] Finished\n14:30:09 [error] Failed"
    text.request(source)
    text.apply_theme()
    assert text.get("1.0", "end-1c") == source
    assert any(
        text.image_cget(name, "image") == str(text._success_icon)
        for name in text.image_names()
    )
    summary = ActivitySummary(root)
    assert summary.request(title="Run A", status="Completed", detail="Finished")
    assert not summary.request(title="Run A", status="Completed", detail="Finished")
    assert summary._status.get() == "Completed"
    assert summary.request(title="Run B", status="Failed", detail="Failure")
    assert summary._title.get() == "Run B"


def test_input_semantics_and_one_interpreter_chrome_cache(root):
    value = tk.StringVar(root, "initial")
    entry = ProductEntry(root, textvariable=value)
    entry.delete(0, "end")
    entry.insert(0, "edited")
    assert value.get() == "edited"
    entry.configure(state="readonly")
    entry.insert(0, "ignored")
    assert value.get() == "edited"
    style = ttk.Style(root)
    owner = root._product_chrome_owner
    images = tuple(str(image) for image in owner.images.values())
    owner.request(style)
    assert tuple(str(image) for image in owner.images.values()) == images
    dropdown = ChoiceDropdown(root, textvariable=value, values=("edited", "second"))
    value.set("second")
    assert dropdown.get() == "second"


def test_segmented_control_retains_bindings_and_noops(root):
    value = tk.StringVar(root, "MP4")
    selector = SegmentedSelector(root, variable=value)
    images = dict(selector._segment_images)
    selector._sync()
    assert selector._segment_images == images
    selector._select_from_event("MP3", None)
    assert value.get() == "MP3"
    assert selector._segment_images != images
    selected_images = dict(selector._segment_images)
    selector._sync()
    assert selector._segment_images == selected_images
    assert all(label.cget("takefocus") for label in selector.tooltip_targets())


def test_output_document_scrolls_without_moving_done(root):
    dialog = OutputDetailsDialog(
        root,
        sections=(
            (
                "Final output",
                "\n".join(f"Field {n}: " + "long value " * 12 for n in range(60)),
            ),
        ),
    )
    dialog.popup.geometry("460x320")
    dialog.popup.update_idletasks()
    document = dialog.documents[0]
    assert "Field 59" in document.raw_snapshot
    document.yview_moveto(1.0)
    assert document.yview()[1] == 1.0

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    done = next(
        w
        for w in descendants(dialog.popup)
        if isinstance(w, ttk.Button) and w.cget("text") == "Done"
    )
    assert done.winfo_rooty() >= dialog.popup.winfo_rooty()
    assert (
        done.winfo_rooty() + done.winfo_height()
        <= dialog.popup.winfo_rooty() + dialog.popup.winfo_height()
    )
    dialog.popup.destroy()


@pytest.mark.parametrize("content", ["Codec: H.264", "Codec: H.264\n"])
def test_details_section_tags_do_not_drift_into_facts(root, content):
    dialog = OutputDetailsDialog(
        root, sections=(("Requested output", content), ("Final output", "Codec: AAC"))
    )
    document = dialog.documents[0]
    ranges = document.tag_ranges("section")
    assert [document.get(ranges[n], ranges[n + 1]) for n in (0, 2)] == [
        "Requested output",
        "Final output",
    ]
    dialog.popup.destroy()


@pytest.mark.parametrize("size", ["1100x786", "980x690"])
def test_player_content_cannot_starve_stage_or_clip_previews(root, size):
    from PIL import Image, ImageTk

    from scripts.focus_ui_preview import PreviewMediaOwner, PreviewPlaybackBackend
    from yt_downloader.media_player_ui import MediaPlayerWindow, apply_preview_image

    player = MediaPlayerWindow(
        root,
        playback=PreviewPlaybackBackend(audio_only=False),
        previews=PreviewMediaOwner(),
        info={
            "title": "A saved film",
            "vodforge_user_note": "A note " * 300,
            "chapters": [
                {
                    "start_time": n * 10,
                    "end_time": (n + 1) * 10,
                    "title": f"Chapter {n}",
                }
                for n in range(10)
            ],
        },
    )
    player.popup.geometry(size)
    player.popup.deiconify()
    image = ImageTk.PhotoImage(Image.new("RGB", (132, 74), "#121419"), master=root)
    for label in player.preview_labels:
        apply_preview_image(label, image)
    player.popup.update_idletasks()
    assert player.stage.winfo_width() >= player.popup.winfo_width() * 0.60
    bottom = player.popup.winfo_rooty() + player.popup.winfo_height()
    for label in player.preview_labels:
        assert label.winfo_height() >= 74
        assert label.winfo_rooty() + label.winfo_height() + 18 <= bottom
    player.close()


def test_dropdown_keeps_arrow_under_width_pressure(root):
    root.geometry("180x90")
    root.deiconify()
    value = tk.StringVar(root, "A very long selected option")
    dropdown = ChoiceDropdown(root, textvariable=value, values=(value.get(),), width=40)
    dropdown.pack(fill="x")
    root.update_idletasks()
    assert dropdown._chevron.winfo_ismapped()
    assert (
        dropdown._chevron.winfo_x() + dropdown._chevron.winfo_width()
        <= dropdown.winfo_width()
    )


def test_analytics_prompt_actions_fit_without_scroll(root, tmp_path):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner
    from yt_downloader.analytics_startup import AnalyticsStartup

    startup = AnalyticsStartup(
        root, AnalyticsConsentOwner(tmp_path), tk.BooleanVar(root), lambda _: None
    )
    startup._prompt()
    popup = next(
        child for child in root.winfo_children() if isinstance(child, tk.Toplevel)
    )
    popup.update_idletasks()

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    buttons = [w for w in descendants(popup) if isinstance(w, ttk.Button)]
    assert {str(w.cget("text")) for w in buttons} == {
        "Not now",
        "Allow analytics",
        "Privacy details",
    }
    for button in buttons:
        assert button.winfo_ismapped()
        assert button.winfo_rooty() >= popup.winfo_rooty()
        assert (
            button.winfo_rooty() + button.winfo_height()
            <= popup.winfo_rooty() + popup.winfo_height()
        )
    startup.close()
    popup.destroy()
