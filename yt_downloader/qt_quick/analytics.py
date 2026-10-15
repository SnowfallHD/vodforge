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
    take_automatic_browser_claim_attempt,
)
from yt_downloader.install_attribution import (
    ClaimIssueResult,
    InstallationAttributionOwner,
)
from yt_downloader.product_telemetry import (
    PRODUCT_TELEMETRY_STATE_FILENAME,
    ProductTelemetryOwner,
)
from yt_downloader.run_state import RunRecoveryOwner
from yt_downloader.telemetry_policy import telemetry_collection_allowed


class QtAnalyticsSession:
    def __init__(
        self,
        directory: Path,
        app_version: str,
        recovery: RunRecoveryOwner,
        *,
        browser_opener: Callable[[str], bool] | None = None,
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
        self._closed = False
        self._choice_save_failed = False
        self._next_telemetry_flush = time.monotonic() + 30.0
        self._app_version = app_version
        self._attribution_path = installation_state_path(data_dir=directory)
        self._attribution = InstallationAttributionOwner(
            self._attribution_path,
            browser_opener=lambda *_args, **_kwargs: False,
        )
        self._attribution_work: ArchiveWorkOwner | None = None
        self._attribution_attempted = False
        self.installation_link_status = "unavailable"
        self.installation_link_message = ""
        self._link_opener: Callable[[str], bool] | None = None
        self._automatic_browser_opener = browser_opener
        self._automatic_browser_checked = False
        if not telemetry_collection_allowed():
            # Offline/preview QA must still show saved local facts. Never
            # create a new identity merely to render this disabled surface.
            if self._attribution_path.is_file():
                self._refresh_installation_link()
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
        )
        self.owner = owner
        self.telemetry = telemetry
        self.lifecycle = ApplicationLifecycle(telemetry, directory)
        self._refresh_installation_link()
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

        def resolve() -> None:
            try:
                saved = owner.saved_region_mode
                self._mode = (
                    saved
                    if saved is not None
                    else owner.resolve(deadline=self._deadline)
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
        state = owner.snapshot()
        if (
            self._mode in {"opt-in", "unknown"}
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
        self._refresh_installation_link()
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
        if (
            not self.allowed
            or self._attribution_attempted
            or self._attribution_work is not None
            or self._closed
        ):
            return
        self._attribution_attempted = True
        try:
            state = load_or_create_installation_state(self._attribution_path)
        except (OSError, ValueError):
            return
        if not self._attribution.needs_delivery(state):
            self._refresh_installation_link()
            return
        self._attribution_work = ArchiveWorkOwner()
        self.installation_link_status = "checking"

        telemetry = self.telemetry
        epoch = telemetry.posthog_admission_epoch() if telemetry is not None else None

        def deliver(_cancelled: threading.Event) -> bool:
            result = self._attribution.deliver_first_launch(
                state,
                app_version=self._app_version,
                cancelled=_cancelled.is_set,
                browser_handoff=False,
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

        self._attribution_work.submit("first_launch", deliver)

    def _refresh_installation_link(self) -> None:
        if self._attribution_work is not None:
            return
        try:
            state = load_or_create_installation_state(self._attribution_path)
            # Saved completion is a local fact, independent of permission to
            # issue/open/poll another link. Showing it must not grant consent.
            self.installation_link_status = (
                "linked"
                if state.attribution_claim_confirmed
                else "waiting"
                if state.attribution_claim_opened and state.attribution_claim_token
                else "ready"
                if state.attribution_claim_token
                else "unavailable"
            )
            if state.attribution_claim_confirmed:
                self.installation_link_message = (
                    "Referral associated with this installation."
                )
        except (OSError, ValueError, RuntimeError):
            self.installation_link_status = "unavailable"

    def request_installation_link(self, opener: Callable[[str], bool]) -> bool:
        """Recovery action; the website owns browser attribution permission."""
        if (
            self._closed
            or self.owner is None
            or self._attribution_work is not None
            or not telemetry_collection_allowed()
        ):
            return False
        self._link_opener = opener
        self.installation_link_status = "preparing"
        self.installation_link_message = "Preparing the installation link…"
        self._attribution_work = ArchiveWorkOwner()
        self._attribution_work.submit(
            "browser_link",
            lambda cancelled: self._attribution.prepare_browser_attribution(
                cancelled=cancelled.is_set
            ),
        )
        return True

    def _start_automatic_browser_attribution(self) -> None:
        if (
            self._closed
            or not self._started
            or self.owner is None
            or not telemetry_collection_allowed()
            or self._automatic_browser_opener is None
            or self._automatic_browser_checked
            or self._attribution_work is not None
        ):
            return
        self._automatic_browser_checked = True
        try:
            state = load_or_create_installation_state(self._attribution_path)
            if state.attribution_claim_confirmed:
                self._refresh_installation_link()
                return
            if state.attribution_claim_opened and state.attribution_claim_token:
                self._start_browser_confirmation()
                return
            admitted = take_automatic_browser_claim_attempt(self._attribution_path)
        except (OSError, ValueError, RuntimeError):
            return
        if admitted:
            self.request_installation_link(self._automatic_browser_opener)

    def _start_browser_confirmation(self) -> None:
        self._attribution_work = ArchiveWorkOwner()
        self._attribution_work.submit(
            "browser_confirmation",
            lambda cancelled: self._attribution.poll_browser_attribution(
                cancelled=cancelled.is_set
            ),
        )

    def poll_first_launch_delivery(self) -> None:
        """Poll startup work and retry the existing outbox while Qt is idle."""
        if self._closed:
            return
        if self.lifecycle is not None and self._presented:
            self.lifecycle.tick()
        work = self._attribution_work
        if work is not None:
            result = work.poll()
            if result is not None:
                work.close()
                self._attribution_work = None
                if result.kind == "browser_link":
                    opener, self._link_opener = self._link_opener, None
                    claim = result.value
                    opened = False
                    if (
                        not result.error
                        and isinstance(claim, ClaimIssueResult)
                        and opener is not None
                        and self.owner is not None
                        and not self._closed
                        and telemetry_collection_allowed()
                    ):
                        try:
                            opened = bool(opener(claim.claim_url))
                        except (OSError, ValueError, RuntimeError):
                            opened = False
                        if opened:
                            opened = (
                                self._attribution.record_browser_attribution_opened(
                                    claim.claim_url, cancelled=lambda: self._closed
                                )
                            )
                    self.installation_link_message = (
                        "Browser opened. Waiting for confirmation."
                        if opened
                        else "Installation link could not be opened. Try again."
                    )
                    if opened:
                        self._start_browser_confirmation()
                elif result.kind == "browser_confirmation" and not result.value:
                    self.installation_link_message = (
                        "No referral confirmed yet. The website requires an eligible "
                        "saved referral and its browser permission."
                    )
                self._refresh_installation_link()
        self._start_automatic_browser_attribution()
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
        self._closed = True
        self._link_opener = None
        if self._attribution_work is not None:
            self._attribution_work.close()
            self._attribution_work = None
