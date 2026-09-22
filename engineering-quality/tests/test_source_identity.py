from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from quality_harness.source_identity import source_manifest


def repository(path: Path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "source.py").write_text("initial")
    subprocess.run(["git", "-C", str(path), "add", "source.py"], check=True)


def test_dirty_content_changes_identity_without_any_head_change(tmp_path):
    repository(tmp_path)
    before = source_manifest(tmp_path)
    (tmp_path / "source.py").write_text("changed")
    after = source_manifest(tmp_path)
    assert before["sha256"] != after["sha256"]
    assert before["files"].keys() == after["files"].keys()


def test_nonignored_new_files_and_tracked_deletions_are_bound(tmp_path):
    repository(tmp_path)
    initial = source_manifest(tmp_path)["sha256"]
    (tmp_path / "new file.py").write_bytes(b"new")
    changed = source_manifest(tmp_path)
    assert changed["sha256"] != initial and "new file.py" in changed["files"]
    (tmp_path / "source.py").unlink()
    deleted = source_manifest(tmp_path)
    assert deleted["sha256"] != changed["sha256"]
    assert deleted["files"]["source.py"]["kind"] == "missing"


def test_ignored_runtime_outputs_do_not_change_source_identity(tmp_path):
    repository(tmp_path)
    (tmp_path / ".gitignore").write_text("reports/\n")
    before = source_manifest(tmp_path)["sha256"]
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/out.json").write_text("runtime evidence")
    assert source_manifest(tmp_path)["sha256"] == before


def test_nested_directory_cannot_silently_hash_another_checkout(tmp_path):
    repository(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    with pytest.raises(ValueError, match="exact checkout root"):
        source_manifest(nested)


def test_source_symlink_outside_checkout_is_refused(tmp_path):
    root = tmp_path / "source"
    repository(root)
    outside = tmp_path / "outside"
    outside.write_text("not in source snapshot")
    (root / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="outside checkout"):
        source_manifest(root)


@pytest.mark.parametrize("fault", ["changed", "missing", "empty", "path", "kind"])
def test_manifest_validation_recomputes_payload(tmp_path, fault):
    from copy import deepcopy

    from quality_harness.source_identity import validate_manifest

    repository(tmp_path)
    manifest = source_manifest(tmp_path)
    expected = manifest["sha256"]
    assert validate_manifest(manifest, expected)
    invalid = deepcopy(manifest)
    if fault == "changed":
        invalid["files"]["source.py"]["sha256"] = "0" * 64
    elif fault == "missing":
        invalid.pop("sha256")
    elif fault == "empty":
        invalid["files"] = {}
    elif fault == "path":
        invalid["files"]["../escape"] = invalid["files"].pop("source.py")
    else:
        invalid["files"]["source.py"]["kind"] = "directory"
    assert not validate_manifest(invalid, expected)
