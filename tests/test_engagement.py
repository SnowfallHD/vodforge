from types import SimpleNamespace

from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    update_onboarding,
)
from yt_downloader.engagement_state import EngagementState
from yt_downloader.support_diagnostics import (
    failure_context,
    public_video_url,
    redact_line,
)


def test_new_profile_welcome_once_and_upgrade_never(tmp_path):
    fresh = EngagementState(tmp_path / "new" / "installation.json")
    assert fresh.welcome_pending
    fresh.presented_welcome()
    assert not EngagementState(fresh.path).welcome_pending
    old = tmp_path / "old"
    old.mkdir()
    (old / "settings.json").write_text("{}")
    assert not EngagementState(old / "installation.json").welcome_pending


def test_legacy_install_without_marker_is_not_first_run(tmp_path):
    path = tmp_path / "installation.json"
    load_or_create_installation_state(path)
    update_onboarding(path, welcome_eligible=False)
    assert not EngagementState(path).welcome_pending


def test_three_operations_deduplicate_and_survive_restart(tmp_path):
    owner = EngagementState(tmp_path / "installation.json")
    for _ in range(10):
        owner.completed_download("playlist-parent")
    owner.completed_download("second")
    assert not owner.rating_pending
    owner = EngagementState(owner.path)
    owner.completed_download("third")
    assert owner.rating_pending
    owner.presented_rating()
    assert not EngagementState(owner.path).rating_pending
    assert len(owner.snapshot()["rating_successes"]) == 3


def test_diagnostics_exclude_secrets_and_personal_locations():
    for line in (
        "Cookie: abc",
        "Authorization: Bearer abc",
        "password=abc",
        "--cookies-from-browser chrome",
    ):
        assert redact_line(line) == "[Sensitive diagnostic line omitted]"
    value = redact_line(
        "ERROR /Users/alice/video.mp4 https://secret.invalid/x?sig=123 alice@example.com"
    )
    assert all(secret not in value for secret in ("alice", "secret.invalid", "sig=123"))
    assert "alice" not in redact_line(r"ERROR C:\Users\alice\video.mp4")


def test_source_url_is_explicit_public_video_only():
    assert (
        public_video_url("https://youtube.com/watch?v=8mv2Gonsdog&list=private")
        == "https://www.youtube.com/watch?v=8mv2Gonsdog"
    )
    assert public_video_url("https://cdn.invalid/watch?v=8mv2Gonsdog") is None
    assert public_video_url("https://user:pass@youtube.com/watch?v=8mv2Gonsdog") is None


def test_diagnostics_only_take_relevant_bounded_job_lines():
    job = SimpleNamespace(
        output_type=SimpleNamespace(value="MP4"),
        quality_label="1080p",
        export_mode=SimpleNamespace(value="auto"),
        single_video_only=True,
        failure_diagnostic=None,
        url="https://youtube.com/watch?v=8mv2Gonsdog",
        activity_lines=["Unrelated title: my private movie"] * 100
        + ["ERROR: HTTP Error 403 Forbidden", "Cookie: secret"],
    )
    context = failure_context(job, "Download failed")
    assert "403" in context.diagnostics
    assert "private movie" not in context.diagnostics
    assert "secret" not in context.diagnostics
    assert len(context.diagnostics) <= 6000
    job.single_video_only = False
    assert failure_context(job, "Playlist partially failed").video_url is None


def test_only_completed_operations_count_not_partial_or_cancelled(
    tmp_path, monkeypatch
):
    from yt_downloader.engagement_ui import EngagementUI

    owner = object.__new__(EngagementUI)
    owner.state = EngagementState(tmp_path / "installation.json")
    owner.latest_failure = None
    monkeypatch.setattr(
        "yt_downloader.engagement_ui.failure_context", lambda *args: "failure"
    )
    for status in ("Partial", "Failed", "Cancelled", "Skipped", "Stopped"):
        owner.finished(SimpleNamespace(run_id=status), status, "done")
    assert not owner.state.rating_pending
    assert owner.state.snapshot().get("rating_successes", []) == []
    for run in ("one", "two", "three"):
        owner.finished(SimpleNamespace(run_id=run), "Completed", "done")
    assert owner.state.rating_pending
