"""Continuation uses the real short-workspace producer and fails closed."""

import json

import pytest
from quality_harness import packaged_e2e, util
from test_e2e_continuation import fixture


def setup_short_workspace(tmp_path, monkeypatch):
    directory, session, candidate, validation, args = fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("VODFORGE_QUALITY_WORKSPACE_ROOT", str(tmp_path))
    root = util.create_quality_workspace(directory, "original-packaged-e2e")
    artifact = root / "candidate-artifact" / "VODForge.app"
    artifact.mkdir(parents=True)
    session["state_paths"] = packaged_e2e._isolated_state_paths(root)
    session["candidate_binding"]["artifact_path"] = str(artifact)
    path = directory / "session.json"
    path.write_text(json.dumps(session))
    return directory, root, session, candidate, validation, args, path


def test_real_short_workspace_continuation_preserves_original_bytes(
    tmp_path, monkeypatch
):
    directory, _, session, _, _, args, path = setup_short_workspace(
        tmp_path, monkeypatch
    )
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    result = packaged_e2e._load_resumable_session(path, args)
    assert result["state_paths"] == session["state_paths"]
    for name, data in before.items():
        assert (directory / name).read_bytes() == data
        if name != "workspace.json":
            assert (directory / "continuation-1" / name).read_bytes() == data


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_receipt",
        "malformed_receipt",
        "foreign_root",
        "not_retained",
        "missing_run_id",
        "root_symlink",
        "receipt_symlink",
        "wrong_prefix",
        "layout",
        "candidate",
        "trace",
        "live",
        "failed_exit",
        "survivors",
        "other_output",
    ],
)
def test_short_workspace_continuation_refuses_changed_ownership(
    tmp_path, monkeypatch, invalid
):
    directory, root, session, candidate, validation, args, path = setup_short_workspace(
        tmp_path, monkeypatch
    )
    receipt = directory / "workspace.json"
    owned = json.loads(receipt.read_text())
    if invalid == "missing_receipt":
        receipt.unlink()
    elif invalid == "malformed_receipt":
        receipt.write_text("not-json")
    elif invalid in ("foreign_root", "not_retained", "missing_run_id"):
        if invalid == "foreign_root":
            owned["run_root"] = str(tmp_path / "vfq-unrelated")
        elif invalid == "not_retained":
            owned["retained_for_evidence"] = False
        else:
            owned.pop("run_id")
        receipt.write_text(json.dumps(owned))
    elif invalid == "root_symlink":
        alias = tmp_path / "vfq-symlink"
        try:
            alias.symlink_to(root, target_is_directory=True)
        except OSError:
            pytest.skip("Native symlink creation is unavailable for this account")
        session["state_paths"]["isolation_root"] = str(alias)
    elif invalid == "receipt_symlink":
        real = directory / "receipt-original.json"
        receipt.rename(real)
        try:
            receipt.symlink_to(real)
        except OSError:
            pytest.skip("Native symlink creation is unavailable for this account")
    elif invalid == "wrong_prefix":
        renamed = tmp_path / "unrelated-directory"
        root.rename(renamed)
        session["state_paths"] = packaged_e2e._isolated_state_paths(renamed)
        owned["run_root"] = str(renamed)
        receipt.write_text(json.dumps(owned))
    elif invalid == "layout":
        session["state_paths"]["home"] = str(tmp_path / "normal-home")
    elif invalid == "candidate":
        candidate["readback_verification"]["archive_sha256"] = "changed"
    elif invalid == "trace":
        validation["structural_valid"] = False
    elif invalid == "live":
        session["current_launch"] = {"pid": 123}
    elif invalid == "failed_exit":
        session["launches"][0]["returncode"] = 1
    elif invalid == "survivors":
        session["launches"][0]["group_survivors_after_exit"] = [123]
    elif invalid == "other_output":
        args.output_dir = tmp_path / "other-report"
    path.write_text(json.dumps(session))
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        packaged_e2e._load_resumable_session(path, args)
    assert not (directory / "continuation-1").exists()
    assert {
        p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()
    } == before
