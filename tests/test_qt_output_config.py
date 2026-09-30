"""Real Qt summary refreshes pending choices and preserves selected-job authority."""

from dataclasses import replace

from PySide6.QtCore import QCoreApplication, QEvent, QObject

from tests.test_qt_scene_port import qt_app, saved
from tests.test_run_identity import make_job
from yt_downloader.models import OutputType
from yt_downloader.qt_quick import main as qt_main


def test_summary_live_pending_and_selected_job(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        details = window.findChild(QObject, "forgeSourceDetails")
        bridge.setOutputFormat("MP3")
        for _ in range(10):
            app.processEvents()
        rows = details.property("selectedFacts")["rows"]
        assert rows[0]["value"] == "MP3"
        assert any(row["label"] == "Cover art" for row in rows)
        job = replace(
            make_job(tmp_path),
            output_type=OutputType.MP4,
            use_cookies=True,
            cookie_browser="firefox",
        )
        bridge._runtime.active_job = job
        bridge.runDeckChanged.emit()
        bridge.setOutputFormat("Original audio")
        for _ in range(10):
            app.processEvents()
        rows = details.property("selectedFacts")["rows"]
        assert rows[0]["value"] == "MP4"
        assert (
            next(row["value"] for row in rows if row["label"] == "YouTube access")
            == "Browser (Firefox)"
        )
        bridge._runtime.active_job = None
        bridge._runtime.history = [saved(tmp_path, "Legacy", "MP4")]
        bridge.historyChanged.emit()
        for _ in range(10):
            app.processEvents()
        facts = bridge.forgeSelectedFacts
        assert facts["heading"] == "Saved output — measured facts"
        assert facts["rows"][-1]["label"] == "Chosen settings"
        assert "not recorded" in facts["rows"][-1]["value"]
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
