"""Actual private entrypoint must reject gaps before filesystem promotion."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from quality_harness import private_review


@pytest.mark.parametrize(
    "fault,reason",
    [
        (
            "enrollment",
            "normal.interaction.reliability.cancel_during_slow_download:unproven",
        ),
        ("negative_control", "private.negative_controls_missing"),
        ("source", "private.source_binding"),
        ("artifact", "packaged_e2e.candidate_binding:failed"),
        ("skipped", "normal.scenario.reliability.cancel_during_slow_download:skipped"),
        ("user_defect", "private.open_user_defect:resize-live-layout"),
    ],
)
def test_private_entrypoint_blocks_before_extraction_or_install(
    tmp_path, monkeypatch, fault, reason
):
    source = "a" * 40
    candidate = {
        "candidate_id": "test-candidate",
        "source": {"commit": source},
        "immutable_archive": {"sha256": "b" * 64},
        "artifact": {"bundle_tree": {"sha256": "c" * 64}},
    }
    normal = {
        "profile": "normal",
        "repository": {"commit": source},
        "scenarios": [
            {
                "id": "reliability.cancel_during_slow_download",
                "status": "passed",
                "evidence": ["Final state succeeded"],
            }
        ],
    }
    packaged = {
        "candidate_binding": {
            "candidate_id": "test-candidate",
            "archive_sha256": "b" * 64,
            "bundle_tree_sha256": "c" * 64,
            "source_commit": source,
            "verified": True,
        }
    }
    negatives = {
        "source_commit": source,
        "controls": [
            {
                "requirement_id": "resize-live-layout",
                "status": "detected",
                "failure_kind": "behavioral_assertion",
                "evidence_sha256": "d" * 64,
            }
        ],
    }
    ledger = {
        "schema_version": 1,
        "defects": [
            {
                "id": "resize-live-layout",
                "status": "verified_closed",
                "verified_source_commit": source,
            }
        ],
    }
    if fault == "negative_control":
        negatives["controls"] = []
    elif fault == "source":
        normal["repository"]["commit"] = "e" * 40
    elif fault == "artifact":
        packaged["candidate_binding"]["archive_sha256"] = "e" * 64
    elif fault == "skipped":
        normal["scenarios"][0]["status"] = "skipped"
    elif fault == "user_defect":
        ledger["defects"][0]["status"] = "open"

    harness = tmp_path / "harness"
    (harness / "acceptance").mkdir(parents=True)
    (harness / "acceptance/user-reported-defects.json").write_text(json.dumps(ledger))
    args = SimpleNamespace(
        candidate=tmp_path / "candidate.json", target=tmp_path / "VODForge.app"
    )
    args.candidate.write_text(json.dumps(candidate))
    args.target.mkdir()
    (args.target / "untouched").write_text("known installed bytes")
    for name, value in (
        ("normal_result", normal),
        ("e2e_result", packaged),
        ("negative_controls", negatives),
    ):
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(value))
        setattr(args, name, path)
    monkeypatch.setattr(
        private_review, "load_and_verify_candidate", lambda _path: candidate
    )
    calls = []
    monkeypatch.setattr(
        private_review,
        "materialize_candidate_for_e2e",
        lambda *_: calls.append("extract"),
    )
    with pytest.raises(RuntimeError) as error:
        private_review.install_private_review(args, harness_root=harness)
    assert reason in str(error.value)
    assert calls == []
    assert (args.target / "untouched").read_text() == "known installed bytes"
    assert list(tmp_path.glob(".private-review-*")) == []
    assert list(tmp_path.glob("*.previous-*")) == []


def valid_private_inputs(monkeypatch):
    """Isolate private boundary checks from unfinished domain enrollment.

    All existing NORMAL/packaged checks are real. Temporal and usability coverage reviews
    remain controlled dependencies here; this is not full-harness acceptance.
    """
    import hashlib

    from test_release_gate import _candidate, _engineering_result, _packaged_e2e

    payload = {
        "format": "vodforge-source-files-v1",
        "files": {
            "main.py": {
                "kind": "file",
                "sha256": hashlib.sha256(b"fixture source").hexdigest(),
            }
        },
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = {**payload, "sha256": digest}
    candidate = _candidate(policy="development")
    candidate["source"]["manifest"] = manifest
    candidate["source"]["manifest_sha256"] = digest
    normal = _engineering_result("normal")
    normal["repository"]["source_manifest_sha256"] = digest
    normal["repository"]["source_manifest_unchanged"] = True
    normal["repository"]["source_manifest"] = manifest
    packaged = _packaged_e2e(candidate)
    packaged["candidate_binding"]["source_commit"] = "a" * 40
    packaged["candidate_binding"]["source_manifest_sha256"] = digest
    negatives = {
        "source_commit": "a" * 40,
        "fixed_source_manifest_sha256": digest,
        "controls": [
            {
                "requirement_id": "resize-live-layout",
                "status": "detected",
                "failure_kind": "behavioral_assertion",
                "evidence_sha256": "d" * 64,
            }
        ],
    }
    ledger = {
        "schema_version": 1,
        "defects": [
            {
                "id": "resize-live-layout",
                "status": "verified_closed",
                "verified_source_commit": "a" * 40,
                "verified_source_manifest_sha256": digest,
            }
        ],
    }
    real = private_review.evaluate_engineering_result

    def enrolled(result, **kwargs):
        checks = real(result, **kwargs)
        return [
            {**check, "status": "passed"}
            if any(kind in check["id"] for kind in (".interaction.", ".usability."))
            else check
            for check in checks
        ]

    monkeypatch.setattr(private_review, "evaluate_engineering_result", enrolled)
    return candidate, normal, packaged, negatives, ledger


def test_private_validation_has_positive_control_for_otherwise_valid_inputs(
    monkeypatch,
):
    values = valid_private_inputs(monkeypatch)
    assert private_review.review_failures(*values) == []


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("negative_control", "private.negative_controls_missing"),
        ("source", "private.source_binding"),
        ("dirty_snapshot", "private.normal_source_manifest_binding"),
        ("artifact", "packaged_e2e.candidate_binding:failed"),
        ("skipped", "normal.scenario.reliability.cancel_during_slow_download:skipped"),
        ("user_defect", "private.open_user_defect:resize-live-layout"),
    ],
)
def test_private_constraints_fail_independently_from_valid_control(
    tmp_path, monkeypatch, fault, reason
):
    candidate, normal, packaged, negatives, ledger = valid_private_inputs(monkeypatch)
    assert (
        private_review.review_failures(candidate, normal, packaged, negatives, ledger)
        == []
    )
    if fault == "negative_control":
        negatives["controls"] = []
        expected = {
            reason,
            "private.defect_negative_control_missing:resize-live-layout",
        }
    else:
        expected = {reason}
    if fault == "source":
        normal["repository"]["commit"] = "e" * 40
    elif fault == "dirty_snapshot":
        normal["repository"]["source_manifest_sha256"] = "e" * 64
    elif fault == "artifact":
        packaged["candidate_binding"]["archive_sha256"] = "e" * 64
    elif fault == "skipped":
        next(
            s
            for s in normal["scenarios"]
            if s["id"] == "reliability.cancel_during_slow_download"
        )["status"] = "skipped"
    elif fault == "user_defect":
        ledger["defects"][0]["status"] = "open"
    assert (
        set(
            private_review.review_failures(
                candidate, normal, packaged, negatives, ledger
            )
        )
        == expected
    )
    harness = tmp_path / "harness"
    (harness / "acceptance").mkdir(parents=True)
    (harness / "acceptance/user-reported-defects.json").write_text(json.dumps(ledger))
    args = SimpleNamespace(
        candidate=tmp_path / "candidate.json", target=tmp_path / "VODForge.app"
    )
    args.candidate.write_text(json.dumps(candidate))
    args.target.mkdir()
    (args.target / "original").write_text("preserved")
    for name, payload in (
        ("normal_result", normal),
        ("e2e_result", packaged),
        ("negative_controls", negatives),
    ):
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(payload))
        setattr(args, name, path)
    monkeypatch.setattr(
        private_review, "load_and_verify_candidate", lambda _: candidate
    )
    extracted = []
    monkeypatch.setattr(
        private_review,
        "materialize_candidate_for_e2e",
        lambda *_: extracted.append(True),
    )
    with pytest.raises(RuntimeError) as error:
        private_review.install_private_review(args, harness_root=harness)
    assert str(error.value) == "Private installation blocked: " + "; ".join(
        private_review.review_failures(candidate, normal, packaged, negatives, ledger)
    )
    assert not extracted
    assert (args.target / "original").read_text() == "preserved"


@pytest.mark.parametrize("swap_candidate", [False, True])
def test_isolated_install_has_positive_control_and_rejects_candidate_swap(
    tmp_path, monkeypatch, swap_candidate
):
    from copy import deepcopy

    from quality_harness.util import sha256_file
    from test_negative_controls import trace

    candidate, normal, packaged, negatives, ledger = valid_private_inputs(monkeypatch)
    evidence = trace()
    evidence["source_manifest_sha256"] = "0" * 64
    evidence["renders"][1]["images"].append({"bbox": [20, 20, 60, 60]})
    evidence_path = tmp_path / "known-bad.json"
    evidence_path.write_text(json.dumps(evidence))
    negatives["controls"] = [
        {
            "requirement_id": "channels-duplicate-artwork",
            "status": "detected",
            "failure_kind": "behavioral_assertion",
            "evidence_path": str(evidence_path),
            "evidence_sha256": sha256_file(evidence_path),
            "known_bad_source_manifest_sha256": "0" * 64,
            "evaluator": "native_channels_v1",
        }
    ]
    ledger["defects"][0]["id"] = "channels-duplicate-artwork"
    harness = tmp_path / "harness"
    (harness / "acceptance").mkdir(parents=True)
    (harness / "acceptance/user-reported-defects.json").write_text(json.dumps(ledger))
    args = SimpleNamespace(
        candidate=tmp_path / "candidate.json", target=tmp_path / "VODForge.app"
    )
    args.candidate.write_text(json.dumps(candidate))
    args.target.mkdir()
    (args.target / "old").write_text("original")
    data = tmp_path / "user-data"
    data.mkdir()
    (data / "history").write_text("untouched")
    for name, payload in (
        ("normal_result", normal),
        ("e2e_result", packaged),
        ("negative_controls", negatives),
    ):
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(payload))
        setattr(args, name, path)
    refreshed = deepcopy(candidate)
    if swap_candidate:
        refreshed["source"]["manifest_sha256"] = "e" * 64
    reads = iter([candidate, refreshed])
    monkeypatch.setattr(
        private_review, "load_and_verify_candidate", lambda _: next(reads)
    )

    def materialize(_receipt, stage):
        # Exact-archive extraction has its own existing tests. Exercise the real
        # private namespace mutation using only an isolated synthetic app tree.
        artifact = stage / "VODForge.app"
        artifact.mkdir(parents=True)
        (artifact / "new").write_text("candidate")
        return artifact, {
            "candidate_id": candidate["candidate_id"],
            "source_commit": candidate["source"]["commit"],
            "source_manifest_sha256": candidate["source"]["manifest_sha256"],
            "archive_sha256": candidate["immutable_archive"]["sha256"],
            "bundle_tree_sha256": candidate["artifact"]["bundle_tree"]["sha256"],
            "receipt_sha256": sha256_file(args.candidate),
        }

    monkeypatch.setattr(private_review, "materialize_candidate_for_e2e", materialize)
    if swap_candidate:
        with pytest.raises(RuntimeError, match="candidate changed after preflight"):
            private_review.install_private_review(args, harness_root=harness)
        assert (args.target / "old").read_text() == "original"
        assert not list(tmp_path.glob("*.previous-*.app"))
    else:
        assert private_review.install_private_review(args, harness_root=harness) == 0
        assert (args.target / "new").read_text() == "candidate"
        backups = list(tmp_path.glob("*.previous-*.app"))
        assert len(backups) == 1 and (backups[0] / "old").read_text() == "original"
    assert (data / "history").read_text() == "untouched"


def test_manifest_payload_cannot_change_under_matching_labels(monkeypatch):
    from copy import deepcopy

    values = list(valid_private_inputs(monkeypatch))
    assert private_review.review_failures(*values) == []
    values[0] = deepcopy(values[0])
    values[0]["source"]["manifest"]["files"]["main.py"]["sha256"] = "0" * 64
    assert private_review.review_failures(*values) == [
        "private.candidate_source_manifest_invalid"
    ]
