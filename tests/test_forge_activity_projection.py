"""The Tk and Qt Forge panes use the same bounded run activity projection."""

from yt_downloader.forge_activity import ForgeActivityProjection


def test_forge_activity_keeps_each_run_friendly_and_technical_views_distinct():
    owner = ForgeActivityProjection()
    assert owner.observe("one", "Video 1 of 2 — downloading")
    assert not owner.observe("one", "Video 1 of 2 — downloading")
    assert owner.observe("two", "Video 1 of 1 — transcoding")
    raw = "selected format 270+251\n12:34:56 [warning] the source skipped a fragment"
    friendly = owner.friendly("one", raw)
    assert "Video 1 of 2 · Downloading media" in friendly
    assert "Converting media" not in friendly
    assert "selected format" not in friendly
    assert "warning was reported" in friendly
    assert owner.observe("one", "Failed", "The download needs attention.")
    assert "The download needs attention." in owner.friendly("one", raw)
    assert "The download needs attention." not in owner.friendly("two", "")


def test_forge_activity_bounds_session_projection_without_truncating_durable_log():
    owner = ForgeActivityProjection()
    for index in range(140):
        assert owner.observe(f"run-{index}", "Completed")
    assert len(owner._runs) == 128
    assert "saved activity" in owner.friendly("run-0", "")
    assert "Download complete" in owner.friendly("run-139", "")
