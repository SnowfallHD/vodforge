"""Qt event handoff for the existing verified update and helper owners."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from yt_downloader.history import application_data_dir
from yt_downloader.platform_services import is_macos, is_windows
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


class QtUpdateSession:
    """Only thread handoff and current UI intent; updates.py retains authority."""

    def __init__(self, current_version: str) -> None:
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
        self.busy = False
        self.stage = "check"
        self.observations: list[tuple[str, dict[str, str] | None]] = []

    def _start(self, target: Any, name: str) -> bool:
        if self.busy:
            return False
        self.busy = True
        self.recovery = False
        self.worker = threading.Thread(target=target, name=name, daemon=True)
        self.worker.start()
        return True

    def check(self) -> bool:
        if not self._start(self._check_worker, "vodforge-qt-update-check"):
            return False
        self.ready = None
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
            self.events.put(("error", str(exc)))

    def download(self, *, repair: bool = False) -> bool:
        release = self.release
        if not repair and (release is None or not self.available):
            return False
        if not self._start(
            lambda: self._download_worker(release if not repair else None),
            "vodforge-qt-update-download",
        ):
            return False
        self.repair = repair
        self.ready = None
        self.stage = "downloading_repair" if repair else "download"
        self.status = "Downloading and verifying the installer…"
        return True

    def _download_worker(self, release: ReleaseInfo | None) -> None:
        try:
            release = release or fetch_latest_release()
            if semantic_version_key(release.version) < semantic_version_key(
                self.current_version
            ):
                raise RuntimeError("A repair cannot install an older release.")
            destination = application_data_dir() / "updates" / release.tag_name
            path = download_verified_update(release, destination)
            payload: Path | MacUpdatePlan = path
            if is_macos():
                target_app = running_macos_app()
                if target_app is None:
                    raise RuntimeError(
                        "VODForge must be running from the packaged app to update itself."
                    )
                cleanup_stale_macos_updates(destination)
                payload = prepare_macos_update(path, target_app)
            elif is_windows():
                verify_windows_authenticode(path)
            self.events.put(("ready", payload))
        except Exception as exc:  # noqa: BLE001 - verified update failures retain app
            self.events.put(("error", str(exc)))

    def poll(self) -> bool:
        """Apply the latest worker result on Qt's UI thread."""
        changed = False
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            self.busy = False
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
            elif kind == "ready" and isinstance(payload, (Path, MacUpdatePlan)):
                self.ready = payload
                self.status = "Verified installer ready."
                self.observations.append(("download_completed", None))
            else:
                self.ready = None
                self.recovery = True
                self.status = (
                    "Update needs attention. Try Repair or open the download page."
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
    ) -> bool:
        """Launch the verified helper before the UI is allowed to close."""
        payload = self.ready
        if payload is None or downloads_busy or self.busy:
            self.status = "Finish active and queued work before installing."
            return False
        try:
            self.stage = "handoff"
            if isinstance(payload, MacUpdatePlan):
                launch_macos_update(
                    payload,
                    repair=self.repair,
                    telemetry_permitted=telemetry_permitted,
                )
            elif is_windows() and payload.suffix.lower() == ".exe":
                launch_windows_update(
                    payload,
                    repair=self.repair,
                    telemetry_permitted=telemetry_permitted,
                    window_bounds=window_bounds,
                )
            else:
                raise RuntimeError("This verified installer cannot be handed off here.")
        except Exception:  # noqa: BLE001 - retain the app and offer recovery
            self.recovery = True
            self.status = (
                "Update needs attention. Try Repair or open the download page."
            )
            self.observations.append(("failed", {"update_stage": "handoff"}))
            return False
        self.ready = None
        self.status = "Installing update… VODForge will reopen afterward."
        return True
