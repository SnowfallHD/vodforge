from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from quality_harness.e2e_record import record_e2e_event


def _args(
    session: Path,
    event: str,
    *,
    screenshot: Path | None = None,
    allow_gap: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        session=session,
        event=event,
        screenshot=screenshot,
        note="test receipt",
        allow_gap=allow_gap,
        control_action=None,
    )


def test_recorder_copies_hashes_and_enforces_event_order(tmp_path: Path) -> None:
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
            }
        )
        + "\n"
    )
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
