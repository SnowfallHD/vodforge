from yt_downloader.archive_file_operations import FileOperationItem, FileOperationPlan
from yt_downloader.qt_quick.library_files import QtLibraryFiles


def test_missing_root_notice_does_not_claim_location_is_inaccessible(tmp_path):
    controller = QtLibraryFiles(tmp_path / "history.json")
    controller.action = "move"
    controller.events.put(
        (
            "plan",
            FileOperationPlan(
                (),
                (
                    FileOperationItem(
                        "legacy",
                        "snapshot",
                        None,
                        "unavailable",
                        reason="hierarchy_root_unknown",
                    ),
                ),
            ),
        )
    )
    assert controller.poll()
    assert not controller.eligible
    assert "original archive root is not recorded" in controller.status
    assert "could not be accessed" not in controller.status
    assert "No files will change" in controller.status
    assert controller.worker is None


def test_mixed_move_notice_explains_skipped_legacy_owner(tmp_path):
    controller = QtLibraryFiles(tmp_path / "history.json")
    controller.action = "move"
    controller.destination = tmp_path / "destination"
    controller.events.put(
        (
            "plan",
            FileOperationPlan(
                (),
                (
                    FileOperationItem(
                        "new", "snapshot", tmp_path / "video.mp4", "ready"
                    ),
                    FileOperationItem(
                        "legacy",
                        "snapshot",
                        None,
                        "unavailable",
                        reason="hierarchy_root_unknown",
                    ),
                ),
            ),
        )
    )
    assert controller.poll()
    assert controller.eligible
    assert "Move 1 verified" in controller.status
    assert "1 item(s) cannot move" in controller.status
    assert "Their files will be kept" in controller.status
    assert controller.worker is None
