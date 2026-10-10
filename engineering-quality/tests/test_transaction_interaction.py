"""Independent transaction review rejects missing and foreign actual outcomes."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

FIXTURES = json.loads(
    Path(__file__).with_name("transaction_observations.json").read_text()
)
COMMON = [
    "foreign_identity",
    "foreign_contract",
    "missing_trace",
    "reversed_trace",
    "missing_clock",
    "wrong_phase",
]
BATCH = [
    "foreign_owner",
    "wrong_source",
    "prior_worker",
    "prior_event",
    "early_dispatch",
    "early_error",
    "changed_report",
    "escaped_report",
    "missing_report",
    "missing_error",
    "duplicate_error",
    "wrong_error",
    "false_completion",
    "later_dispatch",
]
RESTART = [
    "foreign_pid",
    "foreign_command",
    "unrecorded_child",
    "escaped_partial",
    "missing_partial",
    "no_active_stage",
    "not_active",
    "live_child_after_recovery",
    "stage_after_recovery",
    "active_after_recovery",
    "failed_instead_of_paused",
    "changed_settings",
    "changed_manual_selection",
    "changed_destination",
    "reordered_queue",
    "public_settings",
    "escaped_settings",
    "settings_after_changed",
    "journal_survives_removal",
    "stage_survives_removal",
    "cleanup_masks_child",
    "recovery_error",
    "missing_fast_stop",
    "merged_fast_stop",
    "wrong_fast_stop_status",
]
STAGING = [
    "wrong_renderer",
    "missing_constituent",
    "changed_constituent",
    "foreign_constituent",
    "foreign_origin_owner",
    "foreign_execution_owner",
    "foreign_terminal_id",
    "same_parent_id",
    "foreign_source",
    "missing_terminal",
    "duplicate_terminal",
    "wrong_terminal_status",
    "wrong_terminal_message",
    "early_terminal",
    "late_skip_request",
    "no_downloading",
    "wrong_control",
    "shared_transaction_owner",
    "different_destination",
    "escaped_transfer",
    "foreign_worker_control",
    "prior_media",
    "stage_residue",
    "emergency_cleanup",
    "observer_leak",
    "unreadable_commit",
    "foreign_worker_clock",
    "idle_root_survives",
    "active_stage_removed",
    "sentinel_changed",
    "saved_media_changed",
    "history_not_removed",
    "owner_cleanup_failed",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    return {"path": str(path), "sha256": sha(path)}


def controls(scenario):
    return COMMON + (
        BATCH
        if scenario["id"].startswith("reliability")
        else RESTART
        if "restart" in scenario["id"]
        else STAGING
    )


def mutate(scenario, raw, name, directory):
    key = (
        "observations"
        if scenario["id"].startswith("reliability")
        else "snapshots"
        if "restart" in scenario["id"]
        else "transaction_trace"
    )
    if name == "foreign_identity":
        raw["scenario_id"] = "other"
    elif name == "foreign_contract":
        raw["contract"] = "other"
    elif name == "missing_trace":
        del raw[key]
    elif name == "reversed_trace":
        raw[key].reverse()
    elif name == "missing_clock":
        del raw[key][0]["elapsed_seconds"]
    elif name == "wrong_phase":
        raw[key][0]["phase"] = "other"
    elif scenario["id"].startswith("reliability"):
        before, refused, after = raw[key]
        if name == "foreign_owner":
            refused["run_id"] = "other"
        elif name == "wrong_source":
            raw["job"]["urls"][1] = "https://example.invalid/other"
        elif name == "prior_worker":
            before["processed"] = ["media"]
        elif name == "prior_event":
            before["events"] = [["complete", None]]
        elif name == "early_dispatch":
            refused["processed"] = ["media"]
        elif name == "early_error":
            refused["events"] = [["error", "old"]]
        elif name == "changed_report":
            after["report"]["sha256"] = "0" * 64
        elif name == "escaped_report":
            for row in raw[key]:
                row["report"]["path"] = "/foreign/batch-url-failures.txt"
        elif name == "missing_report":
            del before["report"]
        elif name == "missing_error":
            after["events"] = []
        elif name == "duplicate_error":
            after["events"] *= 2
        elif name == "wrong_error":
            after["events"] = [["error", "Other failure"]]
        elif name == "false_completion":
            after["events"].append(["complete", None])
        elif name == "later_dispatch":
            after["processed"] = ["media"]
    elif "restart" in scenario["id"]:
        launched, before, during, after = raw[key][:4]
        terminal = raw["paused_store"]["recovered_failures"][0]
        if name == "foreign_pid":
            before["child_pid"] += 1
        elif name == "foreign_command":
            before["child_command"] += "other"
        elif name == "unrecorded_child":
            before["run_state"]["children"] = []
        elif name == "escaped_partial":
            launched["child_argv"][-1] = "/foreign/partial"
            before["child_command"] = " ".join(launched["child_argv"])
            before["run_state"]["children"][0]["argv"] = launched["child_argv"]
        elif name == "missing_partial":
            before["partial_size"] = 0
        elif name == "no_active_stage":
            before["stage_exists"] = False
        elif name == "not_active":
            before["run_state"]["state"] = "idle"
        elif name == "live_child_after_recovery":
            during["child_command"] = before["child_command"]
        elif name == "stage_after_recovery":
            during["stage_exists"] = True
        elif name == "active_after_recovery":
            during["run_state"]["state"] = "active"
        elif name == "failed_instead_of_paused":
            terminal["terminal_status"] = "Failed"
        elif name == "changed_settings":
            terminal["job"]["quality_label"] = "other"
        elif name == "changed_manual_selection":
            terminal["job"]["manual_settings"]["audio_bitrate_kbps"] += 1
        elif name == "changed_destination":
            terminal["job"]["output_dir"] += "/other"
        elif name == "reordered_queue":
            raw["paused_store"]["queued_jobs"].reverse()
        elif name == "public_settings":
            raw["settings_before"]["file"]["mode"] = 0o644
        elif name == "escaped_settings":
            raw["settings_before"]["file"]["path"] = "/foreign/settings.json"
        elif name == "settings_after_changed":
            raw["settings_after"]["file"]["sha256"] = "0" * 64
        elif name == "journal_survives_removal":
            raw["after"]["journal"]["exists"] = True
        elif name == "stage_survives_removal":
            raw["after"]["stage"]["exists"] = True
        elif name == "cleanup_masks_child":
            after["recovery_reaped_child"] = False
        elif name == "recovery_error":
            after["recovery_error"] = "failed"
        elif name == "missing_fast_stop":
            raw["fast_stop_store"]["recovered_failures"].pop()
        elif name == "merged_fast_stop":
            raw["fast_stop_store"]["recovered_failures"][1]["job"]["run_id"] = (
                "queued-first"
            )
        elif name == "wrong_fast_stop_status":
            raw["fast_stop_store"]["recovered_failures"][0]["terminal_status"] = (
                "Queued"
            )
    else:
        if name == "wrong_renderer":
            raw["renderer"] = "tk"
        elif name == "missing_constituent":
            raw["workers"]["skipped"]["path"] = str(directory / "absent.json")
        elif name == "changed_constituent":
            raw["workers"]["skipped"]["sha256"] = "0" * 64
        elif name == "foreign_constituent":
            raw["workers"]["skipped"]["path"] = "/foreign/worker.json"
        elif name == "idle_root_survives":
            raw[key][1]["root"]["exists"] = True
        elif name == "active_stage_removed":
            raw[key][4]["stage"]["exists"] = False
        elif name == "sentinel_changed":
            raw[key][4]["sentinel"]["sha256"] = "0" * 64
        elif name == "saved_media_changed":
            raw[key][4]["media"]["sha256"] = "0" * 64
        elif name == "history_not_removed":
            raw[key][4]["history"] = raw[key][3]["history"]
        elif name == "owner_cleanup_failed":
            raw[key][5]["stage"]["exists"] = True
        else:
            label = (
                "completed"
                if name
                in {
                    "unreadable_commit",
                    "shared_transaction_owner",
                    "different_destination",
                }
                else "skipped"
            )
            ref = raw["workers"][label]
            worker = json.loads(Path(ref["path"]).read_text())
            terminal = (
                next(e for e in worker["events"] if e["kind"] == "item_terminal")
                if label == "skipped"
                else None
            )
            if name == "foreign_origin_owner":
                terminal["payload"]["job"]["origin_run_id"] = "other"
            elif name == "foreign_execution_owner":
                terminal["payload"]["job"]["execution_run_id"] = "other"
            elif name == "foreign_terminal_id":
                terminal["payload"]["info"]["vodforge_terminal_run_id"] = "other"
            elif name == "same_parent_id":
                terminal["payload"]["job"]["run_id"] = worker["job"]["run_id"]
            elif name == "foreign_source":
                terminal["payload"]["job"]["url"] = "other"
            elif name == "missing_terminal":
                worker["events"].remove(terminal)
            elif name == "duplicate_terminal":
                worker["events"].append(copy.deepcopy(terminal))
            elif name == "wrong_terminal_status":
                terminal["payload"]["job"]["terminal_status"] = "Completed"
            elif name == "wrong_terminal_message":
                terminal["payload"]["job"]["terminal_message"] = "Other"
            elif name == "early_terminal":
                terminal["elapsed_seconds"] = 0
            elif name == "late_skip_request":
                next(
                    r
                    for r in worker["control_trace"]
                    if r["phase"] == "control_requested"
                )["elapsed_seconds"] = 100
            elif name == "no_downloading":
                worker["events"] = [
                    e for e in worker["events"] if e["kind"] != "status"
                ]
            elif name == "wrong_control":
                worker["control_request"] = "cancel"
            elif name == "shared_transaction_owner":
                worker["job"]["run_id"] = json.loads(
                    Path(raw["workers"]["skipped"]["path"]).read_text()
                )["job"]["run_id"]
                for row in worker["control_trace"]:
                    row["run_id"] = worker["job"]["run_id"]
            elif name == "different_destination":
                worker["job"]["output_dir"] += "/other"
            elif name == "escaped_transfer":
                next(
                    r
                    for r in worker["progress_trace"]
                    if r.get("downloaded_bytes", 0) > 0
                )["filename"] = "/foreign/input"
            elif name == "foreign_worker_control":
                worker["control_trace"][0]["run_id"] = "other"
            elif name == "prior_media":
                worker["before_worker"]["output_files"] = ["prior.mp4"]
            elif name == "stage_residue":
                worker["staging_entries_after"] = ["stage"]
            elif name == "emergency_cleanup":
                worker["harness_emergency_cleanup_used"] = True
            elif name == "observer_leak":
                worker["control_observer_stopped"] = False
            elif name == "unreadable_commit":
                next(r for r in worker["outputs"] if r["path"].endswith(".mp4"))[
                    "readable"
                ] = False
            elif name == "foreign_worker_clock":
                worker["observation_clock_origin_monotonic"] += 100
            else:
                raise AssertionError(name)
            raw["workers"][label] = save(directory / "worker.json", worker)


def materialize(tmp_path, example):
    root = tmp_path / "cases"
    root.mkdir()
    folder = root / example["folder"]
    folder.mkdir()
    old = example["case_root"]
    raw = json.loads(json.dumps(example["raw"]).replace(old, str(root)))
    if "workers" in raw:
        for label, value in example["workers"].items():
            worker = json.loads(json.dumps(value).replace(old, str(root)))
            worker_folder = root / worker["case_id"]
            worker_folder.mkdir()
            raw["workers"][label] = save(worker_folder / "pipeline-result.json", worker)
    ref = save(folder / "observation.json", raw)
    return (
        dict(
            example["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]
        ),
        raw,
        folder,
    )


CASES = [(i, name) for i, f in enumerate(FIXTURES) for name in controls(f["scenario"])]


@pytest.mark.parametrize("index", range(len(FIXTURES)))
def test_actual_transaction_shape_qualifies(tmp_path, index):
    scenario, _, _ = materialize(tmp_path, FIXTURES[index])
    review = interaction_coverage(scenario)
    assert review["status"] == "passed", review
    assert review["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("index,name", CASES)
def test_mutated_transaction_cannot_qualify(tmp_path, index, name):
    scenario, raw, folder = materialize(tmp_path, FIXTURES[index])
    directory = folder / name
    directory.mkdir()
    mutate(scenario, raw, name, directory)
    ref = save(folder / "mutation.json", raw)
    scenario.update(raw_result=ref["path"], raw_result_sha256=ref["sha256"])
    assert interaction_coverage(scenario)["status"] in {"failed", "unproven"}
