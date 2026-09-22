"""Actual queue/application telemetry producers with synthetic provider signals.

Real libVLC/file/presentation evidence is the separate native queue scenario.
"""

from types import SimpleNamespace

from yt_downloader.app import DownloaderApp
from yt_downloader.watch_queue import WatchQueueOwner, queue_media_key

QUEUE_CASES = tuple(
    "watch_queue_" + name
    for name in (
        "ordered",
        "shuffle",
        "single",
        "failed",
        "cancelled",
        "large",
        "cancel_after_ended",
        "record_removed",
        "saved_output_missing",
        "unexpected_ended",
        "open_resolve",
        "open_dependency",
        "open_initialization",
        "open_readiness",
        "open_load",
    )
)


def queue_case(directory, telemetry, case):
    count = 105 if case.endswith("large") else 1 if case.endswith("single") else 3
    records = [
        {
            "id": str(i),
            "title": "PRIVATE title",
            "webpage_url": f"https://youtube.com/watch?v={i}",
            "vodforge_output_dir": f"/PRIVATE/{i}",
            "vodforge_output_type": "MP4",
        }
        for i in range(count)
    ]
    app = SimpleNamespace(product_telemetry=telemetry)
    opened, scheduled = [], []
    owner = WatchQueueOwner(
        records=lambda: records,
        open_record=lambda row, token: opened.append((row, token)),
        schedule=scheduled.append,
        unavailable=lambda: None,
        shuffle=lambda keys: keys.reverse(),
        observe=lambda action, operation, dimensions, **extra: (
            DownloaderApp._record_watch_queue_operation(
                app, action, operation, dimensions, **extra
            )
        ),
    )
    shuffled = case.endswith("shuffle")
    owner.start(
        [queue_media_key(row) for row in records],
        kind="channel" if shuffled else "playlist",
        shuffled=shuffled,
    )
    while owner.token is not None:
        row, token = opened[-1]
        player = object()
        owner.attach(player, row, token)
        if case.endswith("unexpected_ended"):
            owner.present(player, "Ended")
            break
        if "watch_queue_open_" in case:
            from yt_downloader.archive_library_ui import ArchiveLibraryMixin
            from yt_downloader.failure_diagnostics import FailureDiagnostic

            app.watch_queue = owner
            app._archive_opening_operation = "opening"
            app._archive_opening_queue_token = owner.token
            app._archive_playback_origins = {}
            app._record_playback_operation = lambda *_a, **_k: None
            detail = FailureDiagnostic(
                reason="permission_denied", stage="playback", os_error=13
            )
            ArchiveLibraryMixin._archive_finish_opening(
                app,
                "opening",
                "failed",
                detail,
                dimensions={
                    "playback_failure_boundary": case.removeprefix("watch_queue_open_")
                },
            )
            break
        owner.present(player, "Playing")
        if case.endswith("record_removed"):
            records.pop(1)
        elif case.endswith("saved_output_missing"):
            records[1]["vodforge_output_dir"] = ""
        if case.endswith("failed"):
            owner.present(player, "Failed")
        elif case.endswith("cancelled"):
            owner.player_closed()
        else:
            owner.present(player, "Ended")
            if case.endswith("cancel_after_ended"):
                owner.player_closed()
            scheduled.pop(0)()
    expected = list(range(count))
    if shuffled:
        expected.reverse()
    if (
        case.endswith(
            (
                "failed",
                "cancelled",
                "cancel_after_ended",
                "record_removed",
                "saved_output_missing",
                "unexpected_ended",
            )
        )
        or "watch_queue_open_" in case
    ):
        expected = expected[:1]
    assert [int(row["id"]) for row, _ in opened] == expected
    assert not app._watch_queue_observations
    return {
        "case": case,
        "opened_count": len(opened),
        "synthetic_provider_signals": True,
        "native_provider_proof": "test_watch_queue_native.py",
    }
