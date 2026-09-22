"""Native player page geometry with controlled provider, not rendered-video proof."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import make_backend, pump, seed

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="native display required",
)


def test_player_fit_viewport_related_columns_and_expanded_information(
    application, tmp_path
):
    from yt_downloader.media_player_ui import MediaPlayerWindow

    app = application
    rows = seed(app, tmp_path, count=12)
    app.geometry("1414x900")
    app._select_focus_view("watch")
    host = app._archive_show_overlay(app._focus_views["watch"])
    backend, module = make_backend()
    media = tmp_path / "controlled.mp4"
    media.write_bytes(b"controlled provider; no real playback claim")
    backend.load(media, duration=100)
    observed = []
    errors = []
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    player = MediaPlayerWindow(
        app,
        playback=backend,
        previews=SimpleNamespace(
            preview_png=lambda _position: None, shutdown=lambda: None
        ),
        host=host,
        info=dict(
            rows[0], chapters=[{"title": "Opening", "start_time": 0, "end_time": 30}]
        ),
        library_records=rows,
        on_feature=lambda action, **fields: observed.append((action, fields)),
        source_details="Video bitrate: 8000 kbps\nAudio bitrate: 256 kbps",
        output_details="Video bitrate: 4000 kbps\nAudio bitrate: 128 kbps",
    )
    receipts = []
    try:
        player.show()
        for width, height in (
            (1414, 900),
            (980, 900),
            (820, 900),
            (1100, 600),
            (1414, 900),
        ):
            app.geometry(f"{width}x{height}")
            pump(app, 0.7)
            actual = player._content_root.winfo_width()
            stage_width, stage_height = (
                player.stage_shell.winfo_width(),
                player.stage_shell.winfo_height(),
            )
            assert abs(stage_width * 9 / 16 - stage_height) <= 2
            assert player._video_fill is False
            assert (
                player.transport.winfo_rooty() + player.transport.winfo_height()
                <= app.winfo_rooty() + app.winfo_height()
            )
            assert not hasattr(player, "_info_notebook")
            assert not hasattr(player, "details_button")
            assert set(player._detail_targets.values()) == {
                "info",
                "chapters",
                "notes",
                "source",
                "output",
                "moments",
            }
            assert int(player._related_view.grid_info()["column"]) == (
                1 if actual >= 1080 else 0
            )
            assert int(player._related_recent_view.grid_info()["row"]) > int(
                player.stage_shell.grid_info()["row"]
            )
            receipts.append(
                {
                    "requested_width": width,
                    "page_width": actual,
                    "viewport": [stage_width, stage_height],
                    "recommendations": dict(player._related_view.grid_info()),
                }
            )
        recent = player._related_recent_view
        player._page_surface.viewport.yview_moveto(0)
        recent.canvas.yview_moveto(0)
        pump(app, 0.2)
        recent._render()
        rail = recent._scene_rails["recent"]
        # Reveal the containing page section, then drive its shared horizontal owner.
        page_canvas = player._page_surface.viewport
        region = tuple(float(v) for v in page_canvas.cget("scrollregion").split())
        top = recent.winfo_rooty() - player._content_root.winfo_rooty()
        page_canvas.yview_moveto(top / region[3])
        pump(app, 0.2)
        recent._render()
        rail = recent._scene_rails["recent"]
        rail.canvas.focus_force()
        pump(app, 0.1)
        assert rail.canvas.winfo_viewable()
        assert rail.canvas.focus_get() is rail.canvas
        rail.canvas.event_generate("<End>")
        pump(app, 0.2)
        assert rail._focus_index == len(recent._related_plan.recent) - 1
        assert rail._focused() is not None
        assert rail.canvas.xview()[0] > 0
        player._page_surface.viewport.yview_moveto(1)
        pump(app, 0.4)
        assert all(
            section.winfo_ismapped()
            for section in player._information_sections.values()
        )
        assert not errors, errors
        destination = Path(
            os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))
        )
        destination.mkdir(parents=True, exist_ok=True)
        # Grid dictionaries include a Tk object; stringify only for this local QA receipt.
        (destination / "player-layout-native.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "scope": "Native Tk geometry with controlled backend, no actual video/physical input claim",
                    "sizes": receipts,
                    "events": observed,
                    "errors": errors,
                },
                default=str,
                indent=2,
            )
        )
    finally:
        player.close()
        pump(app)
    assert module.player.release_calls == 1
