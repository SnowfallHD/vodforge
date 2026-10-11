import json
from pathlib import Path

import pytest
from quality_harness.native_composition import (
    CHAINS,
    compose_native_coverage,
    compose_page_inventory,
)
from quality_harness.util import sha256_file
from test_packaged_e2e_receipts import _driver_trace
from test_receipt_composition import manifest


def bound(path, value):
    path.write_text(json.dumps(value))
    return {"path": str(path), "sha256": sha256_file(path)}


def fixture(tmp_path, names, label="one"):
    directory = tmp_path / label
    directory.mkdir()
    source = manifest({"yt_downloader/main.py": {"kind": "file", "sha256": "c" * 64}})
    candidate = {
        "verification": {"verified": True},
        "machine": {"system": "Darwin"},
        "candidate_id": "frozen",
        "artifact_policy": "release",
        "source": {
            "commit": "a" * 40,
            "manifest": source,
            "manifest_sha256": source["sha256"],
        },
        "immutable_archive": {"sha256": "d" * 64},
        "artifact": {
            "bundle_tree": {"sha256": "b" * 64},
            "executable_sha256": "e" * 64,
        },
    }
    binding = {
        "verified": True,
        "artifact_policy": "release",
        "candidate_id": "frozen",
        "source_commit": "a" * 40,
        "source_manifest_sha256": source["sha256"],
        "archive_sha256": "d" * 64,
        "bundle_tree_sha256": "b" * 64,
    }
    launch = {
        "verified": True,
        "returncode": 0,
        "launch_sequence": 1,
        "launch_id": label,
        "pid": 7001,
        "create_time": 1.0,
        "executable_sha256": "e" * 64,
        "bundle_tree_sha256": "b" * 64,
        "expected_executable": "/qa/app",
        "observed_executable": "/qa/app",
        "window_token": "VFQ-one",
        "attestation": {
            "pid": 7001,
            "session_nonce": label,
            "renderer": "qt",
            "telemetry_production": False,
            "telemetry_preview": True,
        },
    }
    trace = _driver_trace(
        directory,
        profile="telemetry",
        session_nonce=label,
        launches=[launch],
        omit=set(
            __import__(
                "quality_harness.packaged_e2e", fromlist=["TELEMETRY_UI_EVENT_ORDER"]
            ).TELEMETRY_UI_EVENT_ORDER
        )
        - set(names),
    )
    for event in trace["events"]:
        if event["screenshot"]:
            event["screenshot_sha256"] = sha256_file(Path(event["screenshot"]))
    session = {
        "candidate_binding": binding,
        "session_dir": str(directory),
        "e2e_profile": "telemetry",
        "session_nonce": label,
        "telemetry_mode": "preview",
        "launches": [launch],
    }
    receipt = {
        "candidate_binding": binding,
        "completed_at": "2026-08-30T01:00:00Z",
        "telemetry_mode": "preview",
        "artifact_integrity": {"verified": True},
        "process_provenance": {"verified": True},
        "launches": [launch],
        "driver_trace": trace,
        "scenario": {
            "status": "failed",
            "metrics": {
                "clean_exit": True,
                "harness_forced_termination": False,
                "unexpected_process_exit": False,
                "staging_residue_count": 0,
                "surviving_owned_process_count": 0,
            },
        },
    }
    row = {
        "receipt": bound(directory / "receipt.json", receipt),
        "session": bound(directory / "session.json", session),
        "trace": bound(directory / "trace.json", trace),
    }
    return candidate, row, receipt, session, trace


def test_independent_presentations_compose_without_whole_journey_or_status_rewrite(
    tmp_path,
):
    candidate, a, _, _, _ = fixture(tmp_path, ["player_features_observed"])
    _, b, _, _, _ = fixture(tmp_path, ["library_organization_observed"], "two")
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    result = compose_native_coverage(candidate, "macos", [b, a])
    assert result["covered_actions"] == [
        "library_organization_observed",
        "player_features_observed",
    ]
    assert [c["original_status"] for c in result["cohorts"]] == ["failed", "failed"]
    assert not result["native_coverage_complete"] and not result["release_acceptance"]
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


def test_causal_queue_chain_cannot_be_stitched_across_sessions(tmp_path):
    candidate, a, *_ = fixture(tmp_path, CHAINS[1][:3])
    _, b, *_ = fixture(tmp_path, CHAINS[1][3:], "two")
    result = compose_native_coverage(candidate, "macos", [a, b])
    assert not set(CHAINS[1]).intersection(result["covered_actions"])
    assert len(result["incomplete_chains"]) == 2


@pytest.mark.parametrize(
    "defect",
    [
        "hash",
        "platform",
        "candidate",
        "frame",
        "owner",
        "nonce",
        "production",
        "exit",
        "staging",
        "duplicate",
        "absent",
        "privacy",
    ],
)
def test_composition_rejects_changed_or_incompatible_native_evidence(tmp_path, defect):
    candidate, row, receipt, session, trace = fixture(
        tmp_path, ["player_features_observed"]
    )
    if defect == "hash":
        row["receipt"]["sha256"] = "wrong"
    elif defect == "platform":
        candidate["machine"]["system"] = "Windows"
    elif defect == "candidate":
        receipt["candidate_binding"]["archive_sha256"] = "changed"
    elif defect == "frame":
        Path(trace["events"][0]["screenshot"]).write_bytes(b"changed")
    elif defect == "owner":
        trace["events"][0]["window_owner_pid"] = 9999
    elif defect == "nonce":
        trace["events"][0]["session_nonce"] = "other"
    elif defect == "production":
        receipt["launches"][0]["attestation"]["telemetry_production"] = True
    elif defect == "exit":
        receipt["scenario"]["metrics"]["clean_exit"] = False
    elif defect == "staging":
        receipt["scenario"]["metrics"]["staging_residue_count"] = 1
    elif defect == "absent":
        row["actions"] = ["missing_media_recovery_observed"]
    elif defect == "privacy":
        row["snapshots"] = {
            "denied": bound(tmp_path / "denied.json", {"database_id": "production"})
        }
    if defect not in {"hash", "frame"}:
        row["receipt"] = bound(Path(row["receipt"]["path"]), receipt)
        row["session"] = bound(Path(row["session"]["path"]), session)
        row["trace"] = bound(Path(row["trace"]["path"]), trace)
    with pytest.raises(ValueError):
        compose_native_coverage(
            candidate, "macos", [row, row] if defect == "duplicate" else [row]
        )


def test_partial_causal_chain_does_not_erase_independent_observation(tmp_path):
    candidate, row, *_ = fixture(
        tmp_path, ["slow_run_started", "player_features_observed"]
    )
    result = compose_native_coverage(candidate, "macos", [row])
    assert result["covered_actions"] == ["player_features_observed"]
    assert result["incomplete_chains"][0]["missing"]


def page_fixture(tmp_path):
    _, _row, receipt, _, _ = fixture(tmp_path, ["player_features_observed"])
    launch = receipt["launches"][0]
    context = {
        "database_id": "924640fb-3be3-47ca-992c-1c7745bd8469",
        "worker": "vodforge-preview",
        "rows_written": 0,
        "candidate_binding": receipt["candidate_binding"],
        "install_id": "10000000-0000-4000-8000-000000000000",
        "read_at": "2026-08-30T00:01:00Z",
        "events": [],
        "installations": [],
        "launch": launch,
    }
    columns = ["event_id", "event_name", "platform", "dimensions", "rowid"]
    page = {
        "install_id": context["install_id"],
        "watermark": 10,
        "offset": 0,
        "total": 1,
        "read_at": "2026-08-30T00:01:00Z",
        "raw": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "success": True,
                            "meta": {"rows_written": 0},
                            "columns": columns,
                            "rows": [["id", "feature_used", "macos", "{}", 5]],
                        }
                    ),
                }
            ]
        },
    }
    return receipt, context, page


def test_original_pages_compose_inventory_but_never_become_privacy_snapshot(tmp_path):
    receipt, context, page = page_fixture(tmp_path)
    result = compose_page_inventory(
        bound(tmp_path / "context.json", context),
        [bound(tmp_path / "page.json", page)],
        receipt["candidate_binding"],
        receipt["launches"],
        "macos",
    )
    assert result["row_count"] == 1 and result["watermark"] == 10
    assert result["watermark_row_binding_verified"] is True
    assert result["complete_privacy_checkpoint"] is False


def test_missing_original_rowid_remains_explicitly_unproven(tmp_path):
    receipt, context, page = page_fixture(tmp_path)
    raw = json.loads(page["raw"]["content"][0]["text"])
    raw["columns"].pop()
    raw["rows"][0].pop()
    page["raw"]["content"][0]["text"] = json.dumps(raw)
    result = compose_page_inventory(
        bound(tmp_path / "context.json", context),
        [bound(tmp_path / "page.json", page)],
        receipt["candidate_binding"],
        receipt["launches"],
        "macos",
    )
    assert (
        not result["watermark_row_binding_verified"]
        and not result["complete_privacy_checkpoint"]
    )


@pytest.mark.parametrize(
    "defect",
    [
        "identity",
        "platform",
        "offset",
        "total",
        "write",
        "watermark",
        "duplicate",
        "source",
        "context_source",
        "truncated",
    ],
)
def test_paged_composition_rejects_incompatible_scope_and_boundaries(tmp_path, defect):
    receipt, context, page = page_fixture(tmp_path)
    raw = json.loads(page["raw"]["content"][0]["text"])
    if defect == "identity":
        page["install_id"] = "20000000-0000-4000-8000-000000000000"
    elif defect == "platform":
        raw["rows"][0][2] = "windows"
    elif defect == "offset":
        page["offset"] = 1
    elif defect == "total":
        page["total"] = 2
    elif defect == "write":
        raw["meta"]["rows_written"] = 1
    elif defect == "watermark":
        raw["rows"][0][-1] = 11
    elif defect == "source":
        raw["rows"][0][1] = "app_opened"
        raw["rows"][0][3] = json.dumps({"build_revision": "other"})
    elif defect == "context_source":
        context["candidate_binding"]["archive_sha256"] = "other"
        receipt["candidate_binding"] = dict(
            receipt["candidate_binding"], archive_sha256="d" * 64
        )
    elif defect == "truncated":
        raw["rows"][0].pop()
    page["raw"]["content"][0]["text"] = json.dumps(raw)
    refs = [bound(tmp_path / "page.json", page)]
    if defect == "duplicate":
        refs *= 2
    with pytest.raises(ValueError):
        compose_page_inventory(
            bound(tmp_path / "context.json", context),
            refs,
            receipt["candidate_binding"],
            receipt["launches"],
            "macos",
        )


def test_composition_summary_is_recomputed_and_tampered_coverage_rejected(tmp_path):
    from quality_harness.native_composition import verify_native_composition

    candidate, row, *_ = fixture(tmp_path, ["player_features_observed"])
    result = compose_native_coverage(candidate, "macos", [row])
    assert verify_native_composition(result, candidate)
    result["covered_actions"].append("restart_observed")
    result["remaining_actions"].remove("restart_observed")
    result["native_coverage_complete"] = True
    assert not verify_native_composition(result, candidate)


def updater_fixture(tmp_path):
    candidate, _row, *_ = fixture(tmp_path, ["player_features_observed"])
    candidate["artifact"]["executable_sha256"] = "e" * 64
    refs = []
    for index, repair in enumerate((False, True)):
        helper = {
            "status": "relaunched",
            "executable_sha256": "e" * 64,
            "repair": repair,
            "telemetry_permitted": True,
        }
        h = bound(tmp_path / f"helper{index}.json", helper)
        att = {
            "pid": 7001 + index,
            "executable": "/qa/app",
            "telemetry_preview": True,
            "telemetry_production": False,
        }
        a = bound(tmp_path / f"att{index}.json", att)
        frame = tmp_path / f"frame{index}.png"
        frame.write_bytes(b"original-frame")
        state = {
            "pid": att["pid"],
            "executable": "/qa/app",
            "candidate_archive_sha256": "d" * 64,
            "executable_sha256": "e" * 64,
            "attestation_path": a["path"],
            "attestation_sha256": a["sha256"],
            "attestation": att,
            "screenshot": str(frame),
            "screenshot_sha256": sha256_file(frame),
            "data_preservation": [
                {"path": "/qa/data", "sha256": "f" * 64, "observed_sha256": "f" * 64}
            ],
            "helpers": [
                {"copied_path": h["path"], "sha256": h["sha256"], "receipt": helper}
            ],
        }
        refs.append(bound(tmp_path / f"state{index}.json", state))
    proof = {
        "candidate": "a" * 40,
        "installation_id": "10000000-0000-4000-8000-000000000000",
        "evidence": refs,
    }
    return candidate, proof


def test_updater_transactions_remain_separate_from_native_privacy_or_cleanup(tmp_path):
    from quality_harness.native_composition import _update_transactions

    candidate, proof = updater_fixture(tmp_path)
    result = _update_transactions(candidate, bound(tmp_path / "proof.json", proof))
    assert result["retained"]
    assert (
        not result["telemetry_checkpoint_complete"] and not result["clean_exit_proved"]
    )


@pytest.mark.parametrize(
    "defect",
    ["candidate", "archive", "attestation", "frame", "data", "helper", "distinct"],
)
def test_updater_composition_rejects_altered_transaction_identity(tmp_path, defect):
    from quality_harness.native_composition import _update_transactions

    candidate, proof = updater_fixture(tmp_path)
    state = json.loads(Path(proof["evidence"][1]["path"]).read_text())
    if defect == "candidate":
        proof["candidate"] = "other"
    elif defect == "archive":
        state["candidate_archive_sha256"] = "other"
    elif defect == "attestation":
        state["attestation"]["telemetry_production"] = True
    elif defect == "frame":
        Path(state["screenshot"]).write_bytes(b"other")
    elif defect == "data":
        state["data_preservation"][0]["observed_sha256"] = "other"
    elif defect in {"helper", "distinct"}:
        helper = state["helpers"][0]["receipt"]
        if defect == "helper":
            helper["status"] = "failed"
        else:
            helper["repair"] = False
        ref = bound(Path(state["helpers"][0]["copied_path"]), helper)
        state["helpers"][0]["sha256"] = ref["sha256"]
    proof["evidence"][1] = bound(Path(proof["evidence"][1]["path"]), state)
    with pytest.raises(ValueError):
        _update_transactions(candidate, bound(tmp_path / "proof.json", proof))


def test_release_gate_does_not_promote_actual_partial_composition(
    tmp_path, monkeypatch
):
    from quality_harness import candidate_artifact
    from quality_harness.release_gate import evaluate_packaged_e2e_receipt

    candidate, row, *_ = fixture(tmp_path, ["player_features_observed"])
    result = compose_native_coverage(candidate, "macos", [row])
    result["candidate_ref"] = bound(tmp_path / "candidate.json", candidate)
    monkeypatch.setattr(
        candidate_artifact, "load_and_verify_candidate", lambda p: candidate
    )
    checks = evaluate_packaged_e2e_receipt(result)
    assert checks[0]["status"] == "failed"
    assert any("incomplete" in text for text in checks[0]["evidence"])


def test_complete_ui_claim_cannot_waive_core_media_restart_or_cleanup(
    tmp_path, monkeypatch
):
    from quality_harness import candidate_artifact, native_composition
    from quality_harness.release_gate import evaluate_packaged_e2e_receipt

    candidate, row, *_ = fixture(tmp_path, ["player_features_observed"])
    row["core"] = True
    result = compose_native_coverage(candidate, "macos", [row])
    result["candidate_ref"] = bound(tmp_path / "candidate.json", candidate)
    # Isolate the existing core gate: even a qualified full UI layer must not
    # supply missing independent pipeline/output/restart constituents.
    result["native_coverage_complete"] = True
    monkeypatch.setattr(
        native_composition, "verify_native_composition", lambda *a: True
    )
    monkeypatch.setattr(
        candidate_artifact, "load_and_verify_candidate", lambda p: candidate
    )
    checks = evaluate_packaged_e2e_receipt(result)
    assert checks[0]["status"] == "failed"
    assert checks[1]["status"] in {"failed", "unproven"}
    assert "restart_history_persistence_verified" in checks[1]["metrics"]["missing"]


def test_qualified_aggregate_can_use_core_without_rewriting_original_status(
    tmp_path, monkeypatch
):
    from quality_harness import candidate_artifact, native_composition
    from quality_harness.release_gate import evaluate_packaged_e2e_receipt
    from test_release_gate import _packaged_e2e

    candidate, row, original, _, _ = fixture(tmp_path, ["player_features_observed"])
    core = _packaged_e2e(candidate)
    original.update(
        {
            key: value
            for key, value in core.items()
            if key
            in {
                "artifact_integrity",
                "process_provenance",
                "library_description_visibility",
            }
        }
    )
    original["scenario"]["metrics"] = core["scenario"]["metrics"]
    original["scenario"]["metrics"]["ui_interaction_observed"] = False
    row["receipt"] = bound(Path(row["receipt"]["path"]), original)
    row["core"] = True
    # The UI composition boundary is tested separately with actual provenance;
    # this case isolates reuse of the already qualified independent core layer.
    result = {
        "format": native_composition.FORMAT,
        "platform": "macos",
        "constituents": [row],
        "native_coverage_complete": True,
        "remaining_actions": [],
        "cohorts": [{"original_status": "failed"}],
        "candidate_ref": bound(tmp_path / "candidate.json", candidate),
    }
    before = Path(row["receipt"]["path"]).read_bytes()
    monkeypatch.setattr(
        native_composition, "verify_native_composition", lambda *a: True
    )
    monkeypatch.setattr(
        candidate_artifact, "load_and_verify_candidate", lambda p: candidate
    )
    checks = evaluate_packaged_e2e_receipt(result)
    assert all(check["status"] == "passed" for check in checks)
    assert checks[0]["metrics"]["original_statuses"] == ["failed"]
    assert Path(row["receipt"]["path"]).read_bytes() == before
    assert json.loads(before)["scenario"]["status"] == "failed"


@pytest.mark.parametrize("defect", [None, "archive", "privacy", "malformed"])
def test_preview_gate_consumes_qualified_native_aggregate_without_waiving_d1(
    tmp_path, monkeypatch, defect
):
    from quality_harness import native_composition, telemetry_release
    from test_telemetry_release import (
        candidate as telemetry_candidate,
    )
    from test_telemetry_release import (
        telemetry_fixture,
    )

    candidate = telemetry_candidate()
    data = telemetry_fixture(candidate, "macos")
    data["packaged_e2e"]["scenario"]["status"] = "failed"
    data["packaged_e2e"]["driver_trace_validation"]["valid"] = False
    data["native_composition"] = {
        "platform": "macos",
        "candidate_binding": {
            "source_commit": candidate["source"]["commit"],
            "source_manifest_sha256": candidate["source"]["manifest_sha256"],
            "archive_sha256": candidate["immutable_archive"]["sha256"],
        },
    }
    if defect == "archive":
        data["native_composition"]["candidate_binding"]["archive_sha256"] = "other"
    elif defect == "privacy":
        data["snapshots"]["denied"]["clients"] = 2
    elif defect == "malformed":
        data["native_composition"] = True
    monkeypatch.setattr(
        native_composition, "release_checks", lambda d: [{"status": "passed"}]
    )
    checks = telemetry_release.release_checks([data], candidate)
    mac = next(c for c in checks if "macos" in c["id"])
    assert mac["status"] == ("passed" if defect is None else "failed")
