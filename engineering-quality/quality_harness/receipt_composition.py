"""Compose immutable observations without rewriting their source identities.

Only qualification source and prose may differ from the signed source. Every
other tracked/nonignored input must be byte-identical, including dependencies,
packaging and workflow inputs. Runtime changes never qualify through adoption.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .source_identity import validate_manifest

FORMAT = "vodforge-profile-composition-v1"


# Reviewed dispatch-only receipts: download existing candidates and observe them.
# A name match alone must never exempt a changed build or publication workflow.
QA_WORKFLOW_HASHES = {
    ".github/workflows/macos-candidate-startup.yml": "d78d8d8214936605e6f1804a9b88a10058c77724aea3e442d4ef65d466cbcad9",
    ".github/workflows/windows-remaining-checks.yml": "41c7d3120c0835d154a6f09cf3ec5daf5fde876a8ce8ad8c8ccf7e22a8bf4b43",
}


def _qualification_only(name, entry):
    path = PurePosixPath(name)
    return (
        path.parts[0] in {"tests", "engineering-quality", "docs"}
        or path.suffix == ".md"
        or (
            name in QA_WORKFLOW_HASHES
            and entry == {"kind": "file", "sha256": QA_WORKFLOW_HASHES[name]}
        )
    )


def runtime_inputs(manifest):
    if not isinstance(manifest, Mapping) or not validate_manifest(
        manifest, manifest.get("sha256")
    ):
        raise ValueError("Missing or invalid complete source manifest")
    files = {
        k: v for k, v in manifest["files"].items() if not _qualification_only(k, v)
    }
    if not any(k.startswith("yt_downloader/") for k in files):
        raise ValueError("No product source in source manifest")
    if any(v.get("kind") == "missing" for v in files.values()):
        raise ValueError("Missing runtime input")
    return files


def read_bound(ref):
    if not isinstance(ref, Mapping) or set(ref) != {"path", "sha256"}:
        raise ValueError("Missing constituent path/hash")
    path = Path(ref["path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Constituent is not an absolute regular file")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Constituent exceeds bounded size")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise ValueError("Constituent changed")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise TypeError("Constituent is not an object")
    return value


def _source_bound(result, candidate):
    repository = result.get("repository", {})
    manifest = repository.get("source_manifest")
    target = candidate.get("source", {}).get("manifest")
    if (
        not isinstance(manifest, Mapping)
        or not isinstance(repository.get("commit"), str)
        or re.fullmatch("[0-9a-f]{40}", repository["commit"]) is None
        or repository.get("source_manifest_unchanged") is not True
        or repository.get("source_manifest_after_sha256") != manifest.get("sha256")
        or repository.get("source_manifest_sha256") != manifest.get("sha256")
        or runtime_inputs(manifest) != runtime_inputs(target)
    ):
        raise ValueError(
            "Constituent source changed or differs from signed runtime inputs"
        )


def _materialize(binding, candidate):
    source = candidate.get("source", {})
    if (
        not isinstance(candidate.get("candidate_id"), str)
        or not candidate["candidate_id"]
    ):
        raise ValueError("Missing candidate identity")
    if not validate_manifest(source.get("manifest"), source.get("manifest_sha256")):
        raise ValueError("Invalid candidate source manifest")
    if binding.get("format") != FORMAT or binding.get("candidate_id") != candidate.get(
        "candidate_id"
    ):
        raise ValueError("Composition candidate identity mismatch")
    if binding.get("candidate_source_sha256") != candidate.get("source", {}).get(
        "manifest_sha256"
    ):
        raise ValueError("Composition candidate manifest mismatch")
    if binding.get("profile") not in {"fast", "normal", "deep"}:
        raise ValueError("Unknown qualification profile")
    rows = binding.get("constituents")
    if not isinstance(rows, list) or not rows:
        raise ValueError("No composition constituents")
    selected, originals = {}, []
    for row in rows:
        original = read_bound(row.get("result"))
        _source_bound(original, candidate)
        originals.append(original)
        scenarios = original.get("scenarios")
        if not isinstance(scenarios, list):
            raise TypeError("Constituent has no scenario list")
        indexed = {s["id"]: s for s in scenarios}
        if len(indexed) != len(scenarios):
            raise ValueError("Duplicate original scenario")
        ids = row.get("scenario_ids")
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise ValueError("Missing or duplicate selected scenario")
        for sid in ids:
            if sid in selected or sid not in indexed:
                raise ValueError("Duplicate or absent selected scenario")
            selected[sid] = indexed[sid]
    return [selected[k] for k in sorted(selected)], originals


def compose_profile(candidate, profile, constituents):
    """Return a new linked receipt; never modify an original result or commit."""
    binding = {
        "format": FORMAT,
        "candidate_id": candidate.get("candidate_id"),
        "candidate_source_sha256": candidate.get("source", {}).get("manifest_sha256"),
        "profile": profile,
        "constituents": constituents,
    }
    scenarios, originals = _materialize(binding, candidate)
    return {
        "schema_version": originals[0].get("schema_version"),
        "profile": profile,
        "repository": {
            "commit": None,
            "qualification_source_commits": [
                r["repository"]["commit"] for r in originals
            ],
        },
        "source_binding": binding,
        "scenarios": scenarios,
        "findings": [
            f
            for r in originals
            for f in r.get("findings", [])
            if f.get("scenario_id") in {s["id"] for s in scenarios}
        ],
        "summary": {"scenarios": len(scenarios)},
    }


def verify_composition(result, candidate):
    try:
        binding = result["source_binding"]
        scenarios, originals = _materialize(binding, candidate)
        return (
            result.get("profile") == binding["profile"]
            and result.get("scenarios") == scenarios
            and result.get("repository")
            == {
                "commit": None,
                "qualification_source_commits": [
                    r["repository"]["commit"] for r in originals
                ],
            }
        )
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        return False
