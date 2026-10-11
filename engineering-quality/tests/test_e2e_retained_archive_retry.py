"""A refused preflight can reuse only a byte-identical retained original archive."""

import json

import pytest
from quality_harness import packaged_e2e
from test_e2e_continuation import fixture


def retained(tmp_path, monkeypatch):
    directory, session, candidate, _, args = fixture(tmp_path, monkeypatch)
    session["candidate_binding"]["source_commit"] = "a" * 40
    candidate["source"] = {"commit": "a" * 40}
    path = directory / "session.json"
    path.write_text(json.dumps(session))
    (directory / "summary.md").write_text("Original incomplete native result\n")
    (directory / "app.stdout.log").write_text("original stdout\n")
    (directory / "app.stderr.log").write_text("original stderr\n")
    packaged_e2e._load_resumable_session(path, args)
    return directory, path, args


def test_preflight_retry_reuses_original_archive_without_rewriting(
    tmp_path, monkeypatch
):
    directory, path, args = retained(tmp_path, monkeypatch)
    before = {
        p.relative_to(directory): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in directory.rglob("*")
        if p.is_file()
    }
    result = packaged_e2e._load_resumable_session(path, args)
    assert result["continuation_receipt"] == str(
        directory / "continuation-1/e2e-result.json"
    )
    assert {
        p.relative_to(directory): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in directory.rglob("*")
        if p.is_file()
    } == before


@pytest.mark.parametrize(
    "defect",
    [
        "archive_bytes",
        "source_bytes",
        "missing",
        "extra",
        "directory",
        "archive_symlink",
        "entry_symlink",
        "source_symlink",
    ],
)
def test_retry_refuses_any_changed_archive_or_source(tmp_path, monkeypatch, defect):
    directory, path, args = retained(tmp_path, monkeypatch)
    archive = directory / "continuation-1"
    if defect == "archive_bytes":
        (archive / "summary.md").write_text("changed\n")
    elif defect == "source_bytes":
        (directory / "summary.md").write_text("changed\n")
    elif defect == "missing":
        (archive / "summary.md").unlink()
    elif defect == "extra":
        (archive / "unrelated").write_text("must remain\n")
    elif defect == "directory":
        (archive / "extra-dir").mkdir()
    else:
        target = (
            archive
            if defect == "archive_symlink"
            else (archive if defect == "entry_symlink" else directory) / "summary.md"
        )
        original = target.with_name(target.name + "-real")
        target.rename(original)
        try:
            target.symlink_to(original, target_is_directory=original.is_dir())
        except OSError:
            pytest.skip("Native symlink creation is unavailable for this account")
    before = {
        p.relative_to(directory): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in directory.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="retained continuation"):
        packaged_e2e._load_resumable_session(path, args)
    assert {
        p.relative_to(directory): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in directory.rglob("*")
        if p.is_file()
    } == before


@pytest.mark.parametrize("defect", ["missing", "changed"])
def test_continuation_requires_original_frozen_source_binding(
    tmp_path, monkeypatch, defect
):
    directory, session, candidate, _, args = fixture(tmp_path, monkeypatch)
    session["candidate_binding"]["source_commit"] = "a" * 40
    candidate["source"] = {"commit": "a" * 40}
    if defect == "missing":
        session["candidate_binding"].pop("source_commit")
    else:
        session["candidate_binding"]["source_commit"] = "b" * 40
    path = directory / "session.json"
    path.write_text(json.dumps(session))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="candidate differs"):
        packaged_e2e._load_resumable_session(path, args)
    assert path.read_bytes() == before
    assert not (directory / "continuation-1").exists()
