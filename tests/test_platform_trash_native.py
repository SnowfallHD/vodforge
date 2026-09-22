"""Opt-in real system Trash check using a uniquely named temporary fixture only."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

from yt_downloader.platform_services import system_trash_available, trash_file

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_FILE_QA") != "1",
    reason="Requires explicitly enabled Mac native file QA",
)


def test_native_mac_trash_returns_recoverable_fixture_location(tmp_path):
    source = tmp_path / ("vodforge-qa-" + uuid.uuid4().hex + ".txt")
    source.write_bytes(b"VODForge isolated Trash fixture")
    assert system_trash_available()
    trashed = trash_file(source)
    assert trashed and not source.exists()
    recovered = Path(trashed)
    try:
        assert recovered.name == source.name
        assert recovered.read_bytes() == b"VODForge isolated Trash fixture"
    finally:
        # Restore this exact test fixture; never empty or enumerate system Trash.
        if not source.exists() and recovered.exists():
            recovered.rename(source)
    assert source.read_bytes() == b"VODForge isolated Trash fixture"
