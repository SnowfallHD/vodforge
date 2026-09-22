"""Evidence visibility never upgrades overwritten files into valid observations."""

import json

from quality_harness.native_reports import (
    artifact_snapshot,
    changed_artifacts,
    verify_artifacts,
)


def test_each_check_indexes_its_own_changed_artifacts_and_detects_later_overwrite(
    tmp_path,
):
    old = tmp_path / "earlier.json"
    old.write_text('{"earlier": true}')
    before = artifact_snapshot(tmp_path)
    capture = tmp_path / "during.txt"
    capture.write_text("actual pressed frame evidence")
    first = changed_artifacts(tmp_path, before)
    assert [row["path"] for row in first] == ["during.txt"]
    assert first[0]["bytes"] == capture.stat().st_size
    assert changed_artifacts(tmp_path, artifact_snapshot(tmp_path)) == []
    rows = [{"nodeid": "test_control[first]", "artifacts": first}]
    assert verify_artifacts(tmp_path, rows)[0]["artifacts"][0]["integrity"] == "intact"
    capture.write_text("different later case bytes")
    assert (
        verify_artifacts(tmp_path, rows)[0]["artifacts"][0]["integrity"]
        == "changed_after_test"
    )
    capture.unlink()
    assert verify_artifacts(tmp_path, rows)[0]["artifacts"][0]["integrity"] == "missing"
    # Detection must not rewrite the recorded original identity.
    assert "integrity" not in first[0]


def test_native_evidence_index_does_not_recursively_index_its_own_output(tmp_path):
    for name in (
        "native-evidence.json",
        "native-evidence.jsonl",
        "native-results.jsonl",
        "native-source-before.json",
        "native-source-after.json",
    ):
        (tmp_path / name).write_text(json.dumps({"status": "passed"}))
    assert artifact_snapshot(tmp_path) == {}
    folder = tmp_path / "actual-interaction"
    folder.mkdir()
    (folder / "before.json").write_text('{"observed": 0}')
    artifacts = changed_artifacts(tmp_path, {})
    assert [row["path"] for row in artifacts] == ["actual-interaction/before.json"]
    assert len(artifacts[0]["sha256"]) == 64
