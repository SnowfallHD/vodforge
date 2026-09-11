"""Opt-in serializer/transport proof against preview D1; NEVER UI/release proof.

Run in a fresh isolated process/profile. The preview key is inherited privately.
The fixed preview route cannot contact production or the external provider.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import load_or_create_installation_state
from yt_downloader.product_telemetry import ProductTelemetryOwner
from yt_downloader.telemetry_credentials import TelemetryCredentialOwner
from yt_downloader.telemetry_features import FEATURE_ACTIONS
from yt_downloader.telemetry_policy import (
    preview_telemetry_allowed,
    production_telemetry_allowed,
)

from .telemetry_release import read_preview_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    profile = root / "profile"
    profile.mkdir()
    marker = root / "preview-contract-runtime"
    marker.mkdir()
    (marker / "VODFORGE_TELEMETRY_POLICY").write_text("preview")
    # A source-only contract fixture, explicitly distinct from packaged attestation.
    sys._MEIPASS = str(marker)
    os.environ["VODFORGE_QA_PROFILE"] = str(profile)
    os.environ.pop("VODFORGE_DISABLE_TELEMETRY", None)
    assert preview_telemetry_allowed() and not production_telemetry_allowed()
    from yt_downloader import telemetry_credentials

    # Source fixture simulates the declared bundle version, as the local contract does.
    telemetry_credentials.__version__ = args.version
    consent = AnalyticsConsentOwner(profile)
    consent.choose(True)
    credentials = TelemetryCredentialOwner(profile)
    assert credentials.observe_session(args.version, "macos"), (
        "Preview enrollment/launch failed"
    )
    emitted = []

    def deliver(event):
        payload = event.public_payload()
        accepted = credentials.event(payload)
        if accepted:
            emitted.append(payload)
        return accepted

    usage = ProductTelemetryOwner(
        state_path=profile / "product-telemetry.json",
        installation_state_path=profile / "installation.json",
        app_version=args.version,
        platform_name="darwin",
        d1_recorder=deliver,
        heycatch_recorder=lambda *_args, **_kwargs: False,
    )

    def record(name, **fields):
        assert usage.record(name, **fields)
        assert usage.shutdown(15), "Preview request did not finish"
        assert not (profile / "product-telemetry.json").exists(), (
            "Preview rejected or deferred an event"
        )

    record("app_opened")
    for index, output in enumerate(("mp4", "mp3", "original")):
        fields = {
            "attempt_key": f"output-{index}",
            "run_kind": "youtube",
            "output_type": output,
        }
        record("run_started", **fields)
        record(
            "media_exported",
            **fields,
            dimensions={
                "encoder": "copy" if output == "original" else "cpu",
                "resolution": "1080p" if output == "mp4" else "audio",
                "size_bucket": "under_10mb",
                "duration_bucket": "under_1m",
            },
        )
        record("run_completed", **fields, dimensions={"outcome": "complete"})
        record("playback_started", output_type=output)
    for outcome in ("failed", "stopped"):
        fields = {"attempt_key": outcome, "run_kind": "youtube", "output_type": "mp4"}
        record("run_started", **fields)
        record("run_" + outcome, **fields)
    fields = {
        "attempt_key": "retry",
        "retry_key": "failed",
        "run_kind": "youtube",
        "output_type": "mp4",
    }
    record("run_queued", **fields)
    record("run_started", **fields)
    record("run_completed", **fields)
    fields = {"attempt_key": "removed", "run_kind": "youtube", "output_type": "mp4"}
    record("run_queued", **fields)
    record("run_dequeued", **fields)
    fields = {"attempt_key": "skip", "run_kind": "youtube", "output_type": "mp4"}
    record("run_started", **fields)
    record("run_skipped", **fields)
    record("run_completed", **fields, dimensions={"outcome": "partial"})
    for outcome in ("completed", "failed", "stopped"):
        fields = {
            "attempt_key": "local-" + outcome,
            "run_kind": "local_audio_video",
            "output_type": "mp4",
        }
        record("local_conversion_started", **fields)
        record("local_conversion_" + outcome, **fields)
    for feature, actions in FEATURE_ACTIONS.items():
        for action in sorted(actions):
            record("feature_used", feature=feature, action=action)
    for preset in ("everyday", "streaming", "editing", "sharing", "ctv", "custom"):
        record(
            "media_exported",
            attempt_key="output-0",
            run_kind="youtube",
            output_type="mp4",
            dimensions={
                "preset": preset,
                "rate_control": "cbr" if preset == "ctv" else "quality",
                "source_resolution": "1080p",
                "input_kind": "playlist",
                "item_count_bucket": "2_5",
                "metadata": "enabled",
                "artwork": "thumbnail",
                "theme": "violet",
            },
        )
    install = load_or_create_installation_state(
        profile / "installation.json"
    ).install_id
    before = read_preview_snapshot(args.site.resolve(), install)
    assert len(before["events"]) == len(emitted)
    for event in emitted:
        row = next(
            row for row in before["events"] if row["event_id"] == event["event_id"]
        )
        for field in (
            "event_name",
            "output_type",
            "attempt_id",
            "retry_of",
            "feature",
            "action",
            "schema_version",
        ):
            assert row[field] == event[field], field
        assert json.loads(row["dimensions"]) == event["dimensions"]
    # Lost-response replay must not create another row or change immutable data.
    for event in emitted[:3]:
        assert credentials.event(event)
    consent.choose(False)
    for feature, actions in FEATURE_ACTIONS.items():
        for action in actions:
            assert not usage.record("feature_used", feature=feature, action=action)
    after = read_preview_snapshot(args.site.resolve(), install)
    assert (
        before["events"] == after["events"]
        and before["installations"] == after["installations"]
    )
    (root / "emitted.json").write_text(json.dumps(emitted, indent=2))
    (root / "snapshot.json").write_text(json.dumps(after, indent=2))
    (root / "result.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "evidence_tier": "source_serializer_preview_d1",
                "packaged_ui_verified": False,
                "events_verified": len(emitted),
                "install_id": install,
                "privacy_denial_unchanged": True,
            },
            indent=2,
        )
    )
    print(
        f"Preview serializer contract passed: {len(emitted)} events; no packaged UI claim"
    )


if __name__ == "__main__":
    main()
