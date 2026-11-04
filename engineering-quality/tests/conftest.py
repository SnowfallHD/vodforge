from __future__ import annotations

import sys
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_ROOT.parent
for path in (str(HARNESS_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def no_leaked_child_process_observer():
    """A download sets a process-wide child-process observer and clears it when
    the run ends. A test that starts a run without finishing it would leave the
    observer behind, and a later test's fake processes would trip over it, so
    the outcome depended on test order. Clear it around every test."""
    from yt_downloader.download_service import set_active_child_process_observer

    set_active_child_process_observer(None)
    yield
    set_active_child_process_observer(None)
