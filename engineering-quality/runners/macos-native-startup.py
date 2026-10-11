"""Qualify an existing signed archive on native Intel without rebuilding it."""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "engineering-quality")]

from quality_harness.candidate_artifact import validate_candidate_archive
from quality_harness.e2e_provenance import (
    owned_group_survivors,
    terminate_owned_group,
    verify_live_launch,
)
from quality_harness.packaged_e2e import (
    _artifact_receipt,
    _isolated_state_paths,
    _launch_and_attest,
)
from quality_harness.util import json_dump, sha256_file, utc_now


def wait_for_native_window(
    *,
    pid: int,
    deadline: float,
    sample: Callable[[], list[dict[str, Any]]],
    alive: Callable[[], bool],
    observations: list[dict[str, Any]],
    now: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Observe visibility within the existing launch deadline, never a new one."""
    while now() < deadline:
        if not alive():
            raise RuntimeError(
                "Owned candidate exited before native window observation"
            )
        windows = sample()
        observed_at = now()
        owned = [
            window
            for window in windows
            if window["owner_pid"] == pid
            and window["layer"] == 0
            and window["bounds"]["Width"] > 0
            and window["bounds"]["Height"] > 0
        ]
        observations.append(
            {"seconds_remaining": deadline - observed_at, "owned_windows": owned}
        )
        if observed_at < deadline and owned:
            return owned
        pause(min(0.1, max(0.0, deadline - now())))
    raise RuntimeError(
        "Attested process has no independently observed onscreen native window "
        "within the original 20-second startup guard"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--bundle-tree-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "status": "failed",
        "scope": "Bounded native Intel startup of existing signed bytes; no interactive journey claim",
        "recorded_at": utc_now(),
        "source_commit": args.source_commit,
        "expected_archive_sha256": args.sha256,
        "standard_startup_guard_seconds": 20,
        "guard_changed": False,
        "machine": platform.machine(),
    }
    process = launch = stdout = stderr = None
    try:
        if sys.platform != "darwin" or platform.machine() != "x86_64":
            raise RuntimeError("This qualification requires a native Intel Mac")
        translated = subprocess.run(
            ["/usr/sbin/sysctl", "-in", "sysctl.proc_translated"],
            capture_output=True,
            text=True,
            check=False,
        )
        if translated.stdout.strip() == "1":
            raise RuntimeError("Rosetta cannot supply native Intel qualification")
        result["rosetta"] = False
        if sha256_file(args.archive) != args.sha256:
            raise RuntimeError("Downloaded archive hash differs from frozen candidate")
        result["archive_validation"] = validate_candidate_archive(args.archive)
        root = Path(tempfile.mkdtemp(prefix="vfq-native-intel-")).resolve()
        paths = _isolated_state_paths(root)
        for key in ("home", "tmp", "output", "application_data"):
            Path(paths[key]).mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(args.archive), str(root / "candidate")],
            check=True,
            timeout=120,
        )
        artifact = root / "candidate" / "VODForge.app"
        receipt = _artifact_receipt(artifact, REPO, artifact_policy="release")
        json_dump(output / "artifact-receipt.json", receipt)
        if not receipt["verified"]:
            raise RuntimeError("Release signature/notary/identity verification failed")
        if receipt["executable_sha256"] != args.executable_sha256:
            raise RuntimeError("Executable differs from frozen candidate")
        if receipt["bundle_tree"]["sha256"] != args.bundle_tree_sha256:
            raise RuntimeError("Bundle tree differs from frozen candidate")
        environment = os.environ.copy()
        for key in (
            "QT_QPA_PLATFORM",
            "QT_QUICK_BACKEND",
            "QT_DEBUG_PLUGINS",
            "VODFORGE_QA_ACCESS_KEY",
            "VODFORGE_QA_PREVIEW_TELEMETRY",
            "VODFORGE_QA_PROFILE",
        ):
            environment.pop(key, None)
        environment.update(
            {
                "HOME": paths["home"],
                "XDG_DATA_HOME": paths["xdg_data"],
                "LOCALAPPDATA": paths["local_app_data"],
                "TMPDIR": paths["tmp"],
                "TMP": paths["tmp"],
                "TEMP": paths["tmp"],
                "VODFORGE_DISABLE_TELEMETRY": "1",
                "VODFORGE_QUALITY_E2E": "1",
                "VODFORGE_QUALITY_E2E_ISOLATION_ROOT": paths["isolation_root"],
            }
        )
        started = time.monotonic()
        process, stdout, stderr, launch, _ = _launch_and_attest(
            executable=Path(receipt["executable"]),
            base_environment=environment,
            receipt=receipt,
            state_paths=paths,
            session_nonce=secrets.token_hex(16),
            launch_sequence=1,
            stdout_path=output / "app.stdout.log",
            stderr_path=output / "app.stderr.log",
        )
        result["launch_checks_seconds"] = time.monotonic() - started
        if launch["attestation"]["telemetry_production"]:
            raise RuntimeError(
                "Isolated qualification unexpectedly enabled production telemetry"
            )
        if not verify_live_launch(launch)["verified"]:
            raise RuntimeError("Owned launch changed before native observation")
        import AppKit
        import Quartz

        def native_windows() -> list[dict[str, Any]]:
            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
            )
            return [
                {
                    "window_id": int(window.get(Quartz.kCGWindowNumber, 0)),
                    "owner_pid": int(window.get(Quartz.kCGWindowOwnerPID, 0)),
                    "layer": int(window.get(Quartz.kCGWindowLayer, -1)),
                    "title": str(window.get(Quartz.kCGWindowName, "") or ""),
                    "bounds": {
                        key: float(window.get(Quartz.kCGWindowBounds, {}).get(key, 0))
                        for key in ("X", "Y", "Width", "Height")
                    },
                }
                for window in windows or []
            ]

        observations: list[dict[str, Any]] = []
        try:
            owned_windows = wait_for_native_window(
                pid=launch["pid"],
                deadline=started + 20,
                sample=native_windows,
                alive=lambda: process.poll() is None,
                observations=observations,
            )
        finally:
            json_dump(output / "native-window-observation.json", observations)
        if not verify_live_launch(launch)["verified"]:
            raise RuntimeError("Owned launch changed during native observation")
        result["native_window_observed_seconds"] = time.monotonic() - started
        result["native_onscreen_window_count"] = len(owned_windows)
        application = (
            AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
                launch["pid"]
            )
        )
        if application is None or not application.terminate():
            raise RuntimeError("Owned candidate refused normal application termination")
        process.wait(timeout=20)
        if process.returncode != 0 or owned_group_survivors(launch):
            raise RuntimeError("Normal exit failed or an owned child survived")
        result["status"] = "passed"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if process is not None and launch is not None:
            if process.poll() is None or owned_group_survivors(launch):
                launch["cleanup"] = terminate_owned_group(process, launch)
            launch["returncode"] = process.returncode
            launch["group_survivors_after_exit"] = owned_group_survivors(launch)
            json_dump(output / "launch-result.json", launch)
        if stdout is not None:
            stdout.close()
        if stderr is not None:
            stderr.close()
        json_dump(output / "startup-result.json", result)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
