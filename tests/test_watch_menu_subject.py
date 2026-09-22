"""A Watch popup keeps its original subject across projection replacement."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import yt_downloader.watch_scene_ui as module


def opened_watch_menu(monkeypatch, observe=None):
    commands = {}
    menu = SimpleNamespace(
        add_command=lambda **kw: commands.update({kw["label"]: kw["command"]}),
        tk_popup=lambda *_: None,
    )
    monkeypatch.setattr(module, "ContextMenu", lambda *args, **kw: menu)
    original = {"id": "original", "vodforge_output_dir": "/synthetic/PRIVATE-original"}
    later = {"id": "later", "vodforge_output_dir": "/synthetic/PRIVATE-later"}
    calls, usage = [], []
    host = SimpleNamespace(
        _records=(original, later),
        winfo_pointerx=lambda: 0,
        winfo_pointery=lambda: 0,
        _scene_open=lambda *_: None,
        _on_usage=observe or (lambda *args: usage.append(args)),
    )
    host._on_details = lambda index: calls.append(host._records[index]["id"])
    module.WatchSceneMixin._scene_more(host, 0)
    return host, commands, calls, usage


@pytest.mark.parametrize("change", ["same", "reordered", "removed"])
def test_watch_menu_keeps_original_subject(monkeypatch, change):
    host, commands, calls, usage = opened_watch_menu(monkeypatch)
    if change == "reordered":
        host._records = tuple(reversed(host._records))
    elif change == "removed":
        host._records = host._records[1:]
    commands["View in Library"]()
    assert calls == ([] if change == "removed" else ["original"])
    assert usage == ([("watch", "details_retired")] if change == "removed" else [])


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("permission", ["allowed", "denied", "withdrawn"])
def test_retired_watch_subject_observation_uses_real_consent_outbox(
    monkeypatch, tmp_path, permission
):
    from tests.test_product_telemetry import _permitted_installation
    from yt_downloader.cloud_funnel import load_or_create_installation_state
    from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

    installation = tmp_path / "installation.json"
    if permission == "denied":
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
    if permission == "withdrawn":
        telemetry.set_enabled(False)
    host, commands, calls, _usage = opened_watch_menu(
        monkeypatch, telemetry.record_feature
    )
    host._records = host._records[1:]
    commands["View in Library"]()
    commands["View in Library"]()
    assert calls == []
    telemetry.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert len(events) == (1 if permission == "allowed" else 0)
    if events:
        payload = events[0].public_payload()
        assert payload["feature"] == "watch" and payload["action"] == "details_retired"
        assert "PRIVATE" not in json.dumps(payload)
        output = os.environ.get("VODFORGE_WATCH_RETIRED_FIXTURE")
        if output:
            Path(output).write_text(json.dumps(payload, indent=2))
