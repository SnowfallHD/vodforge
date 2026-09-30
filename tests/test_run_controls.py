"""Scope and execution retirement invariants for both Qt control surfaces."""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.qt_quick.run_controls import RunControlPresentation


def mapping(presentation, active):
    return [(row["label"], row["operation"]) for row in presentation.actions(active)]


@pytest.mark.parametrize(
    "batch,playlist,single,expected",
    [
        (False, False, False, [("Cancel download", "cancel")]),
        (
            False,
            True,
            False,
            [("Skip this video", "skip_item"), ("Stop playlist", "cancel")],
        ),
        (False, True, True, [("Cancel download", "cancel")]),
        (
            True,
            False,
            False,
            [("Skip this link", "skip_source"), ("Stop batch", "cancel")],
        ),
        (
            True,
            True,
            False,
            [
                ("Skip this video", "skip_item"),
                ("Skip playlist", "skip_source"),
                ("Stop batch", "cancel"),
            ],
        ),
        (
            True,
            True,
            True,
            [("Skip this link", "skip_source"), ("Stop batch", "cancel")],
        ),
    ],
)
def test_context_mapping_preserves_existing_operations(
    tmp_path, batch, playlist, single, expected
):
    owner = replace(make_job(tmp_path), batch_mode=batch, single_video_only=False)
    source = replace(
        owner,
        url="https://www.youtube.com/playlist?list=PLtest"
        if playlist
        else "https://www.youtube.com/watch?v=test",
        single_video_only=single,
    )
    if not batch:
        owner = source
    presentation = RunControlPresentation()
    presentation.observe(owner, "job_metadata", {"job": source, "info": {}})
    assert mapping(presentation, owner) == expected
    assert all(
        "Completed files" in row["description"] for row in presentation.actions(owner)
    )


def test_batch_source_boundary_retires_playlist_evidence(tmp_path):
    owner = replace(make_job(tmp_path), batch_mode=True, single_video_only=False)
    playlist = replace(owner, url="https://www.youtube.com/playlist?list=PLtest")
    video = replace(
        owner,
        url="https://www.youtube.com/watch?v=test&list=PLtest",
        single_video_only=True,
    )
    presentation = RunControlPresentation()
    presentation.observe(
        owner, "job_metadata", {"job": playlist, "info": {"playlist_id": "PLtest"}}
    )
    assert mapping(presentation, owner)[1] == ("Skip playlist", "skip_source")
    presentation.observe(owner, "job_log", {"job": owner, "line": "any parent event"})
    assert mapping(presentation, owner)[0] == ("Skip this link", "skip_source")
    presentation.observe(
        owner, "job_metadata", {"job": video, "info": {"playlist_id": "PLtest"}}
    )
    assert mapping(presentation, owner) == [
        ("Skip this link", "skip_source"),
        ("Stop batch", "cancel"),
    ]


@pytest.mark.parametrize("replacement", ["finished", "queued_successor", "equal_copy"])
def test_scope_retires_with_execution_owner(tmp_path, replacement):
    owner = replace(make_job(tmp_path), batch_mode=True, single_video_only=False)
    source = replace(owner, url="https://www.youtube.com/playlist?list=PLtest")
    presentation = RunControlPresentation()
    presentation.observe(owner, "job_metadata", {"job": source, "info": {}})
    next_owner = None if replacement == "finished" else replace(owner)
    if replacement == "queued_successor":
        next_owner = replace(
            make_job(tmp_path), batch_mode=False, single_video_only=True
        )
    assert "Skip playlist" not in [
        label for label, _ in mapping(presentation, next_owner)
    ]
    if next_owner is None:
        assert mapping(presentation, next_owner) == []


def test_foreign_and_terminal_metadata_cannot_change_active_scope(tmp_path):
    owner = replace(make_job(tmp_path), single_video_only=True)
    foreign = replace(owner, run_id="another-run", single_video_only=False)
    presentation = RunControlPresentation()
    for kind in ("job_metadata", "item_terminal", "history_record"):
        presentation.observe(
            owner, kind, {"job": foreign, "info": {"playlist_id": "PLtest"}}
        )
    assert mapping(presentation, owner) == [("Cancel download", "cancel")]


def test_source_event_capture_preserves_fifo_identity_and_empty_behavior():
    from queue import Empty

    from yt_downloader.qt_quick.run_controls import RunControlEvents

    events = RunControlEvents()
    metadata = ("job_metadata", {"job": object(), "info": {}})
    progress = ("progress", 12)
    boundary = ("job_log", {"job": object(), "line": "display text"})
    for event in (metadata, progress, boundary):
        events.put(event)
    assert events.get_nowait() is metadata
    assert events.get_nowait() is progress
    assert events.get_nowait() is boundary
    assert events.take_context_events() == [metadata, boundary]
    assert events.take_context_events() == []
    with pytest.raises(Empty):
        events.get_nowait()
