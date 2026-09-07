from types import SimpleNamespace

import pytest

from yt_downloader import analytics_startup as module
from yt_downloader.analytics_consent import AnalyticsConsentOwner


class Variable:
    def __init__(self):
        self.value = False
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in self.callbacks:
            callback()

    def trace_add(self, _event, callback):
        self.callbacks.append(callback)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "production_telemetry_allowed", lambda: True)
    opened, issued = [], []
    monkeypatch.setattr(
        module.webbrowser, "open", lambda url, **kwargs: opened.append((url, kwargs))
    )
    monkeypatch.setattr(
        module, "issue_claim", lambda iid, token: issued.append((iid, token)) or True
    )
    monkeypatch.setattr(module, "cancel_claim", lambda token: None)
    owner = AnalyticsConsentOwner(tmp_path)
    variable = Variable()
    startup = module.AnalyticsStartup(
        SimpleNamespace(after=lambda *_args: None),
        owner,
        variable,
        lambda _enabled: None,
    )
    return startup, owner, opened, issued


@pytest.mark.parametrize("mode", ["default-on", "opt-in", "unknown"])
def test_welcome_once_and_no_prepermission_identity(setup, mode):
    startup, owner, opened, issued = setup
    owner.update(mode=mode)
    startup._open_welcome()
    startup._authorize_ticket()
    startup._open_welcome()
    assert len(opened) == 1
    assert opened[0][0] == f"https://getvodforge.com/claim/#ticket={startup.ticket}"
    assert opened[0][1] == {"new": 2, "autoraise": False}
    assert bool(issued) is (mode == "default-on")


def test_late_opt_in_authorizes_same_ticket_without_second_tab(setup):
    startup, owner, opened, issued = setup
    startup._open_welcome()
    assert not issued
    owner.choose(True)
    startup._authorize_ticket()
    assert issued[0][1] == startup.ticket
    startup._authorize_ticket()
    assert len(issued) == 1
    startup._open_welcome()
    assert len(opened) == 1


def test_decline_timeout_and_shutdown_cannot_authorize(setup):
    startup, owner, opened, issued = setup
    owner.choose(False)
    startup._open_welcome()
    startup._authorize_ticket()
    owner.choose(True)
    startup.ticket_deadline = 0
    startup._authorize_ticket()
    startup.close()
    startup._open_welcome()
    assert not issued
    assert len(opened) == 1


def test_browser_failure_never_reopens_on_retry(setup, monkeypatch):
    startup, owner, opened, _issued = setup

    def fail(*args, **kwargs):
        opened.append("attempt")
        raise OSError()

    monkeypatch.setattr(module.webbrowser, "open", fail)
    startup._open_welcome()
    startup._open_welcome()
    assert opened == ["attempt"]
    assert owner.snapshot()["welcome_attempted"]


def test_private_build_never_opens_or_resolves(setup, monkeypatch):
    startup, _owner, opened, issued = setup
    monkeypatch.setattr(module, "production_telemetry_allowed", lambda: False)
    startup.start()
    startup._open_welcome()
    assert not opened and not issued
