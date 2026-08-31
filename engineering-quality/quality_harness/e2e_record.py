from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .e2e_provenance import verify_live_launch
from .packaged_e2e import SCREENSHOT_OPTIONAL_EVENTS, _required_ui_event_order
from .util import json_dump, sha256_file, utc_now


def record_e2e_event(args: argparse.Namespace) -> int:
    session_path = args.session.resolve()
    if session_path.is_dir():
        session_path = session_path / "session.json"
    if not session_path.is_file():
        raise RuntimeError(f"E2E session.json does not exist: {session_path}")
    session = json.loads(session_path.read_text(encoding="utf-8"))
    session_dir = Path(str(session.get("session_dir") or session_path.parent)).resolve()
    if session_dir != session_path.parent.resolve():
        raise RuntimeError(
            "session_dir does not match the directory containing session.json"
        )
    profile = str(session.get("e2e_profile") or "")
    if session.get("driver_ready") is not True:
        raise RuntimeError(
            "E2E driver is not ready; provenance must verify before UI interaction"
        )
    current_launch = session.get("current_launch")
    if not isinstance(current_launch, dict) or not current_launch.get("verified"):
        raise RuntimeError("E2E session has no verified current launch")
    live_receipt = verify_live_launch(current_launch)
    if live_receipt.get("verified") is not True:
        raise RuntimeError(
            "E2E current launch no longer verifies: "
            + "; ".join(str(item) for item in live_receipt.get("errors") or [])
        )
    expected_pid = int(current_launch["pid"])
    if args.window_pid != expected_pid or args.window_owner_pid != expected_pid:
        raise RuntimeError(
            "E2E window PID does not match the verified harness-owned process"
        )
    if args.window_id <= 0:
        raise RuntimeError("E2E window ID must be a positive native window identifier")
    if args.window_title_token != current_launch.get("window_token"):
        raise RuntimeError("E2E window title token does not match the current launch")
    required_order = _required_ui_event_order(profile)
    if args.event not in required_order:
        raise RuntimeError(
            f"event {args.event!r} is not valid for the {profile!r} E2E profile"
        )

    trace_path = Path(
        str(session.get("driver_events_path") or session_dir / "driver-events.json")
    ).resolve()
    if trace_path.parent != session_dir:
        raise RuntimeError(
            "driver event trace must remain inside the E2E session directory"
        )
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    observed = [str(item.get("event")) for item in events if isinstance(item, dict)]
    if args.event in observed:
        raise RuntimeError(f"E2E event {args.event!r} was already recorded")
    last_index = max(
        (required_order.index(name) for name in observed if name in required_order),
        default=-1,
    )
    next_event = next(
        (name for name in required_order[last_index + 1 :] if name not in observed),
        None,
    )
    if args.event != next_event:
        target_index = required_order.index(args.event)
        if target_index <= last_index or not args.allow_gap:
            raise RuntimeError(
                f"expected next E2E event {next_event!r}, not {args.event!r}"
            )
        unobserved_prior_events = [
            name
            for name in required_order[last_index + 1 : target_index]
            if name not in observed
        ]
    else:
        unobserved_prior_events = []

    screenshot_target: Path | None = None
    if args.event not in SCREENSHOT_OPTIONAL_EVENTS:
        if args.screenshot is None:
            raise RuntimeError(f"event {args.event!r} requires a screenshot")
        source = args.screenshot.resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise RuntimeError(f"screenshot is missing or empty: {source}")
        suffix = source.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg"}:
            raise RuntimeError("E2E screenshots must be PNG or JPEG")
        screenshot_target = (
            session_dir / "ui" / f"{len(events) + 1:02d}-{args.event}{suffix}"
        )
        screenshot_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, screenshot_target)

    event = {
        "event": args.event,
        "observed_at": utc_now(),
        "screenshot": str(screenshot_target) if screenshot_target else None,
        "screenshot_sha256": sha256_file(screenshot_target)
        if screenshot_target
        else None,
        "note": args.note or None,
        "recorder": "quality_harness.e2e_record/1",
        "session_nonce": session.get("session_nonce"),
        "launch_id": current_launch.get("launch_id"),
        "launch_sequence": current_launch.get("launch_sequence"),
        "pid": expected_pid,
        "process_create_time": current_launch.get("create_time"),
        "executable_sha256": current_launch.get("executable_sha256"),
        "bundle_tree_sha256": current_launch.get("bundle_tree_sha256"),
        "window_id": args.window_id,
        "window_owner_pid": args.window_owner_pid,
        "window_title_token": args.window_title_token,
    }
    if unobserved_prior_events:
        event["unobserved_prior_events"] = unobserved_prior_events
    events.append(event)
    trace["events"] = events
    screenshots = (
        trace.get("screenshots") if isinstance(trace.get("screenshots"), list) else []
    )
    if screenshot_target is not None:
        screenshots.append(str(screenshot_target))
    trace["screenshots"] = screenshots
    trace.setdefault("notes", [])
    json_dump(trace_path, trace)

    if args.control_action:
        control_path = Path(
            str(session.get("control_path") or session_dir / "control.json")
        ).resolve()
        if control_path.parent != session_dir:
            raise RuntimeError(
                "E2E control file must remain inside the session directory"
            )
        json_dump(
            control_path, {"action": args.control_action, "recorded_at": utc_now()}
        )

    print(f"[e2e-record] event={args.event} trace={trace_path}")
    if screenshot_target:
        print(
            f"[e2e-record] screenshot={screenshot_target} sha256={event['screenshot_sha256']}"
        )
    return 0
