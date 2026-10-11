import copy
import json

import pytest
from quality_harness.packaged_e2e import _validate_driver_trace
from quality_harness.util import sha256_file
from test_packaged_e2e_receipts import _driver_trace


def continued_trace(tmp_path):
    nonce = "f" * 32
    launches = [
        {
            "verified": True,
            "returncode": 0,
            "launch_sequence": i,
            "launch_id": str(i) * 32,
            "pid": 7000 + i,
            "create_time": float(i),
            "executable_sha256": "a" * 64,
            "bundle_tree_sha256": "b" * 64,
            "window_token": f"VFQ-test-L{i}",
            "attestation": {"telemetry_preview": i < 5, "telemetry_production": False},
        }
        for i in range(1, 6)
    ]
    trace = _driver_trace(
        tmp_path, profile="telemetry", session_nonce=nonce, launches=launches
    )
    # The first eight observations preceded the pause; remaining phase-one
    # actions occur in its independently attested continuation process.
    for index, event in enumerate(trace["events"]):
        sequence = {
            "restart_observed": 3,
            "consent_denied_observed": 4,
            "telemetry_disabled_observed": 5,
        }.get(event["event"], 1 if index < 8 else 2)
        launch = launches[sequence - 1]
        for key in (
            "launch_id",
            "launch_sequence",
            "pid",
            "executable_sha256",
            "bundle_tree_sha256",
        ):
            event[key] = launch[key]
        event["process_create_time"] = launch["create_time"]
        event["window_owner_pid"] = launch["pid"]
        event["window_title_token"] = launch["window_token"]
        event["native_window_identity"]["owner_pid"] = launch["pid"]
        event["native_window_identity"]["title"] = (
            f"VODForge [{launch['window_token']}]"
        )
    archive = tmp_path / "continuation-1"
    archive.mkdir()
    (archive / "e2e-result.json").write_text('{"status":"failed"}')
    (archive / "session.json").write_text(
        json.dumps(
            {
                "session_nonce": nonce,
                "e2e_profile": "telemetry",
                "launches": launches[:1],
                "current_launch": None,
                "driver_ready": False,
            }
        )
    )
    (archive / "driver-events.json").write_text(
        json.dumps(
            {
                **trace,
                "events": trace["events"][:8],
            }
        )
    )
    continuation = {
        "prior_launch_count": 1,
        "prior_receipt": str(archive / "e2e-result.json"),
        "prior_receipt_sha256": sha256_file(archive / "e2e-result.json"),
    }
    return trace, launches, nonce, continuation, archive


def test_completed_journey_can_continue_after_verified_pause_without_replaying(
    tmp_path,
):
    trace, launches, nonce, continuation, _ = continued_trace(tmp_path)
    receipt = _validate_driver_trace(
        trace,
        profile="telemetry",
        session_dir=tmp_path,
        session_nonce=nonce,
        launches=launches,
        continuations=[continuation],
    )
    assert receipt["valid"] is True
    assert receipt["invalid_provenance_events"] == []
    assert receipt["invalid_continuations"] == []
    assert len(trace["events"]) == len({e["event"] for e in trace["events"]})


@pytest.mark.parametrize(
    "invalid",
    [
        "hash",
        "missing_receipt",
        "foreign_receipt",
        "changed_prior_launch",
        "changed_prior_trace",
        "foreign_nonce",
        "live_prior",
        "failed_prior",
        "survivors",
        "duplicate",
        "wrong_phase",
        "disabled_preview",
        "disabled_production",
    ],
)
def test_continuation_phases_require_original_immutable_evidence_and_exact_process(
    tmp_path, invalid
):
    trace, launches, nonce, continuation, archive = continued_trace(tmp_path)
    continuations = [continuation]
    if invalid == "hash":
        continuation["prior_receipt_sha256"] = "changed"
    elif invalid == "missing_receipt":
        (archive / "e2e-result.json").unlink()
    elif invalid == "foreign_receipt":
        continuation["prior_receipt"] = str(tmp_path / "foreign.json")
    elif invalid == "changed_prior_trace":
        old = json.loads((archive / "driver-events.json").read_text())
        old["events"][0]["pid"] = 9000
        (archive / "driver-events.json").write_text(json.dumps(old))
    elif invalid in (
        "changed_prior_launch",
        "foreign_nonce",
        "live_prior",
        "failed_prior",
        "survivors",
    ):
        old = json.loads((archive / "session.json").read_text())
        if invalid == "changed_prior_launch":
            old["launches"][0]["pid"] = 9000
        elif invalid == "foreign_nonce":
            old["session_nonce"] = "other"
        elif invalid == "live_prior":
            old["current_launch"] = old["launches"][0]
        elif invalid == "failed_prior":
            old["launches"][0]["returncode"] = 1
        else:
            old["launches"][0]["group_survivors_after_exit"] = [9000]
        (archive / "session.json").write_text(json.dumps(old))
    elif invalid == "duplicate":
        continuations.append(copy.deepcopy(continuation))
    elif invalid == "wrong_phase":
        event = next(e for e in trace["events"] if e["event"] == "completion_observed")
        event["launch_sequence"] = 3
    elif invalid == "disabled_preview":
        launches[-1]["attestation"]["telemetry_preview"] = True
    elif invalid == "disabled_production":
        launches[-1]["attestation"]["telemetry_production"] = True
    receipt = _validate_driver_trace(
        trace,
        profile="telemetry",
        session_dir=tmp_path,
        session_nonce=nonce,
        launches=launches,
        continuations=continuations,
    )
    assert receipt["valid"] is False
    assert receipt["structural_valid"] is False


def test_additional_launch_without_archived_continuation_is_not_admitted(tmp_path):
    trace, launches, nonce, _, _ = continued_trace(tmp_path)
    receipt = _validate_driver_trace(
        trace,
        profile="telemetry",
        session_dir=tmp_path,
        session_nonce=nonce,
        launches=launches,
    )
    assert receipt["valid"] is False


@pytest.mark.parametrize("paused_before_restart", [True, False])
def test_continuation_history_baseline_requires_an_actual_requested_restart(
    paused_before_restart,
):
    from quality_harness.packaged_e2e import _continuation_restart_baseline

    incomplete = {"history_sha256": "before-exports", "media": []}
    complete = {"history_sha256": "all-exports", "media": ["mp4", "mp3", "original"]}
    launches = [
        {"launch_sequence": 1, "pre_restart_state": incomplete},
        {"launch_sequence": 2, "reason": "continued_after_pause"},
    ]
    if paused_before_restart:
        assert _continuation_restart_baseline(launches) is None
    else:
        launches[1]["pre_restart_state"] = complete
        launches.extend(
            [
                {"launch_sequence": 3, "reason": "driver_requested_restart"},
                {"launch_sequence": 4, "reason": "continued_after_pause"},
            ]
        )
        assert _continuation_restart_baseline(launches) == complete
    assert incomplete["history_sha256"] == "before-exports"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:31337/slow/page/library-description-stress",
        "https://127.0.0.1:31337/slow/page/library-description-stress",
        "http://user:secret@127.0.0.1:31337/slow/page/library-description-stress",
        "http://127.0.0.1/slow/page/library-description-stress",
        "http://127.0.0.1:0/slow/page/library-description-stress",
        "http://127.0.0.1:31337/other-route",
    ],
)
def test_continuation_refuses_changed_fixture_origin(url):
    from quality_harness.packaged_e2e import _continuation_fixture_port

    with pytest.raises(ValueError):
        _continuation_fixture_port({"input_url": url})


def test_continuation_restores_original_fixture_url_and_refuses_port_collision(
    tmp_path,
):
    from urllib.request import urlopen

    from quality_harness.fault_server import FixtureHTTPServer
    from quality_harness.packaged_e2e import _continuation_fixture_port

    assert _continuation_fixture_port(None) == 0
    with FixtureHTTPServer(tmp_path) as original:
        saved_url = original.url("/slow/page/library-description-stress")
        saved_health = original.url("/health")
        saved_port = _continuation_fixture_port({"input_url": saved_url})
        with (
            pytest.raises(OSError),
            FixtureHTTPServer(tmp_path, listen_port=saved_port),
        ):
            pytest.fail("The occupied origin must not be adopted or changed")
    with FixtureHTTPServer(tmp_path, listen_port=saved_port) as resumed:
        assert resumed.url("/slow/page/library-description-stress") == saved_url
        with urlopen(saved_health, timeout=3) as response:
            assert response.read() == b"ok\n"
