"""Terminal opening failures retire one captured intent without modal UI."""

import json
import uuid
from types import SimpleNamespace

import pytest

from tests.test_presentation_diagnostics import real_owner
from tests.test_state_authority import Value
from yt_downloader import app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.archive_browser_ui import ArchiveBrowser
from yt_downloader.product_telemetry import _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def opening_app(tmp_path, telemetry=None):
    app = DownloaderApp.__new__(DownloaderApp)
    app.tk = None
    app._closing = False
    app._media_player_launch_generation = 1
    app.video_tree = ArchiveBrowser.__new__(ArchiveBrowser)
    app._archive_playback_host = app._archive_overlay = object()
    operation = str(uuid.uuid4())
    app._archive_opening_operation = operation
    app._archive_playback_origins = {operation: "watch"}
    app.product_telemetry = telemetry or real_owner(tmp_path / "telemetry")
    app.status_var = Value("Preparing")
    app.attention = []
    app._archive_playback_error = lambda message, **kwargs: app.attention.append(
        (message, kwargs)
    )
    app._record_playback_operation(operation, "requested")
    return app, operation


def events(app, tmp_path):
    assert app.product_telemetry.shutdown(2)
    rows = [
        e.public_payload() for e in _load_outbox(tmp_path / "telemetry/events.json")
    ]
    assert "PRIVATE" not in json.dumps(rows) and str(tmp_path) not in json.dumps(rows)
    return rows


@pytest.mark.parametrize(
    "boundary", ["dependency", "initialization", "readiness", "load"]
)
def test_opening_failure_is_in_window_bounded_and_retires_owner(
    tmp_path, monkeypatch, boundary
):
    app, operation = opening_app(tmp_path)
    released = []

    class Backend:
        def load(self, *_a, **_k):
            raise PermissionError(13, "PRIVATE file /Users/private/story.mp4")

        def shutdown(self):
            released.append("backend")

    app.playback_engine = (
        None
        if boundary == "dependency"
        else SimpleNamespace(
            failed=boundary == "initialization",
            ready=boundary == "load",
            create_backend=lambda: Backend(),
        )
    )
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda *_a, **_k: pytest.fail("embedded failure became modal"),
    )
    original = {
        "id": "PRIVATE-original",
        "title": "PRIVATE selected title",
        "vodforge_output_type": "MP4",
    }
    app._open_library_player_when_ready(
        original,
        tmp_path / "PRIVATE.mp4",
        ffmpeg="unused",
        launch_generation=1,
        deadline=0,
        operation=operation,
    )
    assert len(app.attention) == 1
    assert app.attention[0][1]["info"] == original
    assert app.status_var.get() == "Playback needs attention"
    assert app._archive_opening_operation is None
    assert app._archive_playback_origins == {}
    assert released == (["backend"] if boundary == "load" else [])
    rows = events(app, tmp_path)
    assert [e["action"] for e in rows] == ["requested", "failed"]
    failed = rows[-1]
    assert failed["dimensions"]["player_surface"] == "embedded"
    assert failed["dimensions"]["playback_origin"] == "watch"
    assert failed["dimensions"]["playback_failure_boundary"] == boundary
    if boundary == "dependency":
        assert failed["failure_reason"] == "dependency_missing"
    elif boundary == "readiness":
        assert failed["failure_detail"]["failure_code"] == "timeout"
    elif boundary == "load":
        assert failed["failure_reason"] == "permission_denied"
        assert failed["failure_detail"]["os_error"] == 13


def test_stale_readiness_cannot_retire_or_replace_a_new_opening(tmp_path):
    app, old = opening_app(tmp_path)
    app._archive_finish_opening(old, "cancelled")
    current = str(uuid.uuid4())
    app._media_player_launch_generation = 2
    app._archive_opening_operation = current
    app._archive_playback_origins[current] = "library"
    app.playback_engine = SimpleNamespace(failed=True)
    app._open_library_player_when_ready(
        {"id": "old"},
        tmp_path / "old.mp4",
        ffmpeg="unused",
        launch_generation=1,
        deadline=0,
        operation=old,
    )
    assert not app.attention
    assert app._archive_opening_operation == current
    assert app._archive_playback_origins == {current: "library"}
    assert [e["action"] for e in events(app, tmp_path)] == ["requested", "cancelled"]


def test_cancelled_opening_is_recorded_once_after_resolver_retirement(tmp_path):
    app, operation = opening_app(tmp_path)
    app._archive_finish_opening(operation, "cancelled")
    app._archive_finish_opening(operation, "cancelled")
    assert app._archive_playback_origins == {}
    assert app._archive_opening_operation is None
    assert [e["action"] for e in events(app, tmp_path)] == ["requested", "cancelled"]


def test_duplicate_terminal_callback_does_not_reopen_attention(tmp_path):
    app, operation = opening_app(tmp_path)
    for _ in range(2):
        app._fail_library_player_opening(
            {"id": "original"},
            "Player could not start",
            operation=operation,
            launch_generation=1,
            boundary="initialization",
        )
    assert len(app.attention) == 1
    assert [e["action"] for e in events(app, tmp_path)] == ["requested", "failed"]
