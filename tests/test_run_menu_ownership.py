"""Run-menu commands cannot migrate to a successor run while a popup is open."""

from dataclasses import replace
from types import MethodType, SimpleNamespace

import pytest

from tests.test_run_identity import make_job
from yt_downloader import app as module


class Menu:
    def __init__(self, *args, **kwargs):
        self.commands = {}

    def add_command(self, *, label, command):
        self.commands[label] = command

    def add_separator(self):
        pass

    def tk_popup(self, *_args):
        pass

    def grab_release(self):
        pass


@pytest.mark.parametrize(
    "label", ["Cancel run", "Skip current item", "Skip current source URL"]
)
@pytest.mark.parametrize(
    "transition", ["same", "successor", "finished", "equal_copy", "stale_at_open"]
)
def test_open_run_menu_cannot_control_another_execution(
    monkeypatch, tmp_path, label, transition
):
    menus = []

    def construct(*args, **kwargs):
        menu = Menu(*args, **kwargs)
        menus.append(menu)
        return menu

    monkeypatch.setattr(module, "ContextMenu", construct)
    original = make_job(tmp_path)
    calls = []
    app = SimpleNamespace(
        active_job=original,
        _youtube_url_for_run_record=lambda _: "",
        _select_focus_view=lambda _: None,
        winfo_pointerx=lambda: 0,
        winfo_pointery=lambda: 0,
    )
    for name in ("_cancel", "_skip_video", "_skip_url"):
        setattr(app, name, lambda action=name: calls.append((action, app.active_job)))
    if hasattr(module.DownloaderApp, "_run_focus_active_action"):
        app._run_focus_active_action = MethodType(
            module.DownloaderApp._run_focus_active_action, app
        )
    record = {"kind": "active", "job": original, "run_id": original.run_id}
    if transition == "stale_at_open":
        app.active_job = replace(original, run_id="successor")
    module.DownloaderApp._show_focus_run_actions_menu(app, record)
    command = menus[-1].commands[label]
    if transition == "successor":
        app.active_job = replace(original, run_id="successor")
    elif transition == "finished":
        app.active_job = None
    elif transition == "equal_copy":
        app.active_job = replace(original)
    # Mutable render dictionaries are not authority at the commit boundary.
    record["job"] = app.active_job
    command()
    assert len(calls) == (1 if transition == "same" else 0)
    if calls:
        assert calls[0][1] is original


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("permission", ["allowed", "denied", "withdrawn"])
@pytest.mark.parametrize("retired", [False, True])
@pytest.mark.parametrize("action", ["cancel", "skip_item", "skip_source"])
def test_run_control_producer_outbox_consent_and_private_content(
    tmp_path, permission, retired, action
):
    import json
    import os
    from pathlib import Path

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
    job = make_job(tmp_path / "PRIVATE media folder")
    calls = []
    app = SimpleNamespace(
        active_job=None if retired else job,
        product_telemetry=telemetry,
        _cancel=lambda: calls.append("cancel"),
        _skip_video=lambda: calls.append("skip_item"),
        _skip_url=lambda: calls.append("skip_source"),
    )
    module.DownloaderApp._run_focus_active_action(app, job, action)
    assert calls == ([] if retired else [action])
    telemetry.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert len(events) == (1 if permission == "allowed" else 0)
    if events:
        event = events[0]
        assert event.feature == "run_control_operation"
        assert event.action == ("rejected" if retired else "admitted")
        assert event.dimensions["run_control_action"] == action
        payload = event.public_payload()
        assert "PRIVATE" not in json.dumps(payload)
        assert job.url not in json.dumps(payload) and job.run_id not in json.dumps(
            payload
        )
        output = os.environ.get("VODFORGE_RUN_CONTROL_FIXTURE_DIR")
        if output:
            folder = Path(output)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{action}-{retired}.json").write_text(
                json.dumps(payload, indent=2)
            )


@pytest.mark.parametrize("retired", [False, True])
def test_observation_failure_cannot_change_run_control_admission(tmp_path, retired):
    def unavailable(*args, **kwargs):
        raise OSError("PRIVATE transport failure")

    job = make_job(tmp_path)
    calls = []
    app = SimpleNamespace(
        active_job=None if retired else job,
        product_telemetry=SimpleNamespace(record_operation=unavailable),
        _cancel=lambda: calls.append("cancel"),
        _skip_video=lambda: None,
        _skip_url=lambda: None,
    )
    module.DownloaderApp._run_focus_active_action(app, job, "cancel")
    assert calls == ([] if retired else ["cancel"])
