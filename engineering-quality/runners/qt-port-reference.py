"""Capture current Tk scenes as a source-bound Qt port reference on macOS.

Run with an isolated HOME containing representative VODForge history. Captures
the real Tk window and route implementations; it does not change app state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import Quartz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.app import DownloaderApp
from yt_downloader.engagement_ui import EngagementUI


def settle(app: DownloaderApp, seconds: float = 0.45) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.update()
        time.sleep(0.01)


def owned_window() -> dict:
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, 0
    )
    candidates = [
        dict(item)
        for item in windows
        if item.get("kCGWindowOwnerPID") == os.getpid()
        and item.get("kCGWindowLayer") == 0
        and item.get("kCGWindowName") == "VODForge Qt Port Reference"
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one owned Tk window, found {len(candidates)}")
    return candidates[0]


def capture(app: DownloaderApp, output: Path, name: str, source: str) -> dict:
    settle(app)
    window = owned_window()
    target = output / f"{name}.png"
    subprocess.run(
        [
            "/usr/sbin/screencapture",
            "-x",
            "-o",
            "-l",
            str(window["kCGWindowNumber"]),
            str(target),
        ],
        check=True,
        timeout=10,
    )
    with Image.open(target) as image:
        dimensions = list(image.size)
    return {
        "name": name,
        "source": source,
        "file": target.name,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "dimensions": dimensions,
        "window_id": window["kCGWindowNumber"],
    }


def contact_sheet(output: Path, frames: list[dict]) -> None:
    width, image_width, gap, label_height = 1200, 570, 20, 42
    cells = []
    for entry in frames:
        with Image.open(output / entry["file"]) as original:
            image = original.convert("RGB")
        height = round(image.height * image_width / image.width)
        cells.append((entry["name"], image.resize((image_width, height))))
    row_height = max((image.height for _, image in cells), default=0) + label_height
    sheet = Image.new(
        "RGB",
        (width, gap + ((len(cells) + 1) // 2) * (row_height + gap)),
        "#25212b",
    )
    painter = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (name, image) in enumerate(cells):
        x = gap + (index % 2) * (image_width + gap)
        y = gap + (index // 2) * (row_height + gap)
        painter.text((x, y + 8), name, fill="white", font=font)
        sheet.paste(image, (x, y + label_height))
    sheet.save(output / "contact-sheet.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if sys.platform != "darwin":
        parser.error("This reference capture uses the macOS native window API")
    if "layout-qa-profile" not in str(Path.home()):
        parser.error("Run only with the isolated layout-qa-profile HOME")
    os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    frames: list[dict] = []
    app = None
    try:
        with (
            patch.object(AnalyticsStartup, "start", return_value=None),
            patch.object(EngagementUI, "start", return_value=None),
        ):
            app = DownloaderApp()
            app.title("VODForge Qt Port Reference")
            app.geometry("1180x790+40+40")
            settle(app, 0.8)

            for view in ("forge", "library", "watch", "activity"):
                app._select_focus_view(view)
                frames.append(
                    capture(app, output, view, f"app.py:_select_focus_view({view})")
                )

            app._select_focus_view("library")
            for route in (
                "all",
                "channels",
                "playlists",
                "collections",
                "videos",
                "audio",
            ):
                app.library_scene.navigate(route)
                frames.append(
                    capture(
                        app,
                        output,
                        f"library-{route}",
                        "library_scene_layout.py:_browse",
                    )
                )

            app._select_focus_view("watch")
            for route in ("channels", "playlists", "collections", "videos"):
                app.focus_watch._scene_open(route)
                frames.append(
                    capture(
                        app,
                        output,
                        f"watch-{route}",
                        "watch_scene_ui.py:_render_streaming_scene",
                    )
                )
    finally:
        if app is not None:
            app._request_application_close()
    contact_sheet(output, frames)
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "source_commit": source,
                "renderer": "Tk current app",
                "profile": "isolated layout-qa-profile",
                "captures": frames,
                "uncaptured_states": [
                    "Library and Watch item details",
                    "player, menus, dialogs, active download and errors",
                    "scroll positions and narrow or wide window variants",
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Captured {len(frames)} current Tk scenes in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
