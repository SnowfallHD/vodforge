from pathlib import Path

import pytest

from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress import PlaybackProgressOwner, progress_key


def row(video="one", provider="youtube.com", playlist="a", output="MP4"):
    return {
        "id": video,
        "webpage_url": f"https://{provider}/watch?v={video}",
        "playlist_id": playlist,
        "vodforge_output_type": output,
    }


def snap(position=30, status="Playing", duration=100):
    return PlaybackSnapshot(Path("/fixture.mp4"), status, position, duration, 0)


def test_watched_progress_survives_restart_and_shared_video_variants(tmp_path):
    path = tmp_path / "progress.json"
    owner = PlaybackProgressOwner(path)
    session = owner.begin(row())
    assert owner.observe(session, snap())
    owner.retire(session)
    fresh = PlaybackProgressOwner(path)
    fresh.load()
    assert fresh.resume_position(row(playlist="b", output="MP3")) == 30
    assert fresh.for_record(row()).fraction == 0.3
    assert fresh.for_record(row(provider="vimeo.com")) is None
    assert "youtube.com" not in path.read_text()
    assert "fixture.mp4" not in path.read_text()


def test_resume_acknowledgement_prevents_startup_zero_overwriting_progress(tmp_path):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    first = owner.begin(row())
    owner.observe(first, snap(60))
    resumed = owner.begin(row(), resume=True)
    assert not owner.observe(resumed, snap(0))
    assert not owner.observe(resumed, snap(1))
    assert owner.resume_position(row()) == 60
    assert owner.observe(resumed, snap(60.5))
    assert owner.resume_position(row()) == 60.5
    assert owner.observe(resumed, snap(4))
    assert owner.resume_position(row()) == 4


def test_late_session_cannot_update_or_retire_new_video(tmp_path):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    first = owner.begin(row())
    current = owner.begin(row("two"))
    assert not owner.observe(first, snap(70))
    owner.retire(first)
    assert owner.observe(current, snap(20))
    assert owner.for_record(row()) is None
    assert owner.for_record(row("two")).position == 20
    owner.retire(current)
    assert not owner.observe(current, snap(30))


@pytest.mark.parametrize(
    "status", ["Idle", "Ready", "Starting", "Stopped", "Failed", "Closed"]
)
def test_nonplayback_states_do_not_invent_watched_time(tmp_path, status):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    assert not owner.observe(owner.begin(row()), snap(status=status))
    assert owner.for_record(row()) is None


@pytest.mark.parametrize(
    "position,duration", [(float("nan"), 100), (30, float("inf")), (-1, 100), (0, 0)]
)
def test_invalid_progress_cannot_poison_ledger(tmp_path, position, duration):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    assert not owner.observe(owner.begin(row()), snap(position, duration=duration))
    assert not owner.path.exists()


def test_completed_media_restarts_and_changed_duration_never_resumes_wrong_edit(
    tmp_path,
):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    session = owner.begin(row())
    owner.observe(session, snap(40))
    assert owner.resume_position(row(), duration=20) == 0
    assert owner.resume_position(row(), duration=101) == 40
    owner.observe(session, snap(100, status="Ended"))
    assert owner.resume_position(row()) == 0
    assert owner.for_record(row()).completed


def test_corrupt_ledger_is_preserved_and_write_failure_is_throttled(
    tmp_path, monkeypatch
):
    import yt_downloader.playback_progress as module

    path = tmp_path / "progress.json"
    path.write_text("unrecognized data")
    owner = PlaybackProgressOwner(path)
    owner.load()
    owner.observe(owner.begin(row()), snap())
    owner.flush()
    assert path.read_text() == "unrecognized data"
    calls = []

    def denied(*args):
        calls.append(True)
        raise OSError("unavailable")

    monkeypatch.setattr(module, "write_private_bytes", denied)
    clock = [100.0]
    owner = PlaybackProgressOwner(tmp_path / "other.json", clock=lambda: clock[0])
    session = owner.begin(row())
    for pos in range(1, 50):
        owner.observe(session, snap(pos))
    assert len(calls) == 1
    clock[0] += 5
    owner.observe(session, snap(50))
    assert len(calls) == 2


def test_manual_restart_supersedes_resume_and_provider_identity_is_scoped(tmp_path):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    session = owner.begin(row())
    owner.observe(session, snap(50))
    session = owner.begin(row(), resume=True)
    owner.accept_manual_position(session)
    assert owner.observe(session, snap(0))
    assert owner.resume_position(row()) == 0
    assert progress_key(row()) != progress_key(row(provider="vimeo.com"))


@pytest.mark.parametrize(
    "position,duration", [(float("nan"), 100), (60, 0), (60, float("inf"))]
)
def test_invalid_resume_acknowledgement_cannot_retire_pending_seek(
    tmp_path, position, duration
):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    session = owner.begin(row())
    owner.observe(session, snap(60))
    session = owner.begin(row(), resume=True)
    assert not owner.observe(session, snap(position, duration=duration))
    assert not owner.observe(session, snap(0))
    assert owner.resume_position(row()) == 60


def test_numeric_overflow_in_persisted_progress_is_rejected_without_crashing(tmp_path):
    import json

    path = tmp_path / "progress.json"
    payload = {
        "schema_version": 1,
        "items": {
            progress_key(row()): {
                "position": 10**500,
                "duration": 100,
                "updated_at": 1,
            }
        },
    }
    original = json.dumps(payload)
    path.write_text(original)
    owner = PlaybackProgressOwner(path)
    owner.load()
    assert owner.for_record(row()) is None
    assert path.read_text() == original


def test_changed_media_duration_retires_inapplicable_resume_target(tmp_path):
    owner = PlaybackProgressOwner(tmp_path / "progress.json")
    session = owner.begin(row())
    owner.observe(session, snap(60))
    session = owner.begin(row(), resume=True)
    assert owner.observe(session, snap(0, duration=20))
    assert owner.observe(session, snap(3, duration=20))
    assert owner.resume_position(row()) == 3
