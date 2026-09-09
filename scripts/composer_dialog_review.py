"""Isolated production-surface review; no user data or network operations."""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import Quartz

from scripts.focus_ui_preview import isolated_preview_services
from yt_downloader.app import DownloaderApp


def settle(app):
    for _ in range(12):
        app.update()
        time.sleep(0.025)


def capture(app, name):
    settle(app)
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, 0
    )
    window = next(
        w
        for w in windows
        if w.get("kCGWindowOwnerPID") == os.getpid() and w.get("kCGWindowLayer") == 0
    )
    output = Path("build/composer-dialog-review")
    output.mkdir(exist_ok=True)
    subprocess.run(
        [
            "screencapture",
            "-x",
            "-l",
            str(window["kCGWindowNumber"]),
            str(output / name),
        ],
        check=True,
    )


with isolated_preview_services():
    app = DownloaderApp()
    app.geometry("1180x780")
    app.deiconify()
    app.focus_force()
    settle(app)
    app.output_type_var.set("MP3")
    capture(app, "composer.png")
    app.focus_output_type_selector.open_popover()
    capture(app, "composer-open.png")
    app.focus_output_type_selector._close_popover()
    with patch.object(app, "_select_focus_view") as navigate:
        app.focus_run_overflow_button.invoke()
        navigate.assert_called_once_with("library")
    app._show_local_audio_video()
    dialog = app._local_audio_video_dialog
    capture(app, "image-preview.png")
    with patch("yt_downloader.app.choose_output_directory", return_value="/tmp"):
        dialog.destination_button.invoke()
    assert app.output_var.get() == "/tmp"
    assert dialog.destination_var.get() == "/tmp"
    for size in ("620x500", "700x570"):
        dialog.popup.geometry(size)
        settle(app)
        button = dialog.create_button
        assert button.winfo_y() >= 0
        assert button.winfo_rooty() + button.winfo_height() <= (
            dialog.popup.winfo_rooty() + dialog.popup.winfo_height()
        )
    dialog._destroy()
    app._request_application_close()
