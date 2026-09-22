"""Import producers report durable outcomes with bounded, content-free data."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader import app as app_module
from yt_downloader import library_import
from yt_downloader.history import HistoryError
from yt_downloader.telemetry_features import FEATURE_ACTIONS, validate_dimensions


@pytest.mark.parametrize("failed", [False, True])
def test_import_terminal_observation_follows_actual_persistence(
    tmp_path, monkeypatch, failed
):
    path = tmp_path / "Private filename.mp3"
    path.write_bytes(b"fixture")
    metadata = {
        "id": "private-id",
        "title": "Private title",
        "vodforge_output_type": "MP3",
        "vodforge_output_path": str(path),
    }
    events = []
    pending = []
    worker = SimpleNamespace(
        busy=False,
        submit=Mock(),
        poll=lambda: SimpleNamespace(error=None, value=([metadata], [])),
    )
    state = SimpleNamespace(
        _library_import_owner=worker,
        download_history=[],
        history_path=tmp_path / "history.json",
        _archive_observe=lambda feature, action, key, **dimensions: events.append(
            (feature, action, key, dimensions)
        ),
        bind=Mock(return_value="destroy-id"),
        unbind=Mock(),
        after=lambda _delay, callback: pending.append(callback),
        status_var=Mock(),
        library_scene=SimpleNamespace(navigate=Mock()),
        _select_focus_view=Mock(),
        _reconcile_library_projection=Mock(),
    )
    monkeypatch.setattr(
        app_module.filedialog, "askopenfilenames", lambda **_kw: (str(path),)
    )
    monkeypatch.setattr(app_module.messagebox, "showinfo", Mock())
    if failed:
        monkeypatch.setattr(
            library_import,
            "commit_imports",
            Mock(side_effect=HistoryError("Private disk failure")),
        )
    app_module.DownloaderApp._import_library_media(state)
    assert events[0][1] == "requested"
    pending.pop(0)()
    assert events[-1][1] == ("failed" if failed else "completed")
    assert events[-1][3]["committed_count"] == ("0" if failed else "1")
    assert events[-1][3]["failed_count"] == ("1" if failed else "0")
    assert bool(state.download_history) is not failed
    for feature, action, _key, dimensions in events:
        assert action in FEATURE_ACTIONS[feature]
        validate_dimensions(dimensions)
    assert "Private" not in repr(events) and str(tmp_path) not in repr(events)


def test_scene_route_dimension_rejects_user_content():
    assert validate_dimensions({"scene_route": "playlists"}) == {
        "scene_route": "playlists"
    }
    with pytest.raises(ValueError):
        validate_dimensions({"scene_route": "My private collection"})


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize(
    "permission",
    [
        "allowed",
        "denied",
        "late_grant",
        "regrant",
        "observer_unavailable",
        "observer_failure",
    ],
)
@pytest.mark.parametrize("outcome", ["completed", "failed", "cancelled"])
def test_import_observations_remain_bound_to_starting_consent(
    tmp_path, monkeypatch, permission, outcome
):
    import json
    import os
    from pathlib import Path
    from types import MethodType

    from tests.test_product_telemetry import _permitted_installation
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        enabled=permission not in {"denied", "late_grant"},
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    if permission in {"observer_unavailable", "observer_failure"}:
        monkeypatch.setattr(
            telemetry,
            "bind_operation"
            if permission == "observer_unavailable"
            else "record_operation",
            Mock(side_effect=OSError("PRIVATE observer failure")),
        )
    media = tmp_path / "PRIVATE filename.mp3"
    media.write_bytes(b"controlled inspection fixture")
    metadata = {
        "id": "PRIVATE-id",
        "title": "PRIVATE title",
        "vodforge_output_type": "MP3",
        "vodforge_output_path": str(media),
    }
    pending, bindings = [], {}
    worker = SimpleNamespace(
        busy=False,
        submit=Mock(),
        poll=lambda: SimpleNamespace(error=None, value=([metadata], [])),
    )
    app = SimpleNamespace(
        product_telemetry=telemetry,
        _library_import_owner=worker,
        download_history=[],
        history_path=tmp_path / "history.json",
        bind=lambda _name, callback, **kwargs: (
            bindings.setdefault("destroy", callback) and "destroy"
        ),
        unbind=lambda *args: bindings.pop("destroy", None),
        after=lambda _delay, callback: pending.append(callback),
        status_var=Mock(),
        library_scene=SimpleNamespace(navigate=Mock()),
        _select_focus_view=Mock(),
        _reconcile_library_projection=Mock(),
    )
    app._archive_observe = MethodType(ArchiveLibraryMixin._archive_observe, app)
    monkeypatch.setattr(
        app_module.filedialog, "askopenfilenames", lambda **kwargs: (str(media),)
    )
    monkeypatch.setattr(app_module.messagebox, "showinfo", Mock())
    if outcome == "failed":
        monkeypatch.setattr(
            library_import,
            "commit_imports",
            Mock(side_effect=HistoryError("PRIVATE disk failure")),
        )
    try:
        app_module.DownloaderApp._import_library_media(app)
        if permission == "late_grant":
            telemetry.set_enabled(True)
        elif permission == "regrant":
            telemetry.set_enabled(False)
            telemetry.set_enabled(True)
        if outcome == "cancelled":
            bindings["destroy"](SimpleNamespace(widget=app))
        else:
            pending.pop(0)()
        telemetry.shutdown(2)
        events = _load_outbox(tmp_path / "events.json")
        assert [event.action for event in events] == (
            ["requested", outcome] if permission == "allowed" else []
        )
        assert bool(app.download_history) == (outcome == "completed")
        if events:
            assert len({event.dimensions["operation_id"] for event in events}) == 1
            assert [event.dimensions["operation_step"] for event in events] == [
                "1",
                "2",
            ]
            payloads = [event.public_payload() for event in events]
            assert "PRIVATE" not in json.dumps(payloads) and str(
                tmp_path
            ) not in json.dumps(payloads)
            output = os.environ.get("VODFORGE_IMPORT_FIXTURE_DIR")
            if output:
                folder = Path(output)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{outcome}.json").write_text(json.dumps(payloads, indent=2))
    finally:
        telemetry.shutdown(2)


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("enabled", [True, False])
def test_import_worker_refusal_does_not_leave_polling_or_checking_status(
    tmp_path, monkeypatch, enabled
):
    """A native picker can outlive worker admission; use the real closed owner."""
    import json
    import os
    from pathlib import Path
    from types import MethodType

    from tests.test_product_telemetry import _permitted_installation
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.archive_work import ArchiveWorkOwner
    from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        enabled=enabled,
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    worker = ArchiveWorkOwner()
    pending, bindings = [], {}
    app = SimpleNamespace(
        product_telemetry=telemetry,
        _library_import_owner=worker,
        download_history=[],
        history_path=tmp_path / "history.json",
        bind=lambda _name, callback, **kwargs: (
            bindings.setdefault("destroy", callback) and "destroy"
        ),
        unbind=lambda *args: bindings.pop("destroy", None),
        after=lambda _delay, callback: pending.append(callback),
        status_var=Mock(),
        library_scene=SimpleNamespace(navigate=Mock()),
        _select_focus_view=Mock(),
        _reconcile_library_projection=Mock(),
    )
    app._archive_observe = MethodType(ArchiveLibraryMixin._archive_observe, app)

    def pick(**kwargs):
        worker.close()
        return (str(tmp_path / "PRIVATE unavailable.mp3"),)

    monkeypatch.setattr(app_module.filedialog, "askopenfilenames", pick)
    try:
        app_module.DownloaderApp._import_library_media(app)
        assert not pending, "Refused work must not start an endless result poll"
        assert not bindings, "Refused operation must retire its cancellation callback"
        assert not app.download_history and not app.history_path.exists()
        assert app.status_var.set.call_args.args == (
            "Media could not be checked. Please try again.",
        )
        telemetry.shutdown(2)
        events = _load_outbox(tmp_path / "events.json")
        assert [event.action for event in events] == (
            ["requested", "failed"] if enabled else []
        )
        if events:
            assert len({event.dimensions["operation_id"] for event in events}) == 1
            assert events[-1].dimensions["committed_count"] == "0"
            assert events[-1].dimensions["failed_count"] == "1"
            assert events[-1].dimensions["stage"] == "analysis"
            payloads = [event.public_payload() for event in events]
            assert "PRIVATE" not in json.dumps(payloads) and str(
                tmp_path
            ) not in json.dumps(payloads)
            output = os.environ.get("VODFORGE_IMPORT_FIXTURE_DIR")
            if output:
                folder = Path(output)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "worker_refused.json").write_text(
                    json.dumps(payloads, indent=2)
                )
    finally:
        worker.close()
        telemetry.shutdown(2)
