import copy
import hashlib
import json

import pytest
from quality_harness.receipt_composition import compose_profile, verify_composition


def manifest(files):
    data = {"format": "vodforge-source-files-v1", "files": files}
    return {
        **data,
        "sha256": hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


@pytest.fixture
def evidence(tmp_path):
    files = {
        k: {"kind": "file", "sha256": "a" * 64}
        for k in [
            "yt_downloader/main.py",
            "requirements.txt",
            "VODForge.spec",
            ".github/workflows/build.yml",
            "engineering-quality/quality_harness/release_gate.py",
            "tests/test_main.py",
        ]
    }
    target = manifest(files)
    candidate = {
        "candidate_id": "frozen-1",
        "source": {
            "commit": "a" * 40,
            "manifest": target,
            "manifest_sha256": target["sha256"],
        },
    }
    actual = copy.deepcopy(files)
    actual["engineering-quality/quality_harness/release_gate.py"]["sha256"] = "b" * 64
    observed = manifest(actual)
    original = {
        "schema_version": "1.0.0",
        "repository": {
            "commit": "b" * 40,
            "source_manifest": observed,
            "source_manifest_sha256": observed["sha256"],
            "source_manifest_after_sha256": observed["sha256"],
            "source_manifest_unchanged": True,
        },
        "scenarios": [
            {"id": "example", "status": "passed", "evidence_tier": "unit_static"}
        ],
        "findings": [],
    }
    path = tmp_path / "original.json"

    def save():
        path.write_text(json.dumps(original))
        return {
            "result": {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            "scenario_ids": ["example"],
        }

    return candidate, original, save


def test_qualification_only_change_keeps_original_commit_and_exact_scenario(evidence):
    candidate, original, save = evidence
    before = copy.deepcopy(original)
    result = compose_profile(candidate, "normal", [save()])
    assert verify_composition(result, candidate)
    assert original == before
    assert result["repository"]["commit"] is None
    assert result["repository"]["qualification_source_commits"] == ["b" * 40]
    assert result["scenarios"] == original["scenarios"]


@pytest.mark.parametrize(
    "owner",
    [
        "yt_downloader/main.py",
        "requirements.txt",
        "VODForge.spec",
        ".github/workflows/build.yml",
        "new-runtime.json",
    ],
)
def test_any_runtime_or_build_input_change_refuses_adoption(evidence, owner):
    candidate, original, save = evidence
    files = original["repository"]["source_manifest"]["files"]
    files[owner] = {"kind": "file", "sha256": "c" * 64}
    observed = manifest(files)
    original["repository"].update(
        source_manifest=observed,
        source_manifest_sha256=observed["sha256"],
        source_manifest_after_sha256=observed["sha256"],
    )
    with pytest.raises(ValueError, match="differs"):
        compose_profile(candidate, "normal", [save()])


@pytest.mark.parametrize(
    "field",
    [
        "source_manifest_sha256",
        "source_manifest_after_sha256",
        "source_manifest_unchanged",
        "commit",
    ],
)
def test_missing_source_observation_refuses(evidence, field):
    candidate, original, save = evidence
    del original["repository"][field]
    with pytest.raises(ValueError):
        compose_profile(candidate, "normal", [save()])


@pytest.mark.parametrize(
    "control",
    [
        "candidate",
        "manifest",
        "scenario_status",
        "scenario_missing",
        "source_identity",
        "profile",
        "duplicate",
        "changed_original",
        "missing_original",
    ],
)
def test_linked_receipt_cannot_be_promoted_or_substituted(evidence, control):
    candidate, _original, save = evidence
    member = save()
    result = compose_profile(candidate, "normal", [member])
    if control == "candidate":
        result["source_binding"]["candidate_id"] = "foreign"
    elif control == "manifest":
        result["source_binding"]["candidate_source_sha256"] = "0" * 64
    elif control == "scenario_status":
        result["scenarios"][0]["status"] = "failed"
    elif control == "scenario_missing":
        result["scenarios"] = []
    elif control == "source_identity":
        result["repository"]["commit"] = candidate["source"]["commit"]
    elif control == "profile":
        result["profile"] = "deep"
    elif control == "duplicate":
        result["source_binding"]["constituents"].append(member)
    elif control == "changed_original":
        from pathlib import Path

        Path(member["result"]["path"]).write_text("{}")
    elif control == "missing_original":
        from pathlib import Path

        Path(member["result"]["path"]).unlink()
    assert not verify_composition(result, candidate)


def test_original_failure_is_preserved_and_not_inferred_as_passed(evidence):
    candidate, original, save = evidence
    original["scenarios"][0]["status"] = "failed"
    result = compose_profile(candidate, "normal", [save()])
    assert verify_composition(result, candidate)
    assert result["scenarios"][0]["status"] == "failed"


@pytest.mark.parametrize(
    "control",
    ["candidate_id", "candidate_manifest", "source_manifest", "source_commit"],
)
def test_missing_or_malformed_identity_refuses_composition(evidence, control):
    candidate, original, save = evidence
    if control == "candidate_id":
        candidate["candidate_id"] = None
    elif control == "candidate_manifest":
        candidate["source"]["manifest_sha256"] = "0" * 64
    elif control == "source_manifest":
        original["repository"]["source_manifest"] = None
    elif control == "source_commit":
        original["repository"]["commit"] = "z" * 40
    with pytest.raises(ValueError):
        compose_profile(candidate, "normal", [save()])


@pytest.mark.parametrize(
    "owner",
    [
        ".github/workflows/macos-candidate-startup.yml",
        ".github/workflows/windows-remaining-checks.yml",
    ],
)
@pytest.mark.parametrize("control", ["reviewed", "changed", "symlink", "missing"])
def test_dispatch_only_workflows_require_exact_reviewed_bytes(evidence, owner, control):
    from quality_harness.receipt_composition import QA_WORKFLOW_HASHES

    candidate, original, save = evidence
    files = original["repository"]["source_manifest"]["files"]
    entry = {"kind": "file", "sha256": QA_WORKFLOW_HASHES[owner]}
    if control == "changed":
        entry["sha256"] = "c" * 64
    elif control == "symlink":
        entry["kind"] = "symlink"
    elif control == "missing":
        entry = {"kind": "missing"}
    files[owner] = entry
    observed = manifest(files)
    original["repository"].update(
        source_manifest=observed,
        source_manifest_sha256=observed["sha256"],
        source_manifest_after_sha256=observed["sha256"],
    )
    if control == "reviewed":
        assert verify_composition(
            compose_profile(candidate, "normal", [save()]), candidate
        )
    else:
        with pytest.raises(ValueError):
            compose_profile(candidate, "normal", [save()])
