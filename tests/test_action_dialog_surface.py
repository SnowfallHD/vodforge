from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from yt_downloader.app import DownloaderApp
from yt_downloader.detail_ui import OutputDetailsDialog
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


def test_action_visibility_uses_the_general_protected_content_rule() -> None:
    source = inspect.getsource(ActionDialogSurface.action_is_visible)

    assert "protected_content_is_visible" in source


def test_every_content_bearing_action_dialog_uses_the_protected_surface() -> None:
    owners = (
        FocusSettingsDialog,
        LibraryAnnotationDialog,
        LibraryMediaRecoveryDialog,
        LocalAudioVideoDialog,
        OutputDetailsDialog,
        DownloaderApp._show_selected_metadata_details,
    )
    for owner in owners:
        source = inspect.getsource(owner)
        assert "ActionDialogSurface(" in source
        assert ".footer" in source

    local_content = inspect.getsource(LocalAudioVideoDialog._build_content)
    assert "self._build_actions(surface.footer)" in local_content
    assert "self._build_actions(root)" not in local_content
    assert "protect_status=True" in local_content
    assert "self._build_progress(surface.status)" in local_content
    assert "self._build_progress(root)" not in local_content

    settings_source = inspect.getsource(FocusSettingsDialog)
    assert "allow_body_scroll=True" in settings_source
    # Native injected192 proof shows the bounded screen can compress the note
    # field to1px. The existing viewport is admitted only for enlarged metrics;
    # default geometry remains an ordinary adaptive body.
    annotation_source = inspect.getsource(LibraryAnnotationDialog)
    assert "allow_body_scroll=metrics.scale > 1" in annotation_source
    for ordinary_dialog in (
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
        "detail_ui.py",
        "focus_settings.py",
        "library_annotation_ui.py",
        "library_collection_ui.py",
        "library_file_actions_ui.py",
        "library_media_recovery_ui.py",
        "local_audio_video_ui.py",
        "support_ui.py",
    }


def test_body_map_reconciles_actual_child_width_even_when_item_width_was_set():
    calls = []
    surface = ActionDialogSurface.__new__(ActionDialogSurface)
    surface.viewport = SimpleNamespace(
        winfo_width=lambda: 1060,
        itemconfigure=lambda item, **options: calls.append((item, options)),
    )
    surface._body_window = 4
    surface.body = SimpleNamespace(winfo_width=lambda: 1200)
    surface._sync_overflow = lambda: None
    surface._reconcile_body_width()
    assert calls == [(4, {"width": 1060})]
    surface.body = SimpleNamespace(winfo_width=lambda: 1060)
    surface._reconcile_body_width()
    assert len(calls) == 1


def test_body_geometry_reconciliation_is_coalesced_and_cancelled_on_destroy():
    calls = []
    surface = ActionDialogSurface.__new__(ActionDialogSurface)
    surface._body_width_pending = None
    surface.body = SimpleNamespace(
        after_idle=lambda callback: (calls.append(callback), "pending")[1],
        after_cancel=lambda token: calls.append(token),
    )
    surface._sync_overflow = lambda: None
    surface._body_resized(None)
    surface._body_resized(None)
    assert calls == [surface._reconcile_body_width]
    surface._body_destroyed(SimpleNamespace(widget=object()))
    assert surface._body_width_pending == "pending"
    surface._body_destroyed(SimpleNamespace(widget=surface.body))
    assert calls[-1] == "pending"
    assert surface._body_width_pending is None


def test_final_viewport_configure_schedules_reconcile_after_early_body_map():
    calls = []
    surface = ActionDialogSurface.__new__(ActionDialogSurface)
    surface._body_width_pending = None
    surface._body_window = 4
    width = [1]
    actual_body = [1200]
    surface.viewport = SimpleNamespace(
        winfo_width=lambda: width[0],
        itemconfigure=lambda item, **options: calls.append(("allocation", options)),
    )
    surface.body = SimpleNamespace(
        winfo_width=lambda: actual_body[0],
        after_idle=lambda callback: (calls.append(("deferred", callback)), "pending")[
            1
        ],
    )
    surface._sync_overflow = lambda: None
    surface._body_resized(None)
    surface._reconcile_body_width()
    assert not any(item[0] == "allocation" for item in calls)
    width[0] = 1060
    surface._viewport_resized(SimpleNamespace(width=1060))
    assert surface._body_width_pending == "pending"
    assert calls[-1][0] == "deferred"
    surface._reconcile_body_width()
    assert calls[-1] == ("allocation", {"width": 1060})
