"""Capture Tk detail states the four-route Qt port contact sheet cannot show."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import Quartz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "scripts" / "focus_ui_preview.py"
BASE = ("--approved", "--public-fixture", "--size", "1180x790")
CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("forge-active", "app.py Forge live state", ("--view", "forge")),
    ("forge-idle", "app.py Forge idle state", ("--idle",)),
    ("forge-mp3", "app.py Forge MP3 settings", ("--output-type", "MP3")),
    ("forge-run-actions", "app.py Run Deck actions", ("--run-actions",)),
    ("forge-all-runs", "app.py All Runs menu", ("--all-runs",)),
    ("forge-selected-details", "app.py selected run details", ("--selected-details",)),
    ("forge-output-details", "detail_ui.py output dialog", ("--output-details",)),
    ("forge-local-conversion", "local_audio_video_ui.py", ("--local-conversion",)),
    ("settings", "focus_settings_ui.py", ("--settings",)),
    (
        "settings-mp3",
        "focus_settings_ui.py MP3",
        ("--settings", "--output-type", "MP3"),
    ),
    (
        "library-annotation",
        "library_annotation_ui.py",
        ("--view", "library", "--annotation"),
    ),
    (
        "library-collection",
        "library_collection_ui.py",
        ("--view", "library", "--collection"),
    ),
    ("watch-home-fixture", "watch_scene_ui.py", ("--view", "watch")),
    ("player-mp4", "media_player_ui.py", ("--player", "MP4")),
    ("player-mp3", "media_player_ui.py", ("--player", "MP3")),
    ("analytics-consent", "analytics_consent_ui.py", ("--consent",)),
    (
        "welcome-1",
        "engagement_state.py WELCOME_SLIDES",
        ("--welcome", "--whats-new-slide", "1"),
    ),
    (
        "welcome-4",
        "engagement_state.py WELCOME_SLIDES",
        ("--welcome", "--whats-new-slide", "4"),
    ),
    (
        "welcome-6",
        "engagement_state.py WELCOME_SLIDES",
        ("--welcome", "--whats-new-slide", "6"),
    ),
    ("whats-new", "whats_new.py HIGHLIGHTS", ("--whats-new",)),
    ("did-you-know", "whats_new.py DID_YOU_KNOW_HIGHLIGHTS", ("--did-you-know",)),
    ("warning", "Tk warning dialog", ("--notice", "warning")),
    ("error", "Tk error dialog", ("--notice", "error")),
)
DESKTOP_OVERLAY_CASES = {"forge-run-actions", "forge-all-runs", "warning", "error"}


def capture_desktop_overlay(command: list[str], target: Path) -> tuple[int, str]:
    """Capture native menus/alerts that window-ID capture omits or blocks."""
    process = subprocess.Popen(
        command[:-2],
        cwd=ROOT,
        env={**os.environ, "VODFORGE_DISABLE_TELEMETRY": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(2.4)
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, 0
        )
        roots = [
            item
            for item in windows
            if item.get("kCGWindowOwnerPID") == process.pid
            and item.get("kCGWindowLayer") == 0
            and item.get("kCGWindowName") == "VODForge — UI Review"
        ]
        if len(roots) != 1:
            raise RuntimeError(f"Expected one attested QA root; found {len(roots)}")
        bounds = roots[0]["kCGWindowBounds"]
        rectangle = ",".join(
            str(round(value))
            for value in (
                bounds["X"],
                bounds["Y"],
                bounds["Width"],
                bounds["Height"],
            )
        )
        subprocess.run(
            ["/usr/sbin/screencapture", "-x", f"-R{rectangle}", str(target)],
            check=True,
            timeout=10,
        )
        return 0, ""
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def contact_sheet(output: Path, captures: list[dict]) -> None:
    image_width, gap, label_height = 570, 20, 36
    cells = []
    for entry in captures:
        with Image.open(output / entry["file"]) as original:
            image = original.convert("RGB")
        cells.append(
            (
                entry["name"],
                image.resize(
                    (image_width, round(image.height * image_width / image.width))
                ),
            )
        )
    row_height = max((image.height for _, image in cells), default=0) + label_height
    sheet = Image.new(
        "RGB",
        (1200, gap + ((len(cells) + 1) // 2) * (row_height + gap)),
        "#25212b",
    )
    painter = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(cells):
        x = gap + (index % 2) * (image_width + gap)
        y = gap + (index // 2) * (row_height + gap)
        painter.text((x, y + 8), name, fill="white", font=ImageFont.load_default())
        sheet.paste(image, (x, y + label_height))
    sheet.save(output / "detail-contact-sheet.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if "layout-qa-profile" not in str(Path.home()):
        parser.error("Run only with the isolated layout-qa-profile HOME")
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    captures, failures = [], []
    for name, owner, options in CASES:
        target = output / f"{name}.png"
        command = [
            sys.executable,
            str(PREVIEW),
            *BASE,
            *options,
            "--capture",
            str(target),
        ]
        try:
            if name in DESKTOP_OVERLAY_CASES:
                exit_code, stderr = capture_desktop_overlay(command, target)
            else:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    env={**os.environ, "VODFORGE_DISABLE_TELEMETRY": "1"},
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                exit_code, stderr = result.returncode, result.stderr
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            exit_code, stderr = 1, repr(error)
        if (
            exit_code
            or not target.is_file()
            or not target.stat().st_size
            or "Traceback" in stderr
        ):
            failures.append(
                {"name": name, "exit_code": exit_code, "stderr": stderr[-3000:]}
            )
            print(f"FAIL {name}", flush=True)
            continue
        with Image.open(target) as image:
            dimensions = list(image.size)
        captures.append(
            {
                "name": name,
                "source": owner,
                "file": target.name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "dimensions": dimensions,
                "capture_method": "attested-window-desktop-rectangle"
                if name in DESKTOP_OVERLAY_CASES
                else "own-window-id",
            }
        )
        print(f"PASS {name}", flush=True)
    contact_sheet(output, captures)
    (output / "detail-manifest.json").write_text(
        json.dumps(
            {"source_commit": source, "captures": captures, "failures": failures},
            indent=2,
        )
        + "\n"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
