from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from yt_downloader.app import DownloaderApp
from yt_downloader.focus_settings import FocusSettingsDialog
from yt_downloader.library_annotation_ui import LibraryAnnotationDialog
from yt_downloader.library_media_recovery_ui import LibraryMediaRecoveryDialog
from yt_downloader.local_audio_video_ui import LocalAudioVideoDialog
from yt_downloader.ui_widgets import ActionDialogSurface


class _FakeViewport:
    def __init__(self, *, height: int) -> None:
        self.height = height
        self.configured: list[object] = []
        self.moves: list[float] = []

    def bbox(self, _tag: str):
        return (0, 0, 400, 600)

    def configure(self, **options) -> None:
        self.configured.append(options["scrollregion"])

    def winfo_height(self) -> int:
        return self.height

    def yview_moveto(self, value: float) -> None:
        self.moves.append(value)


class _FakeScrollbar:
    def __init__(self) -> None:
        self.visible = False

    def grid(self) -> None:
        self.visible = True

    def grid_remove(self) -> None:
        self.visible = False


def test_opted_in_action_surface_scrolls_without_surrendering_footer_space() -> None:
    viewport = _FakeViewport(height=420)
    scrollbar = _FakeScrollbar()
    surface = ActionDialogSurface.__new__(ActionDialogSurface)
    surface.viewport = viewport
    surface.scrollbar = scrollbar
    surface.body = SimpleNamespace(winfo_reqheight=lambda: 600)

    surface._sync_overflow()

    assert scrollbar.visible is True
    assert viewport.configured == [(0, 0, 400, 600)]
    assert viewport.moves == []

    surface.body = SimpleNamespace(winfo_reqheight=lambda: 300)
    surface._sync_overflow()

    assert scrollbar.visible is False
    assert viewport.moves == [0.0]


def test_scrollable_action_surface_routes_wheel_events_from_all_descendants() -> None:
    source = inspect.getsource(ActionDialogSurface.__init__)

    assert "viewport, viewport, body, popup" in source


def test_required_action_is_visible_only_when_fully_inside_dialog() -> None:
    popup = SimpleNamespace(
        update_idletasks=lambda: None,
        winfo_rootx=lambda: 100,
        winfo_rooty=lambda: 80,
        winfo_width=lambda: 700,
        winfo_height=lambda: 570,
    )
    widget = SimpleNamespace(
        winfo_ismapped=lambda: True,
        winfo_rootx=lambda: 650,
        winfo_rooty=lambda: 610,
        winfo_width=lambda: 120,
        winfo_height=lambda: 30,
    )
    surface = ActionDialogSurface.__new__(ActionDialogSurface)
    surface.popup = popup

    assert surface.action_is_visible(widget) is True

    widget.winfo_rooty = lambda: 630
    widget.winfo_height = lambda: 30
    assert surface.action_is_visible(widget) is False


def test_every_content_bearing_action_dialog_uses_the_protected_surface() -> None:
    owners = (
        FocusSettingsDialog,
        LibraryAnnotationDialog,
        LibraryMediaRecoveryDialog,
        LocalAudioVideoDialog,
        DownloaderApp._show_focus_output_details,
        DownloaderApp._show_selected_metadata_details,
    )
    for owner in owners:
        source = inspect.getsource(owner)
        assert "ActionDialogSurface(" in source
        assert ".footer" in source

    local_content = inspect.getsource(LocalAudioVideoDialog._build_content)
    assert "self._build_actions(surface.footer)" in local_content
    assert "self._build_actions(root)" not in local_content

    settings_source = inspect.getsource(FocusSettingsDialog)
    assert "allow_body_scroll=True" in settings_source
    for ordinary_dialog in (
        LibraryAnnotationDialog,
        LibraryMediaRecoveryDialog,
        LocalAudioVideoDialog,
        DownloaderApp._show_focus_output_details,
        DownloaderApp._show_selected_metadata_details,
    ):
        assert "allow_body_scroll=True" not in inspect.getsource(ordinary_dialog)


def test_new_action_dialog_modules_must_adopt_the_shared_surface() -> None:
    package = Path(__file__).parents[1] / "yt_downloader"
    exempt = {
        # Player controls live in a stable header/transport, not a bottom action
        # footer that dynamic document content can displace.
        "media_player_ui.py",
        # This module defines the invariant owner and an override-redirect tooltip.
        "ui_widgets.py",
    }
    candidates = []
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if (
            path.name not in exempt
            and "tk.Toplevel" in source
            and ("Accent.TButton" in source or "FocusQuiet.TButton" in source)
        ):
            candidates.append(path)
            assert "ActionDialogSurface" in source, path.name

    assert {path.name for path in candidates} == {
        "app.py",
        "focus_settings.py",
        "library_annotation_ui.py",
        "library_media_recovery_ui.py",
        "local_audio_video_ui.py",
    }
