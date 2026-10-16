"""Qt event handoff for the existing verified update and helper owners."""

from __future__ import annotations

import hashlib
import logging
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from yt_downloader.archive_observations import bind_operation, operation
from yt_downloader.failure_diagnostics import FailureDiagnostic, capture_failure
from yt_downloader.history import application_data_dir
from yt_downloader.platform_services import is_macos, is_windows
from yt_downloader.product_telemetry import BoundProductOperation, ProductTelemetryOwner
from yt_downloader.telemetry_features import time_bucket
from yt_downloader.updates import (
    MacUpdatePlan,
    ReleaseInfo,
    cleanup_stale_macos_updates,
    download_verified_update,
    fetch_latest_release,
    is_newer_release,
    launch_macos_update,
    launch_windows_update,
    prepare_macos_update,
    release_asset_for_platform,
    running_macos_app,
    semantic_version_key,
    verify_windows_authenticode,
)


def _check_failure_status(detail: FailureDiagnostic | None) -> str:
    """Use only machine categories; provider exception messages stay private."""
    if isinstance(detail, FailureDiagnostic):
        if detail.http_status == 429 or detail.reason == "rate_limited":
            return (
                "The update service is limiting requests. Wait and check again later."
            )
        if detail.http_status in {401, 403}:
            return "The update service declined the check. Try again later or open the download page."
        if detail.http_status is not None and detail.http_status >= 500:
            return "The update service is temporarily unavailable. Try again later."
        if detail.http_status == 404:
            return "Update information is unavailable. Check again later or open the download page."
        if detail.tls_verify_code is not None:
            return "The secure connection to the update service could not be verified. Try again later."
        if detail.reason == "network":
            return "Could not check for updates. Check your connection and try again."
    return "Could not check for updates. The cause is unknown. Try again or open the download page."


class QtUpdateSession:
    """Only thread handoff and current UI intent; updates.py retains authority."""

    def __init__(self, current_version: str) -> None:
        self.telemetry: ProductTelemetryOwner | None = None
        self._operation: BoundProductOperation | None = None
        self._attempt = str(uuid.uuid4())
        self._trigger = "manual"
        self._shown = False
        self._started = time.monotonic()
        self.current_version = current_version
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.release: ReleaseInfo | None = None
        self.ready: Path | MacUpdatePlan | None = None
        self.repair = False
        self.status = "Check for updates when you're ready."
        self.available = False
        self.manual = False
        self.recovery = False
        self.check_failed = False
        self.busy = False
        self.stage = "check"
        self.pending_install = False
        self.automatic_download = False
        self._ready_digest: str | None = None
        self._download_cancel = threading.Event()
        self.handoff_started = False
        self.observations: list[tuple[str, dict[str, str] | None]] = []

    @staticmethod
    def _version(value: str) -> str:
        value = value.removeprefix("v")
        return (
            value
            if re.fullmatch(
                r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}(?:-[A-Za-z0-9.-]{1,32})?", value
            )
            else "unknown"
        )

    def _begin_observation(self, trigger: str) -> None:
        self._attempt = str(uuid.uuid4())
        self._trigger = trigger
        self._shown = False
        self._started = time.monotonic()
        self._operation = bind_operation(
            self.telemetry, "updater_operation", operation_key=self._attempt
        )

    def observe(
        self, action: str, *, error: BaseException | None = None, blocker: str = "none"
    ) -> None:
        if action == "shown":
            if self._shown:
                return
            self._shown = True
        # Never rebind delayed work after an analytics choice changes.
        operation(
            self.telemetry,
            "updater_operation",
            action,
            self._operation,
            {
                "update_attempt": self._attempt,
                "update_from": self._version(self.current_version),
                "update_target": self._version(self.release.version)
                if self.release
                else "unknown",
                "update_trigger": self._trigger,
                "update_stage": self.stage,
                "update_blocker": blocker,
                "processing_bucket": time_bucket(
                    max(0, time.monotonic() - self._started)
                ),
            },
            failure_detail=capture_failure(
                error,
                stage="download"
                if self.stage in {"download", "downloading_repair"}
                else "dispatch",
                inspect_text=False,
            )
            if error
            else None,
        )

    def _start(self, target: Any, name: str) -> bool:
        if self.busy:
            return False
        self.busy = True
        self.recovery = False
        self.worker = threading.Thread(target=target, name=name, daemon=True)
        self.worker.start()
        return True

    def check(self, *, automatic: bool = False) -> bool:
        if self.busy or self.pending_install or self.handoff_started:
            return False
        self.check_failed = False
        self._begin_observation("automatic" if automatic else "manual")
        self.stage = "check"
        self.release = None
        self.available = False
        self.manual = False
        self.observe("check_started")
        logging.getLogger(__name__).info("Update check started (%s).", self._trigger)
        if not self._start(self._check_worker, "vodforge-qt-update-check"):
            return False
        self.ready = None
        self._ready_digest = None
        self.release = None
        self.available = False
        self.manual = False
        self.stage = "check"
        self.status = "Checking for updates…"
        return True

    def _check_worker(self) -> None:
        try:
            self.events.put(("checked", fetch_latest_release()))
        except Exception as exc:  # noqa: BLE001 - release provider errors are user-visible
            self.events.put(
                (
                    "error",
                    (
                        str(exc),
                        capture_failure(
                            exc,
                            stage="analysis" if self.stage == "check" else "download",
                            inspect_text=False,
                        ),
                    ),
                )
            )
        finally:
            logging.getLogger(__name__).info(
                "Update check finished in %.3f seconds.",
                time.monotonic() - self._started,
            )

    def download(
        self,
        *,
        repair: bool = False,
        install_when_ready: bool = False,
        automatic: bool = False,
    ) -> bool:
        release = self.release
        if not repair and (release is None or not self.available):
            return False
        if self.busy or self.pending_install or self.handoff_started:
            return False
        if repair:
            self._begin_observation("repair")
            self.release = None
        self._download_cancel.clear()
        self.automatic_download = automatic
        self.stage = "downloading_repair" if repair else "download"
        self.observe("repair_started" if repair else "download_started")
        if not self._start(
            lambda: self._download_worker(
                release if not repair else None, automatic=automatic
            ),
            "vodforge-qt-update-download",
        ):
            return False
        self.repair = repair
        self.automatic_download = automatic
        self.check_failed = False
        self.pending_install = install_when_ready
        self.ready = None
        self._ready_digest = None
        self.stage = "downloading_repair" if repair else "download"
        self.status = "Downloading and verifying the installer…"
        return True

    def request_install_now(self) -> bool:
        """Promote the same staged/in-flight automatic payload to explicit restart."""
        if self.pending_install or self.handoff_started or self.repair:
            return False
        if self.ready is None and not (
            self.automatic_download and self.busy and self.stage == "download"
        ):
            return False
        self.automatic_download = False
        self._trigger = "manual"
        self.pending_install = True
        self.status = (
            "Update verified. VODForge will restart when active work has finished."
            if self.ready is not None
            else "Downloading update… VODForge will restart after verification and active work."
        )
        return True

    def cancel_automatic_download(self) -> None:
        if self.automatic_download:
            self._download_cancel.set()
            self.automatic_download = False
            self.pending_install = False

    def _download_worker(
        self, release: ReleaseInfo | None, *, automatic: bool = False
    ) -> None:
        try:
            release = release or fetch_latest_release()
            if semantic_version_key(release.version) < semantic_version_key(
                self.current_version
            ):
                raise RuntimeError("A repair cannot install an older release.")
            self.events.put(("release", release))
            destination = application_data_dir() / "updates" / release.tag_name
            path = (
                download_verified_update(
                    release, destination, cancelled=self._download_cancel.is_set
                )
                if automatic
                else download_verified_update(release, destination)
            )
            if self._download_cancel.is_set():
                raise InterruptedError("Automatic update download canceled.")
            payload: Path | MacUpdatePlan = path
            if is_macos():
                target_app = running_macos_app()
                if target_app is None:
                    raise RuntimeError(
                        "VODForge must be running from the packaged app to update itself."
                    )
                cleanup_stale_macos_updates(destination)
                payload = prepare_macos_update(
                    path, target_app, expected_version=release.version
                )
            elif is_windows():
                verify_windows_authenticode(path)
            fingerprint_path = (
                payload.source_app / "Contents/MacOS/VODForge"
                if isinstance(payload, MacUpdatePlan)
                else payload
            )
            with fingerprint_path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if self._download_cancel.is_set():
                raise InterruptedError("Automatic update download canceled.")
            self.events.put(("fingerprint", digest))
            self.events.put(("ready", payload))
        except InterruptedError:
            self.events.put(("cancelled", None))
        except Exception as exc:  # noqa: BLE001 - verified update failures retain app
            self.events.put(
                (
                    "error",
                    (
                        str(exc),
                        capture_failure(
                            exc,
                            stage="analysis" if self.stage == "check" else "download",
                            inspect_text=False,
                        ),
                    ),
                )
            )

    def poll(self) -> bool:
        """Apply the latest worker result on Qt's UI thread."""
        changed = False
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == "fingerprint" and isinstance(payload, str):
                self._ready_digest = payload
                continue
            if kind == "release" and isinstance(payload, ReleaseInfo):
                self.release = payload
                continue
            self.busy = False
            if kind == "cancelled":
                self.ready = None
                self.pending_install = False
                self.automatic_download = False
                self.status = (
                    "Automatic updates are off. Manual update remains available."
                )
                continue
            if kind == "checked" and isinstance(payload, ReleaseInfo):
                self.release = payload
                newer = is_newer_release(self.current_version, payload.version)
                self.available = (
                    newer and release_asset_for_platform(payload) is not None
                )
                self.manual = newer and not self.available
                self.status = (
                    f"VODForge {payload.tag_name} is available."
                    if self.available
                    else f"VODForge {payload.tag_name} is available on the download page."
                    if newer
                    else "VODForge is up to date."
                )
                logging.getLogger(__name__).info(
                    "Update check applied: available=%s manual=%s.",
                    self.available,
                    self.manual,
                )
                self.observe(
                    "available"
                    if self.available
                    else "unsupported"
                    if newer
                    else "current"
                )
            elif kind == "ready" and isinstance(payload, (Path, MacUpdatePlan)):
                self.ready = payload
                self.status = (
                    "Update verified. It will install when you quit VODForge."
                    if self.automatic_download
                    else "Verified installer ready."
                )
                self.observe("download_completed")
                self.observations.append(("download_completed", None))
            else:
                self.ready = None
                self.pending_install = False
                detail = (
                    payload[1]
                    if isinstance(payload, tuple) and len(payload) == 2
                    else None
                )
                # Failure to obtain release metadata says nothing about the
                # installed app. Retain repair for download/handoff recovery.
                self.check_failed = self.stage == "check"
                self.recovery = not self.check_failed
                self.status = (
                    _check_failure_status(detail)
                    if self.check_failed
                    else "Update needs attention. Try Repair or open the download page."
                )
                operation(
                    self.telemetry,
                    "updater_operation",
                    "failed",
                    self._operation,
                    {
                        "update_attempt": self._attempt,
                        "update_stage": self.stage,
                        "update_trigger": self._trigger,
                        "update_from": self._version(self.current_version),
                        "update_target": self._version(self.release.version)
                        if self.release
                        else "unknown",
                        "processing_bucket": time_bucket(
                            max(0, time.monotonic() - self._started)
                        ),
                    },
                    failure_detail=detail,
                )
                self.observations.append(("failed", {"update_stage": self.stage}))
        return changed

    def take_observations(self) -> list[tuple[str, dict[str, str] | None]]:
        observations = self.observations
        self.observations = []
        return observations

    def install(
        self,
        *,
        downloads_busy: bool,
        telemetry_permitted: bool,
        window_bounds: tuple[int, int, int, int] | None = None,
        relaunch_after_install: bool = True,
    ) -> bool:
        """Launch the verified helper before the UI is allowed to close."""
        payload = self.ready
        self.observe("install_requested")
        if payload is None or downloads_busy or self.busy:
            self.observe(
                "blocked",
                blocker="active_work"
                if downloads_busy
                else "busy"
                if self.busy
                else "not_ready",
            )
            self.status = "Finish active and queued work before installing."
            return False
        try:
            telemetry_permitted = bool(
                telemetry_permitted
                and self._operation is not None
                and self._operation.permitted()
            )
        except Exception:  # noqa: BLE001 - a failed consent observer cannot grant permission
            telemetry_permitted = False
        try:
            self.stage = "handoff"
            if isinstance(payload, MacUpdatePlan):
                launch_macos_update(
                    payload,
                    repair=self.repair,
                    relaunch_after_install=relaunch_after_install,
                    expected_digest=self._ready_digest,
                    expected_version=self.release.version if self.release else None,
                    telemetry_permitted=telemetry_permitted,
                    telemetry_token=uuid.UUID(self._attempt).hex,
                )
            elif is_windows() and payload.suffix.lower() == ".exe":
                launch_windows_update(
                    payload,
                    repair=self.repair,
                    relaunch_after_install=relaunch_after_install,
                    expected_digest=self._ready_digest,
                    expected_version=self.release.version if self.release else None,
                    telemetry_permitted=telemetry_permitted,
                    telemetry_token=uuid.UUID(self._attempt).hex,
                    window_bounds=window_bounds,
                )
            else:
                raise RuntimeError("This verified installer cannot be handed off here.")
        except Exception as exc:  # noqa: BLE001 - retain the app and offer recovery
            self.observe("failed", error=exc)
            self.pending_install = False
            self.recovery = True
            self.status = (
                "Update needs attention. Try Repair or open the download page."
            )
            self.observations.append(("failed", {"update_stage": "handoff"}))
            return False
        self.observe("handoff")
        self.pending_install = False
        self.handoff_started = True
        self.ready = None
        self.status = (
            "Installing update… VODForge will reopen afterward."
            if relaunch_after_install
            else "Installing update after closing…"
        )
        return True
