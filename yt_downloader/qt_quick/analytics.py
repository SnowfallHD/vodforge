"""Qt presentation adapter for the existing consent and telemetry owners.

The durable consent and event outbox stay in their current owners. This adapter
only schedules the existing bounded region lookup and exposes a prompt signal
to the Qt view; it never manufactures consent from a timeout.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.cloud_funnel import (
    installation_state_path,
    load_or_create_installation_state,
)
from yt_downloader.install_attribution import InstallationAttributionOwner
from yt_downloader.product_telemetry import (
    PRODUCT_TELEMETRY_STATE_FILENAME,
    ProductTelemetryOwner,
)
from yt_downloader.telemetry_policy import telemetry_collection_allowed


class QtAnalyticsSession:
    def __init__(self, directory: Path, app_version: str, recovery: object) -> None:
        self.owner: AnalyticsConsentOwner | None = None
        self.telemetry: ProductTelemetryOwner | None = None
        self._mode = "unknown"
        self._deadline = 0.0
        self._resolved = threading.Event()
        self._started = False
        self._presented = False
        self._opened = False
        self._app_version = app_version
        self._attribution_path = installation_state_path(data_dir=directory)
        self._attribution = InstallationAttributionOwner(
            self._attribution_path,
            browser_opener=lambda *_args, **_kwargs: False,
        )
        self._attribution_work: ArchiveWorkOwner | None = None
        self._attribution_attempted = False
        if not telemetry_collection_allowed():
            return
        owner = AnalyticsConsentOwner(directory)
        initial_allowed = owner.allowed
        initial_epoch = owner.snapshot().get("collection_epoch")
        telemetry = ProductTelemetryOwner(
            state_path=directory / PRODUCT_TELEMETRY_STATE_FILENAME,
            installation_state_path=installation_state_path(data_dir=directory),
            app_version=app_version,
            enabled=initial_allowed,
        )
        self.owner = owner
        self.telemetry = telemetry
        recovery.bind_observer(
            telemetry.record_operation,
            report_startup=(
                initial_allowed
                and owner.allowed
                and initial_epoch == owner.snapshot().get("collection_epoch")
            ),
        )

    @property
    def allowed(self) -> bool:
        return bool(self.owner is not None and self.owner.allowed)

    @property
    def settled(self) -> bool:
        return self.owner is None or self._presented

    @property
    def update_receipt_decided(self) -> bool:
        """Unknown consent cannot discard an inherited update outcome."""
        return bool(
            self.owner is not None
            and self._presented
            and (
                self.owner.allowed
                or self.owner.snapshot().get("choice") in {"granted", "denied"}
            )
        )

    def start(self) -> None:
        if self.owner is None or self._started:
            return
        self._started = True
        self._deadline = time.monotonic() + 2.5

        def resolve() -> None:
            try:
                assert self.owner is not None
                saved = self.owner.saved_region_mode
                self._mode = (
                    saved
                    if saved is not None
                    else self.owner.resolve(deadline=self._deadline)
                )
            except (OSError, ValueError):
                self._mode = "unknown"
            finally:
                self._resolved.set()

        threading.Thread(
            target=resolve, name="vodforge-qt-consent", daemon=True
        ).start()

    def poll(self) -> bool:
        """Return True exactly once when the existing owner requires a prompt."""
        if self.owner is None or not self._started or self._presented:
            return False
        if not self._resolved.is_set() and time.monotonic() < self._deadline:
            return False
        self._presented = True
        assert self.telemetry is not None
        try:
            self.owner.update(region_checked=True)
        except (OSError, RuntimeError, ValueError):
            self.telemetry.set_enabled(False)
            return False
        self.telemetry.set_enabled(self.owner.allowed)
        self._record_opened_if_allowed()
        state = self.owner.snapshot()
        if (
            self._mode in {"opt-in", "unknown"}
            and not state.get("choice")
            and not state.get("prompted")
        ):
            try:
                self.owner.update(prompted=True)
            except (OSError, RuntimeError, ValueError):
                return False
            return True
        return False

    def choose(self, enabled: bool) -> bool:
        if self.owner is None or self.telemetry is None:
            return False
        try:
            self.owner.choose(enabled)
        except (OSError, RuntimeError, ValueError):
            self.telemetry.set_enabled(False)
            return False
        self.telemetry.set_enabled(self.owner.allowed)
        self._record_opened_if_allowed()
        return self.owner.allowed == enabled

    def _record_opened_if_allowed(self) -> None:
        if (
            self.telemetry is not None
            and self.allowed
            and not self._opened
            and self.telemetry.record_app_opened()
        ):
            self._opened = True

    def start_first_launch_delivery(self) -> None:
        """Use Tk's consent-gated attribution owner once per Qt session."""
        if not self.allowed or self._attribution_attempted:
            return
        self._attribution_attempted = True
        try:
            state = load_or_create_installation_state(self._attribution_path)
        except (OSError, ValueError):
            return
        if not self._attribution.needs_delivery(state):
            return
        self._attribution_work = ArchiveWorkOwner()

        def deliver(_cancelled: threading.Event) -> bool:
            result = self._attribution.deliver_first_launch(
                state, app_version=self._app_version
            )
            return result.first_launch_confirmed

        self._attribution_work.submit("first_launch", deliver)

    def poll_first_launch_delivery(self) -> None:
        work = self._attribution_work
        if work is not None and work.poll() is not None:
            work.close()
            self._attribution_work = None

    def close(self) -> None:
        if self._attribution_work is not None:
            self._attribution_work.close()
            self._attribution_work = None
