"""Consent and outbox ownership across the Qt presentation boundary."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.models import CookieSource
from yt_downloader.qt_quick import analytics
from yt_downloader.qt_quick.main import Bridge


class _Recovery:
    def __init__(self) -> None:
        self.report_startup: bool | None = None

    def bind_observer(self, _observer: Any, *, report_startup: bool) -> None:
        self.report_startup = report_startup


class _Telemetry:
    instances: ClassVar[list[_Telemetry]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.path = kwargs["state_path"]
        self.installation = kwargs["installation_state_path"]
        self.enabled = kwargs["enabled"]
        self.opens = 0
        self.instances.append(self)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def record_app_opened(self) -> bool:
        if not self.enabled:
            return False
        self.opens += 1
        return True

    def record_operation(self, *_args: Any, **_kwargs: Any) -> None:
        pass


def _await_resolution(session: analytics.QtAnalyticsSession) -> None:
    deadline = time.monotonic() + 2
    while not session._resolved.is_set() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert session._resolved.is_set()


@pytest.fixture(autouse=True)
def _fake_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    _Telemetry.instances.clear()
    monkeypatch.setattr(analytics, "ProductTelemetryOwner", _Telemetry)


def test_qt_disabled_build_does_not_create_consent_or_outbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: False)
    recovery = _Recovery()
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.3", recovery)
    session.start()
    assert session.settled and not session.poll()
    session.choose(True)
    assert not session.allowed and not _Telemetry.instances
    assert recovery.report_startup is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mode", ["opt-in", "unknown"])
def test_qt_permission_waits_for_choice_and_revokes_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)

    def resolve(owner: AnalyticsConsentOwner, *, deadline: float) -> str:
        assert deadline > time.monotonic()
        owner.update(mode=mode)
        return mode

    monkeypatch.setattr(AnalyticsConsentOwner, "resolve", resolve)
    recovery = _Recovery()
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.3", recovery)
    assert session.telemetry is not None
    assert _Telemetry.instances[0].path == tmp_path / "product-telemetry.json"
    assert _Telemetry.instances[0].installation == tmp_path / "installation.json"
    assert recovery.report_startup is False
    session.start()
    _await_resolution(session)
    assert session.poll()
    assert session.settled and not session.allowed
    assert _Telemetry.instances[0].opens == 0
    session.choose(True)
    assert session.allowed and _Telemetry.instances[0].opens == 1
    session.choose(False)
    assert not session.allowed and not _Telemetry.instances[0].enabled
    assert not session.poll() and _Telemetry.instances[0].opens == 1
    assert AnalyticsConsentOwner(tmp_path).snapshot()["choice"] == "denied"


def test_qt_existing_permission_reports_recovery_and_one_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    owner = AnalyticsConsentOwner(tmp_path)
    owner.choose(True)
    owner.update(mode="opt-in", region_checked=True)
    recovery = _Recovery()
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.3", recovery)
    assert recovery.report_startup is True
    session.start()
    _await_resolution(session)
    assert not session.poll()
    assert session.allowed
    assert _Telemetry.instances[0].opens == 1
    assert not session.poll() and _Telemetry.instances[0].opens == 1


def test_qt_permission_write_failure_keeps_delivery_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.3", _Recovery())

    def refuse(_self: AnalyticsConsentOwner, _enabled: bool) -> None:
        raise OSError("private settings unavailable")

    monkeypatch.setattr(AnalyticsConsentOwner, "choose", refuse)
    assert not session.choose(True)
    assert not session.allowed
    assert not _Telemetry.instances[0].enabled
    assert _Telemetry.instances[0].opens == 0


def test_qt_first_play_denied_attempt_is_not_replayed_after_consent_change() -> None:
    observed: list[str] = []

    class Telemetry:
        def record(self, event_name: str, **_fields: Any) -> bool:
            observed.append(event_name)
            return False

    binding = SimpleNamespace(present=lambda _snapshot: None)
    fake = SimpleNamespace(
        _playback_binding=binding,
        _playback_recorded=False,
        _playback_output_type="MP4",
        _analytics=SimpleNamespace(telemetry=Telemetry()),
        _playback_snapshot=lambda: object(),
    )
    Bridge.observePlayback(fake, 0.1, 4.0, "Playing")
    Bridge.observePlayback(fake, 0.2, 4.0, "Playing")
    assert observed == ["playback_started"]


def test_qt_settings_snapshot_uses_allowlisted_dimensions_only() -> None:
    observed: list[dict[str, str]] = []

    class Telemetry:
        def permitted(self) -> bool:
            return True

        def record_feature(
            self, feature: str, action: str, *, dimensions: dict[str, str]
        ) -> None:
            assert (feature, action) == ("settings", "snapshot")
            observed.append(dimensions)

    fake = SimpleNamespace(
        _analytics=SimpleNamespace(telemetry=Telemetry()),
        _settings={"output_dir": "/private/customer/job", "quality": "1080p Full HD"},
        _output_format="MP4",
        _export_mode="Everyday",
        _quality="1080p Full HD",
        downloadOptions={"single_video_only": True},
        _manual_values={"manual_audio_bitrate": "320"},
        _mp3_values={},
        _cookie_source=CookieSource.PUBLIC,
    )
    Bridge._record_settings_snapshot(fake)
    assert observed and observed[0]["cookie_access"] == "disabled"
    assert "/private/customer/job" not in str(observed)
