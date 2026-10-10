import json
from pathlib import PurePosixPath, PureWindowsPath

import pytest
from quality_harness.observation_fixtures import relocate_observation


@pytest.mark.parametrize(
    "destination",
    [
        PurePosixPath('/tmp/QA "quoted" 日本語'),
        PureWindowsPath('C:/Users/QA "quoted" 日本語'),
    ],
)
def test_relocation_serializes_paths_without_corrupting_bound_fixture_values(
    destination,
):
    original = {
        "path": "/recorded/root/child/cases.json",
        "command": ["--junitxml=/recorded/root/cases.xml"],
        "files": {"tests/test_case.py": "unchanged digest"},
        "provider": "https://example.test/video",
        "status": None,
        "message": "Destination: /recorded/root\nDone",
    }
    moved = relocate_observation(original, "/recorded/root", destination)
    decoded = json.loads(json.dumps(moved))
    assert decoded["path"] == str(destination / "child" / "cases.json")
    assert decoded["command"] == ["--junitxml=" + str(destination / "cases.xml")]
    assert decoded["files"] == original["files"]
    assert decoded["provider"] == original["provider"]
    assert decoded["status"] is None
    assert decoded["message"] == f"Destination: {destination}\nDone"
    assert original["path"] == "/recorded/root/child/cases.json"
    assert moved is not original and moved["command"] is not original["command"]
