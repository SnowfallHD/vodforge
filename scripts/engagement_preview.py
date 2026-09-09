"""Capture isolated production engagement surfaces; never submit or load user state."""

from __future__ import annotations

import argparse
import os
import subprocess
import tkinter as tk
from pathlib import Path

from yt_downloader.engagement_state import WELCOME_SLIDES
from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.support_ui import SupportPanel
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_theme import THEME
from yt_downloader.whats_new_ui import WhatsNewPanel


class OfflineTransport:
    def submit(self, *args):
        raise ValueError("Illustrative preview cannot submit")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("feedback", "review", "welcome"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = tk.Tk()
    root.title("VODForge — isolated design preview")
    root.geometry("960x700")
    root.configure(bg=THEME["bg"])
    apply_product_styles(root)
    root.update()
    if args.kind == "welcome":
        panel = WhatsNewPanel(
            root,
            WELCOME_SLIDES,
            lambda: None,
            heading="Welcome to VODForge",
            finish_label="Start using VODForge",
        )
        panel.render(2)
    else:
        panel = SupportPanel(
            root,
            kind=args.kind,
            transport=OfflineTransport(),
            closed=lambda: None,
            context=FailureContext(
                "Stage: downloading\nHTTP Error 403 Forbidden\nOutput: MP4, 1080p, Auto CBR",
                "https://www.youtube.com/watch?v=8mv2Gonsdog",
            ),
        )

    def capture():
        import Quartz

        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, 0
        )
        owned = [
            w
            for w in windows
            if w.get("kCGWindowOwnerPID") == os.getpid()
            and w.get("kCGWindowLayer") == 0
        ]
        if not owned:
            raise RuntimeError("No owned preview window")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "/usr/sbin/screencapture",
                "-x",
                "-o",
                "-l",
                str(owned[0]["kCGWindowNumber"]),
                str(args.output),
            ],
            check=True,
        )
        panel.close()
        root.destroy()

    root.after(1200, capture)
    root.mainloop()


if __name__ == "__main__":
    main()
