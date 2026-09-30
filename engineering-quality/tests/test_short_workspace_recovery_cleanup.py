from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from quality_harness import cli, scenarios


def test_workspace_is_short_private_unique_and_receipted(monkeypatch, tmp_path):
    monkeypatch.delenv("VODFORGE_QUALITY_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(cli.tempfile, "gettempdir", lambda: str(tmp_path))
    report = tmp_path / ("named-worktree-" * 8) / "report"
    first = cli._create_quality_workspace(report, "first")
    second = cli._create_quality_workspace(report / "second", "second")
    assert first.parent == tmp_path
    assert first != second
    assert first.name.startswith("vfq-")
    assert first.stat().st_mode & 0o777 == 0o700
    assert len(str(first)) < len(str(report))
    assert json.loads((report / "workspace.json").read_text()) == {
        "run_id": "first",
        "run_root": str(first),
        "retained_for_evidence": True,
    }
    assert first.exists() and second.exists()


def test_explicit_workspace_parent_and_unrelated_files_preserved(monkeypatch, tmp_path):
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("keep")
    monkeypatch.setenv("VODFORGE_QUALITY_WORKSPACE_ROOT", str(tmp_path))
    root = cli._create_quality_workspace(tmp_path / "receipts", "run")
    assert root.parent == tmp_path
    assert sentinel.read_text() == "keep"
    monkeypatch.setenv("VODFORGE_QUALITY_WORKSPACE_ROOT", "relative")
    with pytest.raises(ValueError, match="must be absolute"):
        cli._create_quality_workspace(tmp_path / "receipts", "invalid")


class Child:
    pid = 12345

    def __init__(self):
        self.alive = True
        self.actions = []

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.actions.append("terminate")
        self.alive = False

    def wait(self, timeout):
        self.actions.append("wait")
        return 0

    def kill(self):
        self.actions.append("kill")
        self.alive = False


def setup_child(monkeypatch, tmp_path):
    from yt_downloader import process_lifecycle, run_state

    child = Child()
    monkeypatch.setattr(scenarios.subprocess, "Popen", lambda *_args, **_kwargs: child)
    monkeypatch.setattr(
        process_lifecycle, "process_command", lambda _pid: "owned command"
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    partial = stage / "part"
    partial.write_bytes(b"partial")
    store = SimpleNamespace(child_started=lambda *_args: None, load=dict)
    return child, store, stage, partial, process_lifecycle, run_state


def test_denied_identity_cleans_direct_child_without_alternate_probe(
    monkeypatch, tmp_path
):
    child, store, stage, partial, lifecycle, state = setup_child(monkeypatch, tmp_path)
    calls = []

    def denied(_pid):
        calls.append(_pid)
        raise lifecycle.ProcessOwnershipError("identity denied")

    monkeypatch.setattr(lifecycle, "process_command", denied)
    monkeypatch.setattr(
        state, "recover_interrupted_run", lambda *_args: pytest.fail("recovery reached")
    )
    recovered, error, recovery_reaped, trace = scenarios._recover_with_owned_child(
        store, ["fixture"], stage, partial
    )
    assert recovered == []
    assert error == "ProcessOwnershipError: identity denied"
    assert not recovery_reaped
    assert trace[-1]["owned_fixture_child_reaped"]
    assert child.actions == ["terminate", "wait"]
    assert calls == [child.pid]
    assert partial.read_bytes() == b"partial"


def test_recovery_denial_cleanup_never_counts_as_recovery_success(
    monkeypatch, tmp_path
):
    child, store, stage, partial, lifecycle, state = setup_child(monkeypatch, tmp_path)

    def denied(_store):
        raise lifecycle.ProcessOwnershipError("recovery blocked")

    monkeypatch.setattr(state, "recover_interrupted_run", denied)
    _, error, reaped, trace = scenarios._recover_with_owned_child(
        store, ["fixture"], stage, partial
    )
    assert error == "ProcessOwnershipError: recovery blocked"
    assert not reaped
    assert trace[-1]["owned_fixture_child_reaped"]
    assert child.actions == ["terminate", "wait"]


def test_success_requires_production_recovery_to_reap_child(monkeypatch, tmp_path):
    child, store, stage, partial, _lifecycle, state = setup_child(monkeypatch, tmp_path)

    def recover(_store):
        child.alive = False
        return ["recovered"]

    monkeypatch.setattr(state, "recover_interrupted_run", recover)
    recovered, error, reaped, _trace = scenarios._recover_with_owned_child(
        store, ["fixture"], stage, partial
    )
    assert recovered == ["recovered"]
    assert error is None and reaped
    assert child.actions == ["wait"]


def test_owned_cleanup_timeout_uses_only_same_handle(monkeypatch, tmp_path):
    child, store, stage, partial, lifecycle, _state = setup_child(monkeypatch, tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "process_command",
        lambda _pid: (_ for _ in ()).throw(lifecycle.ProcessOwnershipError("denied")),
    )
    waits = []

    def wait(timeout):
        waits.append(timeout)
        if len(waits) == 1:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return 0

    child.wait = wait
    _, error, reaped, trace = scenarios._recover_with_owned_child(
        store, ["fixture"], stage, partial
    )
    assert "ProcessOwnershipError" in error
    assert not reaped
    assert child.actions == ["terminate", "kill"]
    assert waits == [5, 5]
    assert trace[-1]["owned_fixture_child_reaped"]


def test_blocked_recovery_returns_explicit_failed_receipt(monkeypatch, tmp_path):
    trace = [
        {
            "owned_fixture_child_reaped": True,
            "recovery_error": "ProcessOwnershipError: denied",
        }
    ]
    monkeypatch.setattr(
        scenarios,
        "_recover_with_owned_child",
        lambda *_args: ([], "ProcessOwnershipError: denied", False, trace),
    )
    result, findings = scenarios.lifecycle_quit_restart_recovery(
        SimpleNamespace(run_root=tmp_path)
    )
    assert result["status"] == "failed"
    assert result["error"] == "ProcessOwnershipError: denied"
    assert result["metrics"] == {
        "recovery_blocked": True,
        "owned_fixture_child_reaped": True,
    }
    assert findings == []
    receipt = json.loads(Path(result["artifacts"][0]).read_text())
    assert receipt["snapshots"] == trace


def test_default_workspace_fits_previously_failed_fixture_paths(monkeypatch, tmp_path):
    from yt_downloader import app

    monkeypatch.delenv("VODFORGE_QUALITY_WORKSPACE_ROOT", raising=False)
    root = cli._create_quality_workspace(tmp_path / "external-receipt", "budget")
    metadata = {
        "id": "unicode?staging-lifecycle=successor-1",
        "title": "A long title" * 50,
        "vodforge_output_variant": "MP4 360p CTV [3a352b362be3df98]",
    }
    output = root / "cases" / "lifecycle-staging-successor" / "output"
    directory, filename = app.resolved_video_output_target(output, metadata, ".mp4")
    assert len(str(directory / filename).encode("utf-16-le")) // 2 <= 240
    assert not output.exists()
