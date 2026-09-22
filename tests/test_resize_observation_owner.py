"""Resize telemetry retains the originating view through delayed settlement."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_product_telemetry import _permitted_installation
from yt_downloader import app as module
from yt_downloader.cloud_funnel import load_or_create_installation_state
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize(
    "origin,destination",
    [
        ("watch", "watch"),
        ("watch", "library"),
        ("library", "watch"),
        ("forge", "activity"),
        ("activity", "forge"),
        ("PRIVATE-title", "library"),
    ],
)
def test_resize_outbox_keeps_originating_view(
    tmp_path, monkeypatch, origin, destination
):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    clock = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    host = SimpleNamespace(
        product_telemetry=telemetry,
        _closing=False,
        anonymous_usage_analytics_var=SimpleNamespace(get=lambda: True),
        _focus_selected_view=origin,
        download_history=[{}] * 26,
        _resize_last_pump=10.0,
    )
    module.DownloaderApp._observe_resize_geometry(host, 1000, 700)
    clock[0] = 10.1
    module.DownloaderApp._observe_resize_geometry(host, 1100, 740)
    host._focus_selected_view = destination
    host.download_history = []
    clock[0] = 10.7
    module.DownloaderApp._observe_resize_pump(host)
    # Repeated pump work must not duplicate the settled burst.
    clock[0] = 11.0
    module.DownloaderApp._observe_resize_pump(host)
    assert telemetry.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert len(events) == 1
    payload = events[0].public_payload()
    expected = (
        origin if origin in {"watch", "library", "forge", "activity"} else "unknown"
    )
    assert payload["dimensions"]["view"] == expected
    assert payload["dimensions"]["row_count_bucket"] == "26_500"
    assert payload["dimensions"]["lag_measurement"] == "ui_pump_delay"
    assert "PRIVATE" not in json.dumps(payload)
    output = os.environ.get("VODFORGE_RESIZE_PRODUCER_FIXTURES")
    if output:
        folder = Path(output)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{expected}-{destination}.json").write_text(
            json.dumps(payload, indent=2)
        )


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("condition", ["denied", "withdrawn", "closed", "unchanged"])
def test_resize_observation_does_not_emit_without_eligible_burst(
    tmp_path, monkeypatch, condition
):
    installation = tmp_path / "installation.json"
    if condition == "denied":
        load_or_create_installation_state(installation)
    else:
        _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    clock = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    host = SimpleNamespace(
        product_telemetry=telemetry,
        _closing=False,
        anonymous_usage_analytics_var=SimpleNamespace(
            get=lambda: condition != "denied"
        ),
        _focus_selected_view="watch",
        download_history=[],
        _resize_last_pump=10.0,
    )
    module.DownloaderApp._observe_resize_geometry(host, 1000, 700)
    clock[0] = 10.1
    module.DownloaderApp._observe_resize_geometry(
        host, 1000 if condition == "unchanged" else 1100, 700
    )
    if condition == "withdrawn":
        telemetry.set_enabled(False)
    if condition == "closed":
        host._closing = True
    clock[0] = 10.7
    module.DownloaderApp._observe_resize_pump(host)
    assert telemetry.shutdown(2)
    assert _load_outbox(tmp_path / "events.json") == []
