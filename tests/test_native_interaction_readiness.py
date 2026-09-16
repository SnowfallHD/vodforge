"""Real Tk outcomes for click intent and asynchronously available media facts."""

import gc
import io
import os
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from yt_downloader.media_player_ui import MediaPlayerWindow
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_widgets import ChoiceDropdown

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


@pytest.fixture
def root():
    # Collect retired Tk graphs on the owning thread before a preview worker runs.
    gc.collect()
    root = tk.Tk()
    root.geometry("1180x900")
    apply_product_styles(root)
    root.update()
    root.focus_force()
    root.update()
    yield root
    root.destroy()


def settle(root, predicate=lambda: False, seconds=0.35):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(0.01)


@pytest.mark.parametrize(
    "inline,initial,index,top",
    [
        (True, "MP4", 1, 0),
        (True, "Original audio", 0, 0),
        (False, "Download problem", 3, 0),
        (False, "Download problem", 9, 4),
    ],
)
def test_click_commits_pointed_row_without_prior_hover(
    root, inline, initial, index, top
):
    values = (
        ("MP4", "MP3", "Original audio")
        if inline
        else (
            "Download problem",
            "Playback problem",
            "Interface problem",
            "Suggestion",
            "Other",
            "Five",
            "Six",
            "Seven",
            "Eight",
            "Nine",
            "Ten",
            "Eleven",
        )
    )
    value = tk.StringVar(root, initial)
    field = ChoiceDropdown(root, textvariable=value, values=values, inline=inline)
    field.pack()
    root.update()
    field.open_popover()
    root.update()
    menu = field._popover.winfo_children()[0]
    # Keep a different keyboard selection, with the clicked row visible.
    menu.top = top
    menu._paint()
    y = 6 + (index - top) * menu.row_height + 17
    menu.event_generate("<ButtonPress-1>", x=24, y=y)
    menu.event_generate("<ButtonRelease-1>", x=24, y=y)
    root.update()
    assert value.get() == values[index]
    assert field._popover is None
    assert field.focus_get() is field


def open_choice(root, inline):
    value = tk.StringVar(root, "MP4")
    field = ChoiceDropdown(
        root,
        textvariable=value,
        values=("MP4", "MP3", "Original audio"),
        inline=inline,
    )
    field.pack()
    selected = []
    field.bind("<<ComboboxSelected>>", lambda _event: selected.append(value.get()))
    root.update()
    field.open_popover()
    root.update()
    return field, field._popover.winfo_children()[0], value, selected


@pytest.mark.parametrize("inline", [False, True])
@pytest.mark.parametrize("edge", ["left", "right", "top_padding", "bottom_padding"])
def test_drag_release_outside_rows_cancels_without_selection(root, inline, edge):
    field, menu, value, selected = open_choice(root, inline)
    row_y = 6 + menu.row_height + 17
    menu.event_generate("<ButtonPress-1>", x=24, y=row_y)
    x, y = {
        "left": (-2, row_y),
        "right": (menu.winfo_width() + 2, row_y),
        "top_padding": (24, 2),
        "bottom_padding": (24, menu.winfo_height() - 2),
    }[edge]
    menu.event_generate("<ButtonRelease-1>", x=x, y=y)
    root.update()
    assert value.get() == "MP4"
    assert selected == []
    assert field._popover is None


@pytest.mark.parametrize("inline", [False, True])
def test_release_commits_final_pointed_row_without_intermediate_motion(root, inline):
    field, menu, value, selected = open_choice(root, inline)
    menu.event_generate("<ButtonPress-1>", x=24, y=23)
    menu.event_generate("<ButtonRelease-1>", x=24, y=6 + menu.row_height + 17)
    root.update()
    assert value.get() == "MP3"
    assert selected == ["MP3"]
    assert field._popover is None


@pytest.mark.parametrize("inline", [False, True])
@pytest.mark.parametrize("finish", ["<ButtonRelease-1>", "<Return>"])
def test_disabling_open_choice_cancels_pending_input_then_reenable_works(
    root, inline, finish
):
    field, menu, value, selected = open_choice(root, inline)
    menu.event_generate("<ButtonPress-1>", x=24, y=6 + menu.row_height + 17)
    menu.event_generate(finish, x=24, y=6 + menu.row_height + 17, when="tail")
    field.configure(state="disabled")
    root.update()
    assert value.get() == "MP4"
    assert selected == []
    assert field._popover is None
    field.state(["!disabled"])
    field.open_popover()
    root.update()
    current = field._popover.winfo_children()[0]
    current.event_generate("<ButtonPress-1>", x=24, y=6 + menu.row_height + 17)
    current.event_generate("<ButtonRelease-1>", x=24, y=6 + menu.row_height + 17)
    root.update()
    assert value.get() == "MP3"
    assert selected == ["MP3"]


def test_retired_menu_callback_cannot_change_or_close_replacement(root):
    field, retired, value, selected = open_choice(root, False)
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    root.after_idle(lambda: field._commit_listbox(retired))
    field._close_popover()
    field.open_popover()
    current = field._popover
    root.update()
    assert errors == []
    assert value.get() == "MP4"
    assert selected == []
    assert field._popover is current
    assert current.winfo_exists()


class Backend:
    def __init__(self, duration):
        self.snapshot = PlaybackSnapshot(
            Path("generated.mp4"), "Ready", 0, duration, 37
        )
        self.closed = False

    def detach_render_surface(self):
        pass

    def shutdown(self):
        self.closed = True

    def seek(self, position):
        self.snapshot = replace(self.snapshot, position=position)


class Previews:
    def __init__(self, gate=None):
        self.positions = []
        self.active = 0
        self.max_active = 0
        self.gate = gate
        self.entered = threading.Event()
        self.closed = False

    def preview_png(self, position):
        self.positions.append(position)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.entered.set()
        try:
            if self.gate is not None:
                assert self.gate.wait(5)
                self.gate = None
            output = io.BytesIO()
            Image.new("RGB", (192, 108), (int(position * 10) % 255, 40, 80)).save(
                output, format="PNG"
            )
            return output.getvalue()
        finally:
            self.active -= 1

    def shutdown(self):
        self.closed = True


def make_player(root, duration=0, gate=None):
    backend, previews = Backend(duration), Previews(gate)
    player = MediaPlayerWindow(
        root,
        playback=backend,
        previews=previews,
        info={
            "title": "Generated fixture without source duration",
            "vodforge_output_type": "MP4",
        },
    )
    player.show()
    return player, backend, previews


def captions(player):
    strip = player.preview_labels[0].master
    return [
        str(next(iter(strip.grid_slaves(row=2, column=i))).cget("text"))
        for i in range(5)
    ]


def test_unknown_duration_does_not_extract_five_identical_zero_frames(root):
    player, _backend, previews = make_player(root)
    try:
        settle(root)
        assert previews.positions == []
        assert captions(player) == ["—"] * 5
    finally:
        player.close()


def test_late_duration_updates_visible_captions_images_and_seek_together(root):
    player, backend, previews = make_player(root)
    try:
        settle(root)
        backend.snapshot = replace(backend.snapshot, duration=6.0)
        settle(root, lambda: len(previews.positions) >= 5, seconds=2)
        settle(root)
        assert previews.positions == pytest.approx([0.6, 1.8, 3.0, 4.2, 5.4])
        assert captions(player) == ["0:00", "0:01", "0:03", "0:04", "0:05"]
        assert all(str(label.cget("image")) for label in player.preview_labels)
        player.preview_labels[3].event_generate("<Button-1>", x=5, y=5)
        assert backend.snapshot.position == pytest.approx(4.2)
        before = list(previews.positions)
        settle(root)
        assert previews.positions == before
    finally:
        player.close()


def test_new_duration_discards_inflight_old_images_without_parallel_workers(root):
    gate = threading.Event()
    player, backend, previews = make_player(root, duration=10.0, gate=gate)
    try:
        settle(root, previews.entered.is_set, seconds=2)
        assert previews.entered.is_set()
        backend.snapshot = replace(backend.snapshot, duration=20.0)
        settle(root)
        gate.set()
        settle(root, lambda: 18.0 in previews.positions, seconds=2)
        settle(root)
        assert previews.positions[-5:] == pytest.approx([2, 6, 10, 14, 18])
        assert captions(player) == ["0:02", "0:06", "0:10", "0:14", "0:18"]
        assert previews.max_active == 1
        from PIL import ImageTk

        images = [ImageTk.getimage(image) for image in player._preview_images]
        assert [image.getpixel((96, 54))[:3] for image in images] == [
            (20, 40, 80),
            (60, 40, 80),
            (100, 40, 80),
            (140, 40, 80),
            (180, 40, 80),
        ]
    finally:
        gate.set()
        player.close()


def test_close_while_preview_pending_retires_window_before_late_completion(root):
    gate = threading.Event()
    player, backend, previews = make_player(root, duration=10.0, gate=gate)
    settle(root, previews.entered.is_set, seconds=2)
    player.close()
    gate.set()
    settle(root)
    assert player.closed and backend.closed and previews.closed
    assert not player.popup.winfo_exists()
    assert previews.positions == [1.0]


@pytest.mark.parametrize("failure", ["unavailable", "invalid_png"])
def test_failed_preview_is_bounded_until_media_facts_change(root, failure):
    from yt_downloader.playback_backend import MediaPlayerError

    player, backend, previews = make_player(root)

    def fail(position):
        previews.positions.append(position)
        if failure == "unavailable":
            raise MediaPlayerError("Controlled unavailable preview")
        return b"not an image"

    previews.preview_png = fail
    try:
        backend.snapshot = replace(backend.snapshot, duration=6)
        settle(root, lambda: len(previews.positions) == 5, seconds=2)
        settle(root)
        assert previews.positions == pytest.approx([0.6, 1.8, 3, 4.2, 5.4])
        assert [label.cget("text") for label in player.preview_labels] == [
            "No preview"
        ] * 5
        settle(root)
        assert len(previews.positions) == 5
        backend.snapshot = replace(backend.snapshot, duration=10)
        settle(root, lambda: len(previews.positions) == 10, seconds=2)
        assert previews.positions[-5:] == pytest.approx([1, 3, 5, 7, 9])
    finally:
        player.close()
