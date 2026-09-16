"""Synthetic child process for the maintained interrupted-history contract."""

import sys
import time
from pathlib import Path

from yt_downloader import history

fixture_root = Path(sys.argv[1])
boundary = sys.argv[2]
ledger = fixture_root / "history.json"
marker = fixture_root / "boundary"
first = history.sanitize_history_record(
    {
        "id": "first",
        "title": "Original preserved",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(fixture_root / "first.mp4"),
    },
    fixture_root,
)
second = history.sanitize_history_record(
    {
        "id": "second",
        "title": "Accepted pending",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(fixture_root / "second.mp4"),
    },
    fixture_root,
)
history.save_history(ledger, [first])
history.stage_history_mutation(ledger, {"kind": "record", "record": second})


def pause():
    marker.write_text(boundary)
    while True:
        time.sleep(0.1)


if boundary == "accepted-journal":
    pause()
elif boundary == "saved-before-retirement":
    actual = history.Path.unlink

    def delayed_unlink(path, *args, **kwargs):
        if path == history.pending_history_path(ledger):
            pause()
        return actual(path, *args, **kwargs)

    history.Path.unlink = delayed_unlink
    history.load_history(ledger)
elif boundary == "normal-control":
    history.load_history(ledger)
    marker.write_text(boundary)
else:
    raise ValueError(boundary)
