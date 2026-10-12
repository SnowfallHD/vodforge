"""Application producer contracts, separate from transport/storage regressions."""

import pytest


@pytest.fixture(autouse=True)
def stable_architecture(monkeypatch):
    monkeypatch.setattr(
        "yt_downloader.telemetry_features.platform.machine", lambda: "x86_64"
    )


class Recorder:
    def __init__(self):
        self.events = []

    def record(self, name, **fields):
        self.events.append((name, fields))
