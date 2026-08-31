from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_harness.scenarios import packaged_e2e_placeholder


def _receipt() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "started_at": "2026-08-31T00:00:00Z",
        "completed_at": "2026-08-31T00:01:00Z",
        "scenario": {
            "id": "packaged_app_e2e.full_journey",
            "evidence_tier": "packaged_app_e2e",
            "status": "passed",
            "metrics": {},
            "evidence": ["complete journey"],
            "artifacts": [],
        },
        "artifact_receipt": {
            "executable_sha256": "a" * 64,
            "policy_verified": True,
            "bundle_tree": {"sha256": "b" * 64},
        },
        "candidate_binding": {
            "verified": True,
            "candidate_id": "candidate",
            "archive_sha256": "c" * 64,
            "bundle_tree_sha256": "b" * 64,
        },
        "artifact_integrity": {"verified": True},
        "process_provenance": {"verified": True},
        "driver_trace": {"events": []},
        "driver_trace_validation": {
            "provenance_required": True,
            "invalid_provenance_events": [],
        },
        "launches": [],
        "findings": [],
    }


def test_packaged_receipt_import_requires_candidate_and_process_provenance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "e2e-result.json"
    payload = _receipt()
    path.write_text(json.dumps(payload), encoding="utf-8")

    scenario, findings = packaged_e2e_placeholder(path)
    assert scenario["status"] == "passed"
    assert scenario["metrics"]["receipt_valid"] is True
    assert findings == []

    payload["candidate_binding"]["verified"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    rejected, rejected_findings = packaged_e2e_placeholder(path)
    assert rejected["status"] == "error"
    assert "immutable candidate" in " ".join(rejected["evidence"])
    assert rejected_findings
