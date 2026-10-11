"""The public boundary must recognize a typed no-video refusal, fail closed otherwise."""

import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.observation_fixtures import relocate_observation

REPO = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (REPO / "engineering-quality/tests/public_observation.json").read_text()
)


def receipt(root, invalid=None):
    raw = relocate_observation(FIXTURE["raw"], FIXTURE["old_root"], root)
    raw["failure_diagnostic"] = {
        "failure_code": "no_video_stream",
        "format_count": 1,
        "video_format_count": 0,
        "audio_format_count": 0,
        "stage": "analysis",
        "reason": "unsupported_format",
        "error_type": None,
        "http_status": None,
        "source_module": "export_planning",
        "source_scope": "first_party_frame",
        "source_line": 802,
    }
    raw["error"] = (
        "_DownloadItemExecutionError: No usable video source was found for this URL."
    )
    if invalid is not None:
        raw["failure_diagnostic"].update(invalid)
    path = root / "observation.json"
    path.write_text(json.dumps(raw))
    return dict(
        FIXTURE["scenario"],
        raw_result=str(path),
        raw_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_typed_no_video_refusal_qualifies(tmp_path):
    result = interaction_coverage(receipt(tmp_path))
    assert result["status"] == "passed", result
    assert result["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize(
    "invalid",
    [
        {"failure_code": "foreign"},
        {"reason": "unknown"},
        {"error_type": "ForeignError"},
        {"source_module": "foreign"},
        {"source_scope": "foreign"},
        {"source_line": True},
        {"source_line": 0},
        {"format_count": True},
        {"format_count": 0},
        {"video_format_count": 1},
        {"video_format_count": False},
        {"audio_format_count": 1},
        {"audio_format_count": False},
        {"stage": "transcode"},
        {"http_status": 900},
    ],
)
def test_invalid_no_video_refusal_fails_closed(tmp_path, invalid):
    assert interaction_coverage(receipt(tmp_path, invalid))["status"] == "failed"
