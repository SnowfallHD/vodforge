"""Actual offscreen QML source edits retire only the reviewed recovery draft."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from yt_downloader.history import load_history, save_history
from yt_downloader.qt_quick import main as qt_main

_APP = None


@pytest.mark.parametrize("input_delivery", ["text_change", "key_event"])
@pytest.mark.parametrize("replacement", ["", "https://www.youtube.com/watch?v=other"])
def test_actual_qml_source_edit_retires_draft_without_reviving_or_saving_defaults(
    tmp_path, monkeypatch, replacement, input_delivery
):
    global _APP
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    if _APP is None:
        QQuickStyle.setStyle("Basic")
        _APP = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    field = window.findChild(QObject, "forgeUrlInput")
    assert field is not None
    default = bridge._output_path
    bridge._export_mode = "Auto CBR"
    rows = [
        {
            "id": "abcdefghijk",
            "title": "Missing",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(tmp_path / "archive"),
            "vodforge_output_path": str(tmp_path / "archive/missing.mp4"),
            "vodforge_output_profile": "MP4 • 1080p Full HD • Auto CBR",
        }
    ]
    save_history(bridge._runtime.history_path, rows)
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    saves = []
    monkeypatch.setattr(
        bridge, "_schedule_preferences_save", lambda: saves.append(True)
    )
    try:
        assert not bridge.openLibraryItem(0)
        assert bridge.openMissingInForge(QUrl.fromLocalFile(str(tmp_path)))
        source = field.property("text")
        assert source == "https://www.youtube.com/watch?v=abcdefghijk"
        assert bridge.exportMode == "Everyday" and bridge.outputPath == str(tmp_path)
        saves.clear()
        # Re-emitting the prepared source or whitespace preserves the same draft.
        field.setProperty("text", source + " ")
        assert bridge.exportMode == "Everyday"
        field.setProperty("text", source)
        bridge.setExportMode("Manual Override")
        assert bridge.exportMode == "Manual Override"
        assert bridge._export_mode == "Auto CBR" and bridge._output_path == default
        if input_delivery == "text_change":
            field.setProperty("text", replacement)
        else:
            for _ in range(3):
                _APP.processEvents()
            field.forceActiveFocus()
            assert field.property("activeFocus")
            assert QMetaObject.invokeMethod(field, "selectAll", Qt.DirectConnection)
            QTest.keyClick(window, Qt.Key_Backspace if not replacement else Qt.Key_X)
        _APP.processEvents()
        assert bridge.exportMode == "Auto CBR"
        assert bridge.outputPath == default
        assert bridge._recovery_source_url == ""
        assert not bridge._media_recovery.is_draft_for(source)
        field.setProperty("text", source)
        _APP.processEvents()
        assert bridge.exportMode == "Auto CBR" and bridge.outputPath == default
        assert not bridge._media_recovery.is_draft_for(source)
        # Editing and retiring this draft does not save output defaults.
        assert not saves
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()
        bridge.close()


@pytest.mark.parametrize("accepted", [False, True])
def test_qt_send_retires_only_an_accepted_draft(tmp_path, monkeypatch, accepted):
    global _APP
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    if _APP is None:
        QQuickStyle.setStyle("Basic")
        _APP = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    source = "https://www.youtube.com/watch?v=abcdefghijk"
    default = bridge._output_path
    bridge._export_mode = "Auto CBR"
    bridge._recovery_source_url = source
    from yt_downloader.models import ExportMode

    bridge._media_recovery.prepare_destination(
        source, tmp_path, export_mode=ExportMode.EVERYDAY
    )
    admissions = []
    signals = []
    bridge.sourceAccepted.connect(lambda: signals.append(True))

    def controlled_start(*args, **kwargs):
        admissions.append(args)
        if not accepted:
            raise RuntimeError("Controlled admission refusal")
        return bridge._runtime.prepare_job(*args, **kwargs)

    monkeypatch.setattr(bridge._runtime, "start", controlled_start)
    try:
        assert bridge.submit(source, "MP4") is accepted
        assert len(admissions) == 1
        assert admissions[0][1] == tmp_path and admissions[0][3] == "Everyday"
        assert bridge._output_path == default and bridge._export_mode == "Auto CBR"
        assert signals == ([True] if accepted else [])
        assert bridge._media_recovery.is_draft_for(source) is not accepted
        assert bridge.exportMode == ("Auto CBR" if accepted else "Everyday")
        assert bridge.outputPath == (default if accepted else str(tmp_path))
    finally:
        bridge.close()
