"""Selected-item recovery controls bind the authoritative selection contract."""

from pathlib import Path

from yt_downloader.qt_quick import main as qt_main


def test_inspector_actions_use_authoritative_selection_and_keep_file_actions_separate():
    source = (Path(qt_main.__file__).parent / "LibraryFolderInspector.qml").read_text()
    start = source.index('objectName: "libraryInspectorRecoveryDetails"')
    panel = source[start:]
    assert "id: recoveryActionsRow" in source
    assert "id: recoveryDetailsScroll" not in source
    assert 'path: inspector.recoveryActions.location || ""' in source
    assert "visible: !!inspector.recoveryActions.canOpenLocation" in panel
    assert "openInspectorLocation(inspector.recoveryActions.selectionKey)" in panel
    # One Remove per item: "Remove run" only when the run saved no files;
    # otherwise the Trash button covers the run too.
    assert (
        "visible: !!inspector.recoveryActions.dismissRunId && "
        "!inspector.recoveryActions.savedOwner" in panel
    )
    assert "requestRunRemoval(inspector.recoveryActions.dismissRunId)" in panel
    assert 'label: "Remove run"' in panel
    assert "visible: !!inspector.recoveryActions.savedOwner" in panel
    assert (
        "requestInspectorLibraryRemoval(inspector.recoveryActions.selectionKey)"
        in panel
    )
    assert 'label: "Move to " + inspector.appBridge.trashName' in panel
