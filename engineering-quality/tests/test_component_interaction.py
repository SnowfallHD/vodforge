"""Independent construction and injected-validator evidence must fail closed."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

FIXTURES = json.loads(
    Path(__file__).with_name("component_observations.json").read_text()
)
COMMON = [
    "foreign_identity",
    "foreign_contract",
    "missing_trace",
    "reversed_trace",
    "missing_clock",
    "foreign_raw_hash",
]
ARGV = [
    "prior_root",
    "prior_marker",
    "wrong_metadata",
    "escaped_target",
    "split_source",
    "string_command",
    "wrong_input_position",
    "executed_marker",
    "shell_true",
    "missing_source_hash",
]
SYMLINK = [
    "missing_symlink",
    "wrong_link_target",
    "prior_outside",
    "escaped_source",
    "missing_source",
    "source_changed_during",
    "source_changed_after",
    "no_refusal",
    "packaged_escape",
    "outside_write",
    "public_stage",
    "public_root",
    "symlink_stage",
    "escaped_stage",
    "not_posix",
]
VALIDATION = [
    "missing_call",
    "duplicate_call",
    "changed_source",
    "escaped_source",
    "wrong_size",
    "after_file_changed",
    "missing_final_file",
    "false_scope",
] + [f"{kind}:{i}" for i in range(27) for kind in ["outcome", "plan", "probe"]]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def controls(s):
    return COMMON + (
        VALIDATION
        if s["id"].startswith("correctness")
        else ARGV
        if "subprocess" in s["id"]
        else SYMLINK
    )


def mutate(s, a, name):
    key = "calls" if s["id"].startswith("correctness") else "trace"
    if name == "foreign_identity":
        a["scenario_id"] = "other"
    elif name == "foreign_contract":
        a["contract"] = "other"
    elif name == "missing_trace":
        del a[key]
    elif name == "reversed_trace":
        a[key].reverse()
    elif name == "missing_clock":
        del a[key][0]["entered_seconds" if key == "calls" else "elapsed_seconds"]
    elif name == "foreign_raw_hash":
        pass
    elif key == "calls":
        calls = a[key]
        if ":" in name:
            kind, i = name.split(":")
            row = calls[int(i)]
            if kind == "outcome":
                row["exception_type"] = (
                    "RuntimeError" if row["exception_type"] is None else None
                )
            elif kind == "plan":
                row["plan"]["audio_bitrate_kbps"] = 128
            elif kind == "probe":
                row["probe"]["format"]["duration"] = "1000"
        elif name == "missing_call":
            calls.pop()
        elif name == "duplicate_call":
            calls[-1] = copy.deepcopy(calls[0])
        elif name == "changed_source":
            calls[0]["source_after"]["sha256"] = "0" * 64
        elif name == "escaped_source":
            calls[0]["source_before"]["path"] = "/foreign/source.mp3"
        elif name == "wrong_size":
            calls[0]["source_before"]["size_bytes"] = 0
        elif name == "after_file_changed":
            a["files_after"][0]["sha256"] = "0" * 64
        elif name == "missing_final_file":
            a["files_after"].pop()
        elif name == "false_scope":
            a["scope"] = "real media decode"
    elif "subprocess" in s["id"]:
        before, during, after = a[key]
        if name == "prior_root":
            before["root_exists"] = True
        elif name == "prior_marker":
            before["marker_exists"] = True
        elif name == "wrong_metadata":
            during["metadata"]["title"] = "Normal title"
        elif name == "escaped_target":
            during["target_dir"] = "/foreign"
        elif name == "split_source":
            during["command"] += [during["source_path"]]
        elif name == "string_command":
            during["command"] = "ffmpeg -i source"
        elif name == "wrong_input_position":
            during["command"][during["command"].index("-i") + 1] = "other"
        elif name == "executed_marker":
            after["marker_exists"] = True
        elif name == "shell_true":
            after["shell_true"] = [123]
        elif name == "missing_source_hash":
            del after["source"]["sha256"]
    else:
        before, during, after = a[key]
        if name == "missing_symlink":
            before["link_is_symlink"] = False
        elif name == "wrong_link_target":
            before["link_target"] = "/foreign"
        elif name == "prior_outside":
            before["outside_entries"] = ["file"]
        elif name == "escaped_source":
            before["source"]["path"] = "/foreign/source"
        elif name == "missing_source":
            before["source"]["exists"] = False
        elif name == "source_changed_during":
            during["source"]["sha256"] = "0" * 64
        elif name == "source_changed_after":
            after["source"]["sha256"] = "0" * 64
        elif name == "no_refusal":
            during["exception_type"] = None
        elif name == "packaged_escape":
            during["packaged"] = ["/foreign/video.mp4"]
        elif name == "outside_write":
            during["outside_entries"] = ["video.mp4"]
        elif name == "public_stage":
            after["stage"]["mode"] = 0o755
        elif name == "public_root":
            after["root"]["mode"] = 0o755
        elif name == "symlink_stage":
            after["stage"]["symlink"] = True
        elif name == "escaped_stage":
            after["stage"]["path"] = "/foreign/stage"
        elif name == "not_posix":
            after["os_name"] = "nt"


def materialize(tmp_path, example):
    folder = tmp_path / example["folder"]
    folder.mkdir()
    a = json.loads(json.dumps(example["raw"]).replace(example["old_root"], str(folder)))
    ref = save(folder / "observation.json", a)
    return (
        dict(
            example["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]
        ),
        a,
        folder,
    )


CASES = [(i, n) for i, f in enumerate(FIXTURES) for n in controls(f["scenario"])]


@pytest.mark.parametrize("i", range(len(FIXTURES)))
def test_actual_component_shape_qualifies(tmp_path, i):
    s, _, _ = materialize(tmp_path, FIXTURES[i])
    q = interaction_coverage(s)
    assert q["status"] == "passed", q
    assert q["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("i,name", CASES)
def test_altered_component_cannot_qualify(tmp_path, i, name):
    s, a, folder = materialize(tmp_path, FIXTURES[i])
    mutate(s, a, name)
    ref = save(folder / "mutation.json", a)
    s.update(
        raw_result=ref["path"],
        raw_result_sha256="0" * 64 if name == "foreign_raw_hash" else ref["sha256"],
    )
    q = interaction_coverage(s)
    assert q["status"] in {"failed", "unproven"}, q
