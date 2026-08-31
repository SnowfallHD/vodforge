from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from quality_harness import e2e_record
from quality_harness.e2e_record import record_e2e_event

TEST_PID = 4312
TEST_WINDOW_ID = 9876
TEST_WINDOW_TOKEN = "VFQ-0123456789ab-L1"


def _args(
    session: Path,
    event: str,
    *,
    screenshot: Path | None = None,
    allow_gap: bool = False,
    window_pid: int = TEST_PID,
    window_owner_pid: int = TEST_PID,
    window_id: int = TEST_WINDOW_ID,
    window_title_token: str = TEST_WINDOW_TOKEN,
) -> argparse.Namespace:
    return argparse.Namespace(
        session=session,
        event=event,
        screenshot=screenshot,
        note="test receipt",
        allow_gap=allow_gap,
        control_action=None,
        window_pid=window_pid,
        window_owner_pid=window_owner_pid,
        window_id=window_id,
        window_title_token=window_title_token,
    )


def _write_session(tmp_path: Path) -> tuple[Path, Path]:
    session_dir = tmp_path / "session"
    ui_dir = session_dir / "ui"
    ui_dir.mkdir(parents=True)
    trace_path = session_dir / "driver-events.json"
    control_path = session_dir / "control.json"
    trace_path.write_text('{"events": [], "screenshots": [], "notes": []}\n')
    control_path.write_text('{"action": "running"}\n')
    session_path = session_dir / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "session_dir": str(session_dir),
                "e2e_profile": "smoke",
                "driver_events_path": str(trace_path),
                "control_path": str(control_path),
                "driver_ready": True,
                "session_nonce": "0123456789abcdef0123456789abcdef",
                "current_launch": {
                    "verified": True,
                    "session_nonce": "0123456789abcdef0123456789abcdef",
                    "launch_id": "launch-1",
                    "launch_sequence": 1,
                    "pid": TEST_PID,
                    "create_time": 1234.5,
                    "executable_sha256": "a" * 64,
                    "bundle_tree_sha256": "b" * 64,
                    "window_token": TEST_WINDOW_TOKEN,
                },
            }
        )
        + "\n"
    )
    return session_path, trace_path


def _verified_live_receipt(_launch: dict[str, Any]) -> dict[str, Any]:
    return {"verified": True, "errors": []}


def test_recorder_copies_hashes_and_enforces_event_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_path, trace_path = _write_session(tmp_path)
    observed_launches: list[dict[str, Any]] = []

    def verify(launch: dict[str, Any]) -> dict[str, Any]:
        observed_launches.append(launch)
        return _verified_live_receipt(launch)

    monkeypatch.setattr(e2e_record, "verify_live_launch", verify)
    screenshot = tmp_path / "visible.png"
    screenshot.write_bytes(b"not-a-real-png-but-nonempty-driver-evidence")

    assert (
        record_e2e_event(_args(session_path, "app_visible", screenshot=screenshot)) == 0
    )
    trace = json.loads(trace_path.read_text())
    event = trace["events"][0]
    assert event["event"] == "app_visible"
    assert event["screenshot_sha256"]
    assert Path(event["screenshot"]).is_file()
    assert trace["screenshots"] == [event["screenshot"]]
    assert event["session_nonce"] == "0123456789abcdef0123456789abcdef"
    assert event["launch_id"] == "launch-1"
    assert event["launch_sequence"] == 1
    assert event["pid"] == TEST_PID
    assert event["window_id"] == TEST_WINDOW_ID
    assert event["window_owner_pid"] == TEST_PID
    assert event["window_title_token"] == TEST_WINDOW_TOKEN
    assert observed_launches[0]["pid"] == TEST_PID

    with pytest.raises(RuntimeError, match="expected next E2E event"):
        record_e2e_event(_args(session_path, "forge_started", screenshot=screenshot))

    assert (
        record_e2e_event(
            _args(
                session_path,
                "forge_started",
                screenshot=screenshot,
                allow_gap=True,
            )
        )
        == 0
    )
    trace = json.loads(trace_path.read_text())
    assert trace["events"][1]["unobserved_prior_events"] == [
        "url_entered",
        "settings_observed",
    ]

    with pytest.raises(RuntimeError, match="already recorded"):
        record_e2e_event(
            _args(
                session_path,
                "forge_started",
                screenshot=screenshot,
                allow_gap=True,
            )
        )

    # Once a forward gap is explicit, subsequent events continue from the
    # latest receipt instead of being blocked forever by the earlier gap.
    assert (
        record_e2e_event(
            _args(session_path, "progress_observed", screenshot=screenshot)
        )
        == 0
    )


@pytest.mark.parametrize(
    ("argument_overrides", "message"),
    [
        ({"window_pid": TEST_PID + 1}, "window PID"),
        ({"window_owner_pid": TEST_PID + 1}, "window PID"),
        ({"window_title_token": "VFQ-wrong-L1"}, "window title token"),
    ],
)
def test_recorder_rejects_window_identity_not_owned_by_current_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argument_overrides: dict[str, Any],
    message: str,
) -> None:
    session_path, trace_path = _write_session(tmp_path)
    monkeypatch.setattr(e2e_record, "verify_live_launch", _verified_live_receipt)
    screenshot = tmp_path / "visible.png"
    screenshot.write_bytes(b"visible")

    with pytest.raises(RuntimeError, match=message):
        record_e2e_event(
            _args(
                session_path,
                "app_visible",
                screenshot=screenshot,
                **argument_overrides,
            )
        )

    assert json.loads(trace_path.read_text())["events"] == []


def test_recorder_fails_closed_when_current_launch_no_longer_verifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_path, trace_path = _write_session(tmp_path)
    monkeypatch.setattr(
        e2e_record,
        "verify_live_launch",
        lambda _launch: {
            "verified": False,
            "errors": ["live launch executable mismatch"],
        },
    )

    with pytest.raises(RuntimeError, match="no longer verifies"):
        record_e2e_event(
            _args(
                session_path,
                "app_visible",
                screenshot=tmp_path / "not-read.png",
            )
        )

    assert json.loads(trace_path.read_text())["events"] == []
