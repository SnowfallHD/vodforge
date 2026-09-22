"""Evidence must bind the actual source, including snapshots within other repos."""

import subprocess

import pytest
from quality_harness.diagnostic_pipeline import source_snapshot


def test_frozen_snapshot_inside_parent_git_has_nonempty_local_inventory(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text("frozen/\n")
    child = tmp_path / "frozen"
    child.mkdir()
    ignored = subprocess.run(
        ["git", "check-ignore", "frozen/"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 0
    (child / "owner.py").write_text("first")
    result = source_snapshot(child)
    assert result["inventory"] == "directory"
    assert set(result["files"]) == {"owner.py"}
    (child / "owner.py").write_text("second")
    assert source_snapshot(child)["files"] != result["files"]


def test_new_source_files_change_frozen_inventory(tmp_path):
    (tmp_path / "owner.py").write_text("first")
    before = source_snapshot(tmp_path)
    (tmp_path / "new.py").write_text("new code")
    assert source_snapshot(tmp_path)["files"] != before["files"]


def test_empty_source_inventory_is_rejected(tmp_path):
    with pytest.raises(AssertionError, match="empty"):
        source_snapshot(tmp_path)


def test_generated_caches_and_dependency_symlinks_are_excluded(tmp_path):
    (tmp_path / "owner.py").write_text("code")
    generated = tmp_path / "__pycache__"
    generated.mkdir()
    (generated / "owner.pyc").write_bytes(b"cache")
    hypothesis = tmp_path / ".hypothesis"
    hypothesis.mkdir()
    (hypothesis / "example.json").write_text("generated test data")
    dependencies = tmp_path.parent / (tmp_path.name + "-dependencies")
    dependencies.mkdir()
    (dependencies / "dependency.js").write_text("dependency")
    (tmp_path / "node_modules").symlink_to(dependencies, target_is_directory=True)
    assert set(source_snapshot(tmp_path)["files"]) == {"owner.py"}


def test_requested_source_must_match_loaded_runtime_before_starting_transport(tmp_path):
    from quality_harness.diagnostic_pipeline import pipeline

    with pytest.raises(AssertionError, match="runtime does not match"):
        pipeline(tmp_path, tmp_path, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_imported_desktop_must_match_runtime_before_starting_transport(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from quality_harness import diagnostic_pipeline

    from yt_downloader import product_telemetry

    monkeypatch.setattr(
        product_telemetry,
        "__file__",
        str(tmp_path / "other" / "yt_downloader" / "product_telemetry.py"),
    )
    root = Path(diagnostic_pipeline.__file__).resolve().parents[2]
    with pytest.raises(AssertionError, match="Imported desktop"):
        diagnostic_pipeline.pipeline(root, tmp_path, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_real_git_root_inventory_handles_nul_delimited_tracked_and_untracked_paths(
    tmp_path,
):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "tracked source.py").write_text("committed code")
    subprocess.run(
        ["git", "add", "tracked source.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "-m",
            "Synthetic source inventory fixture",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "untracked source.py").write_text("new code")
    result = source_snapshot(tmp_path)
    assert result["inventory"] == "git"
    assert set(result["files"]) == {"tracked source.py", "untracked source.py"}
    assert result["base_commit"]
