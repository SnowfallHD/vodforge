"""Real Tcl ownership probes; synthetic pixels and local telemetry outbox."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MethodType

import pytest
from PIL import Image

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from tests.test_presentation_diagnostics import real_owner
from yt_downloader.presentation_diagnostics import PresentationObservations
from yt_downloader.product_telemetry import ProductTelemetryOwner

_ORIGINAL_RECORD = ProductTelemetryOwner.record

application = _application
pytestmark = [
    pytest.mark.skipif(
        os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native GUI lease"
    ),
    pytest.mark.usefixtures("production_telemetry_contract"),
]


def instrument(app, path):
    owner = real_owner(path)
    # The general visual fixture disables ProductTelemetryOwner.record.
    # Restore only this local fake-transport owner's original method.
    owner.record = MethodType(_ORIGINAL_RECORD, owner)
    app.product_telemetry = owner
    for view, surface in [(app.focus_watch, "watch"), (app.video_tree, "library")]:
        view._presentation.observations = PresentationObservations(owner, surface)
    return owner


def stored(path, owner):
    assert owner.shutdown(2)
    payload = json.loads((path / "events.json").read_text())
    return [
        row
        for row in payload["events"]
        if row.get("feature") == "presentation_operation"
    ]


def seed_artwork(app, tmp_path, count=2):
    rows = seed(app, tmp_path, count=count)
    for row in rows:
        folder = Path(row["vodforge_output_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), "#4455cc").save(folder / "thumbnail.jpeg")
        row["title"] = "PRIVATE title"
        row["description"] = "PRIVATE source description"
    app.download_history = rows
    app._reconcile_library_projection()
    return rows


def test_cold_entry_and_invalid_control_lifetime_are_distinct_and_recover(
    application, tmp_path
):
    app = application
    owner = instrument(app, tmp_path / "events")
    seed_artwork(app, tmp_path / "media")
    app._select_focus_view("watch")
    pump(app, 0.7)
    watch = app.focus_watch
    initial = stored(tmp_path / "events", owner)
    assert any(row["dimensions"].get("artwork_state") == "pending" for row in initial)
    assert any(
        row["action"] == "settled" and row["dimensions"].get("artwork_state") == "ready"
        for row in initial
    )
    control = watch.canvas.find_withtag("presentation-control")[0]
    name = watch.canvas.itemcget(control, "image")
    watch.canvas.tk.call("image", "delete", name)
    # Exercise the actual artwork-owner observation boundary while the scene
    # remains invalid, then let the real renderer repair the same operation.
    watch._presentation_change("artwork")
    pump(app, 0.04)
    watch._queue_render()
    pump(app, 0.5)
    events = stored(tmp_path / "events", owner)
    faults = [row for row in events if row["action"] == "fault"]
    assert faults and faults[-1]["dimensions"]["missing_image_role"] == "control"
    operation = faults[-1]["dimensions"]["operation_id"]
    sequence = [
        row["action"]
        for row in events
        if row["dimensions"]["operation_id"] == operation
    ]
    assert "recovered" in sequence and sequence[-1] == "settled"
    encoded = json.dumps(events)
    assert (
        "PRIVATE" not in encoded
        and name not in encoded
        and str(tmp_path) not in encoded
    )


def test_empty_search_and_unavailable_artwork_have_explicit_population_context(
    application, tmp_path
):
    app = application
    owner = instrument(app, tmp_path / "events")
    rows = seed(app, tmp_path / "missing", count=1)
    app._select_focus_view("watch")
    watch = app.focus_watch
    pump(app, 0.5)
    watch._navigate("collections")
    pump(app, 0.3)
    watch.set_records([{**rows[0], "vodforge_user_category": "PRIVATE category"}])
    watch._mode_origin = "default"
    watch.search.set("PRIVATE query with no match")
    pump(app, 0.4)
    events = stored(tmp_path / "events", owner)
    zero_mode = [
        row
        for row in events
        if row["dimensions"].get("presentation_mode") == "collections"
        and row["dimensions"].get("mode_eligible_bucket") == "0"
    ]
    empty_query = [
        row for row in events if row["dimensions"].get("query_state") == "active"
    ]
    assert zero_mode and zero_mode[-1]["dimensions"]["query_state"] == "inactive"
    assert empty_query and empty_query[-1]["dimensions"]["mode_eligible_bucket"] == "1"
    assert empty_query[-1]["dimensions"]["matching_bucket"] == "0"
    assert any(
        row["dimensions"].get("artwork_state") == "unavailable" for row in events
    )
    assert not any(row["action"] == "fault" for row in events)
    assert "PRIVATE" not in json.dumps(events)


def test_hidden_scene_retains_live_images_and_return_settles(application, tmp_path):
    app = application
    owner = instrument(app, tmp_path / "events")
    seed_artwork(app, tmp_path / "media")
    app._select_focus_view("watch")
    pump(app, 0.6)
    app._select_focus_view("library")
    pump(app, 0.2)
    app.video_tree.navigate(None, mode="all")
    app.video_tree.navigate(None, mode="folders")
    pump(app, 0.2)
    app._select_focus_view("watch")
    pump(app, 0.4)
    events = stored(tmp_path / "events", owner)
    assert any(
        row["dimensions"].get("presentation_scene") == "retained" for row in events
    )
    assert any(
        row["dimensions"].get("presentation_surface") == "library"
        and row["dimensions"].get("mode_origin") == "user"
        for row in events
    )
    assert not any(row["action"] == "fault" for row in events)
    assert any(
        row["action"] == "settled"
        and row["dimensions"].get("presentation_surface") == "watch"
        for row in events
    )


def test_snapshot_of_5000_records_reuses_cached_mode_counts(
    application, tmp_path, monkeypatch
):
    import hashlib
    import statistics
    import time

    from yt_downloader import watch_ui

    app = application
    owner = instrument(app, tmp_path / "events")
    image = tmp_path / "synthetic.png"
    Image.new("RGB", (320, 180), "#4455cc").save(image)
    watch = app.focus_watch
    monkeypatch.setattr(watch, "_artwork_path", lambda _record: image)
    watch.set_records(
        [
            {
                "id": f"PRIVATE-{i}",
                "title": "PRIVATE saved title",
                "channel": "PRIVATE creator",
                "playlist_id": f"PRIVATE-list-{i // 20}",
                "vodforge_output_dir": str(tmp_path / f"PRIVATE-{i}"),
                "vodforge_output_path": str(tmp_path / f"PRIVATE-{i}" / "media.mp4"),
            }
            for i in range(5000)
        ]
    )
    app._select_focus_view("watch")
    pump(app, 0.9)
    assert watch._presentation_eligible == 5000
    assert watch._presentation_mode_eligible == 5000
    original = watch_ui.watch_rails

    def unexpected(*_args, **_kwargs):
        raise AssertionError("diagnostic snapshot regrouped5000records")

    monkeypatch.setattr(watch_ui, "watch_rails", unexpected)
    durations = []
    for _ in range(30):
        start = time.perf_counter()
        dimensions, _pending = watch._presentation_snapshot()
        durations.append((time.perf_counter() - start) * 1000)
        assert dimensions["eligible_bucket"] == "101_plus"
    monkeypatch.setattr(watch_ui, "watch_rails", original)
    receipt = {
        "scope": "Actual Tk canvas audit and cached population snapshot of5000synthetic records; excludes render/grouping, no physical drag/FPS claim.",
        "count": 5000,
        "samples_ms": durations,
        "median_ms": statistics.median(durations),
        "max_ms": max(durations),
        "canvas_items": len(watch.canvas.find_all()),
        "source_hashes": {
            name: hashlib.sha256(
                (Path(__file__).parents[1] / name).read_bytes()
            ).hexdigest()
            for name in [
                "yt_downloader/watch_ui.py",
                "yt_downloader/presentation_diagnostics.py",
            ]
        },
    }
    destination = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "presentation-5000-snapshot.json").write_text(
        json.dumps(receipt, indent=2)
    )
    assert statistics.median(durations) < 20
    assert owner.shutdown(2)


@pytest.fixture(autouse=True)
def legacy_folder_workspace_for_existing_contracts(application):
    """These contracts target the retained folder workspace, not the default scenes."""
    application._library_scene_action("folders", None)
    application.update()


def test_coalesced_audit_wait_is_visible_in_real_tk_and_local_outbox(
    application, tmp_path
):
    """Controlled blocked Tk pump; not compositor or physical resize latency."""
    import time

    from yt_downloader.product_telemetry import _parse_event

    app = application
    destination = tmp_path / "lag-events"
    owner = instrument(app, destination)
    seed_artwork(app, tmp_path / "lag-media", count=2)
    app._select_focus_view("watch")
    pump(app, 0.8)
    previous = stored(destination, owner)
    old_operations = {row["dimensions"]["operation_id"] for row in previous}
    probe = app.focus_watch._presentation
    probe.change("data")
    probe.schedule()
    started = time.monotonic()
    for _ in range(4):
        time.sleep(0.08)
        probe.schedule()
    blocked_ms = (time.monotonic() - started) * 1000
    pump(app, 0.12)
    events = stored(destination, owner)
    current = [
        row
        for row in events
        if row["dimensions"]["operation_id"] not in old_operations
        and row["dimensions"].get("presentation_trigger") == "data"
    ]
    observed = [row for row in current if row["action"] == "observed"]
    assert 250 <= blocked_ms < 1000, (
        "Controlled fixture did not exercise the intended wait range"
    )
    assert observed
    assert observed[0]["dimensions"]["lag_measurement"] == "ui_pump_delay"
    assert observed[0]["dimensions"]["lag_bucket"] == "250_999ms"
    assert current[-1]["action"] == "settled"
    assert "PRIVATE" not in json.dumps(current)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / "presentation-audit-wait.json").write_text(
        json.dumps(
            {
                "scope": "Production probe, real Tk timer and production local outbox under controlled blocked pump; no delivery/presentation claim",
                "blocked_ms": blocked_ms,
                "events": [_parse_event(row).public_payload() for row in current],
            },
            indent=2,
        )
    )
