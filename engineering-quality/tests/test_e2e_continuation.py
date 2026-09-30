import json
from argparse import Namespace

import pytest
from quality_harness import candidate_artifact, packaged_e2e


def fixture(tmp_path, monkeypatch):
    directory = tmp_path / "report"
    directory.mkdir()
    root = tmp_path / ".runs" / "owned"
    artifact = root / "candidate-artifact" / "VODForge.app"
    artifact.mkdir(parents=True)
    session = {
        "session_dir": str(directory),
        "e2e_profile": "telemetry",
        "telemetry_mode": "preview",
        "session_nonce": "original",
        "current_launch": None,
        "driver_ready": False,
        "launches": [{"verified": True, "returncode": 0}],
        "state_paths": packaged_e2e._isolated_state_paths(root),
        "candidate_binding": {
            "verified": True,
            "candidate_id": "frozen",
            "archive_sha256": "zip",
            "bundle_tree_sha256": "tree",
            "artifact_path": str(artifact),
        },
        "artifact_receipt": {},
    }
    candidate = {
        "candidate_id": "frozen",
        "readback_verification": {
            "verified": True,
            "archive_sha256": "zip",
            "bundle_tree_sha256": "tree",
        },
    }
    monkeypatch.setattr(
        candidate_artifact, "load_and_verify_candidate", lambda p: candidate
    )
    monkeypatch.setattr(
        packaged_e2e, "_artifact_integrity_receipt", lambda *a: {"verified": True}
    )
    validation = {"structural_valid": True}
    monkeypatch.setattr(
        packaged_e2e, "_validate_driver_trace", lambda *a, **k: validation
    )
    (directory / "driver-events.json").write_text('{"events":["original"]}')
    (directory / "e2e-result.json").write_text('{"status":"failed"}')
    args = Namespace(
        output_dir=None,
        profile="telemetry",
        telemetry="preview",
        candidate=tmp_path / "candidate.json",
    )
    return directory, session, candidate, validation, args


@pytest.mark.parametrize(
    "invalid",
    ["live", "failed_exit", "survivors", "profile", "state", "candidate", "trace"],
)
def test_continuation_refuses_unowned_or_changed_evidence(
    tmp_path, monkeypatch, invalid
):
    directory, session, candidate, validation, args = fixture(tmp_path, monkeypatch)
    if invalid == "live":
        session["current_launch"] = {"pid": 123}
    elif invalid == "failed_exit":
        session["launches"][0]["returncode"] = 1
    elif invalid == "survivors":
        session["launches"][0]["group_survivors_after_exit"] = [123]
    elif invalid == "profile":
        args.telemetry = "off"
    elif invalid == "state":
        session["state_paths"]["home"] = str(tmp_path / "normal-home")
    elif invalid == "candidate":
        candidate["readback_verification"]["archive_sha256"] = "changed"
    elif invalid == "trace":
        validation["structural_valid"] = False
    path = directory / "session.json"
    path.write_text(json.dumps(session))
    with pytest.raises(ValueError):
        packaged_e2e._load_resumable_session(path, args)
    assert not (directory / "continuation-1").exists()
    assert json.loads(path.read_text()) == session


def test_continuation_keeps_original_failed_receipt_and_trace(tmp_path, monkeypatch):
    directory, session, _, _, args = fixture(tmp_path, monkeypatch)
    path = directory / "session.json"
    path.write_text(json.dumps(session))
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    result = packaged_e2e._load_resumable_session(path, args)
    assert result["launches"] == session["launches"]
    assert result["session_nonce"] == "original"
    for name, content in before.items():
        assert (directory / name).read_bytes() == content
        assert (directory / "continuation-1" / name).read_bytes() == content


@pytest.mark.parametrize("key", [None, "", "short", "G" * 64])
def test_refused_preview_launch_does_not_archive_or_rewrite_continuation(
    tmp_path, monkeypatch, key
):
    directory, session, _, _, args = fixture(tmp_path, monkeypatch)
    session["candidate_binding"]["artifact_policy"] = "release"
    session["fixture_manifest"] = {}
    monkeypatch.setattr(
        packaged_e2e,
        "_artifact_receipt",
        lambda *a, **k: {
            "verified": True,
            "executable": session["candidate_binding"]["artifact_path"],
            "bundle_tree": {"sha256": "tree"},
        },
    )
    monkeypatch.setattr(packaged_e2e, "preexisting_vodforge_processes", lambda p: [])
    path = directory / "session.json"
    path.write_text(json.dumps(session))
    args.resume = path
    monkeypatch.setattr(packaged_e2e.sys, "platform", "darwin")
    if key is None:
        monkeypatch.delenv("VODFORGE_QA_ACCESS_KEY", raising=False)
    else:
        monkeypatch.setenv("VODFORGE_QA_ACCESS_KEY", key)
    before = {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="requires the private QA access key"):
        packaged_e2e.run_packaged_e2e_session(
            args, repo_root=tmp_path, harness_root=tmp_path
        )
    assert not (directory / "continuation-1").exists()
    assert {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    } == before
