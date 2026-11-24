"""Qt presentation adapter for the existing consent and telemetry owners.

The durable consent and event outbox stay in their current owners. This adapter
only schedules the existing bounded region lookup and exposes a prompt signal
to the Qt view; it never manufactures consent from a timeout.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.application_lifecycle import ApplicationLifecycle
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.cloud_funnel import (
    installation_state_path,
    load_or_create_installation_state,
)
from yt_downloader.first_launch import FirstLaunchDelivery
from yt_downloader.product_telemetry import (
    PRODUCT_TELEMETRY_STATE_FILENAME,
    ProductTelemetryOwner,
)
from yt_downloader.run_state import RunRecoveryOwner
from yt_downloader.telemetry_credentials import TelemetryCredentialOwner
from yt_downloader.telemetry_policy import (
    telemetry_collection_allowed,
    telemetry_site_origin,
)


class QtAnalyticsSession:
    def __init__(
        self,
        directory: Path,
        app_version: str,
        recovery: RunRecoveryOwner,
    ) -> None:
        self.owner: AnalyticsConsentOwner | None = None
        self.telemetry: ProductTelemetryOwner | None = None
        self.lifecycle: ApplicationLifecycle | None = None
        self._mode = "unknown"
        self._deadline = 0.0
        self._resolved = threading.Event()
        self._started = False
        self._presented = False
        self._opened = False
        self._baseline_started = False
        self._closed = False
        self._choice_save_failed = False
        self._next_telemetry_flush = time.monotonic() + 30.0
        self._app_version = app_version
        self._installation_path = installation_state_path(data_dir=directory)
        self._first_launch = FirstLaunchDelivery(self._installation_path)
        self._first_launch_work: ArchiveWorkOwner | None = None
        self._first_launch_attempted = False
        self._privacy_work: ArchiveWorkOwner | None = None
        self._privacy_opener: Callable[[str], bool] | None = None
        if not telemetry_collection_allowed():
            return
        owner = AnalyticsConsentOwner(directory)
        try:
            owner.migrate_data_sharing_choice()
        except (OSError, RuntimeError, ValueError):
            return  # An unreadable/unwritable migration cannot enable collection.
        initial_allowed = owner.allowed
        initial_epoch = owner.snapshot().get("collection_epoch")
        telemetry = ProductTelemetryOwner(
            state_path=directory / PRODUCT_TELEMETRY_STATE_FILENAME,
            installation_state_path=installation_state_path(data_dir=directory),
            app_version=app_version,
            enabled=initial_allowed,
            baseline_permitted=lambda: (
                not self._closed and owner.native_baseline_allowed
            ),
            policy_pending=lambda: self._started and not self._resolved.is_set(),
        )
        self.owner = owner
        self.telemetry = telemetry
        self.lifecycle = ApplicationLifecycle(telemetry, directory)
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
        return bool(
            not self._choice_save_failed
            and self.owner is not None
            and self.owner.allowed
        )

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
        owner = self.owner
        if owner is None or self._started:
            return
        self._started = True
        self._deadline = time.monotonic() + 2.5
        if owner.declined:
            # The user refused: no policy check either. Its answer could not
            # turn anything on, and the request alone reports an app launch.
            self._mode = owner.saved_region_mode or "unknown"
            self._resolved.set()
            return

        def resolve() -> None:
            try:
                saved = owner.saved_region_mode
                prior = owner.snapshot()
                self._mode = owner.resolve(deadline=self._deadline)
                if self._mode == "unknown" and saved is not None:
                    # Preserve the established rich-policy cache on outage;
                    # native baseline permission remains fresh-only and Off.
                    owner.update(
                        mode=saved,
                        posthog_mode=prior.get("posthog_mode", "opt-in"),
                        posthog_region_resolved=prior.get("posthog_region_resolved")
                        is True,
                    )
                    self._mode = saved
            except (OSError, ValueError):
                self._mode = "unknown"
            finally:
                self._resolved.set()
                # Send what was held during the refresh (or nothing, if the
                # answer turned analytics off: delivery re-reads the choice).
                if self.telemetry is not None:
                    self.telemetry.flush_async()

        threading.Thread(
            target=resolve, name="vodforge-qt-consent", daemon=True
        ).start()

    def poll(self) -> bool:
        """Return True exactly once when the existing owner requires a prompt."""
        owner = self.owner
        telemetry = self.telemetry
        if owner is None or telemetry is None or not self._started or self._presented:
            return False
        if not self._resolved.is_set() and time.monotonic() < self._deadline:
            return False
        self._presented = True
        try:
            owner.update(region_checked=True)
        except (OSError, RuntimeError, ValueError):
            telemetry.set_enabled(False)
            return False
        telemetry.set_enabled(owner.allowed)
        self._record_opened_if_allowed()
        if not self._baseline_started:
            self._baseline_started = True
            telemetry.record_baseline("app_started")
        state = owner.snapshot()
        # If the refresh hasn't answered yet, the saved answer decides, so a
        # slow network doesn't ask a default-on user for consent.
        mode = (
            self._mode
            if self._resolved.is_set()
            else owner.saved_region_mode or "unknown"
        )
        if (
            mode in {"opt-in", "unknown"}
            and not state.get("choice")
            and not state.get("prompted")
        ):
            try:
                owner.update(prompted=True)
            except (OSError, RuntimeError, ValueError):
                return False
            return True
        return False

    def choose(self, enabled: bool) -> bool:
        if self.owner is None or self.telemetry is None:
            return False
        try:
            self.owner.choose_data_sharing(enabled)
        except (OSError, RuntimeError, ValueError):
            self._choice_save_failed = True
            self.telemetry.set_enabled(False)
            return False
        self._choice_save_failed = False
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
        """Report this launch once per session, while analytics are on."""
        if (
            not self.allowed
            or self._first_launch_attempted
            or self._first_launch_work is not None
            or self._closed
        ):
            return
        self._first_launch_attempted = True
        try:
            state = load_or_create_installation_state(self._installation_path)
        except (OSError, ValueError):
            return
        if not self._first_launch.needs_delivery(state):
            return
        self._first_launch_work = ArchiveWorkOwner()

        telemetry = self.telemetry
        epoch = telemetry.posthog_admission_epoch() if telemetry is not None else None

        def deliver(_cancelled: threading.Event) -> bool:
            result = self._first_launch.deliver(
                state,
                app_version=self._app_version,
                cancelled=_cancelled.is_set,
            )
            if (
                result.first_launch_confirmed
                and not state.first_launch_confirmed
                and not self._closed
                and not _cancelled.is_set()
                and telemetry is not None
            ):
                telemetry.mirror_first_run_confirmed(state.install_id, epoch)
            return result.first_launch_confirmed

        self._first_launch_work.submit("first_launch", deliver)

    def request_privacy_action(
        self, request_kind: str, opener: Callable[[str], bool]
    ) -> bool:
        """Explicit Help action, independent of the optional analytics switch."""
        if self._closed or self._privacy_work is not None:
            return False
        if request_kind not in {"access", "deletion"}:
            return False
        owner = self.owner
        # After a refusal the launch policy check is skipped, so whether the
        # service takes requests is unknown until this explicit action asks.
        ask_first = (
            owner is not None
            and not owner.privacy_requests_available
            and owner.declined
        )
        if owner is None or not (owner.privacy_requests_available or ask_first):
            return bool(opener(f"{telemetry_site_origin()}/privacy/"))
        self._privacy_opener = opener
        self._privacy_work = ArchiveWorkOwner()
        credentials = TelemetryCredentialOwner(self._installation_path.parent)

        def issue(cancelled: threading.Event) -> str | None:
            if ask_first and not cancelled.is_set() and not self._closed:
                owner.resolve(user_requested=True)
            return credentials.issue_privacy_request(
                request_kind,
                permitted=lambda: (
                    not cancelled.is_set()
                    and not self._closed
                    and owner.privacy_requests_available
                ),
            )

        self._privacy_work.submit("privacy_request", issue)
        return True

    def poll_first_launch_delivery(self) -> None:
        """Poll startup work and retry the existing outbox while Qt is idle."""
        if self._closed:
            return
        privacy_work = self._privacy_work
        if privacy_work is not None:
            result = privacy_work.poll()
            if result is not None:
                privacy_work.close()
                self._privacy_work = None
                opener, self._privacy_opener = self._privacy_opener, None
                if opener is not None:
                    # Only the credential owner can construct a validated URL.
                    opener(
                        result.value
                        if not result.error and isinstance(result.value, str)
                        else f"{telemetry_site_origin()}/privacy/"
                    )
        if self.lifecycle is not None and self._presented:
            self.lifecycle.tick()
        work = self._first_launch_work
        if work is not None and work.poll() is not None:
            work.close()
            self._first_launch_work = None
        now = time.monotonic()
        if (
            self.allowed
            and self.telemetry is not None
            and now >= self._next_telemetry_flush
        ):
            self._next_telemetry_flush = now + 30.0
            # The durable owner retains event identity, consent and transport
            # backoff. Retrying must not require another feature interaction.
            self.telemetry.flush_async()

    def close(self) -> None:
        if self.lifecycle is not None:
            self.lifecycle.close()
        if self.telemetry is not None:
            # Anonymous counts live only in memory, and closing stops them, so
            # send what is pending first (bounded). Saved events wait in the
            # outbox for the next launch, as before.
            self.telemetry.flush_counts(timeout_seconds=1.0)
        self._closed = True
        self._privacy_opener = None
        if self._privacy_work is not None:
            self._privacy_work.close()
            self._privacy_work = None
        if self._first_launch_work is not None:
            self._first_launch_work.close()
            self._first_launch_work = None
