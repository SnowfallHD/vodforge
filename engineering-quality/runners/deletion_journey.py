"""Delete saved media through a packaged VODForge app's own buttons, unattended.

Companion to release_journey.py, using the same accessibility drivers and the
same isolated profile (telemetry off). Each deletion goes Library -> Details ->
More actions -> Move media to Trash -> Move to Trash, exactly as a user clicks.
Afterwards the script checks which folders remain, finds every moved file in
the real system Trash / Recycle Bin at the path the app recorded, checks its
bytes against the file before deletion, and takes it back out of the Trash into
the output folder, so the user's Trash keeps nothing from the run.

The media is one real YouTube video saved as MP4, MP3 and Original audio: three
Library items in three folders under one channel folder.

1. shared_channel - delete the MP3 while the MP4 is still there: the MP3 folder
                    goes; the MP4, the channel folder and Downloads stay
2. empty_sibling  - the MP4's files are removed outside the app (its folder is
                    empty); delete the Original audio: every folder up to and
                    including the channel goes, Downloads stays, and the MP4
                    stays in the Library as missing
3. user_file      - a file the user put in the channel folder keeps the channel
                    when the channel's only saved item is deleted

    python engineering-quality/runners/deletion_journey.py \
        --app /Applications/VODForge.app --output deletion-result
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_journey as rj

NOTE = "kept by the user\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DeletionJourney(rj.Journey):
    def __init__(self, app: Path, output: Path, youtube_url: str) -> None:
        super().__init__(app, output, youtube_url)
        self.returned = self.output / "returned-from-trash"
        self.taken: set[tuple[str, int, int]] = set()
        self.title = ""

    # Filesystem --------------------------------------------------------
    def files(self) -> dict[str, str]:
        return {str(p): sha256(p) for p in self.downloads.rglob("*") if p.is_file()}

    def history(self) -> list[dict[str, Any]]:
        path = next(self.home.rglob("download-history.json"), None)
        if path is None:
            return []
        data = json.loads(path.read_text("utf-8"))
        return data.get("items", []) if isinstance(data, dict) else data

    def journals(self) -> list[Path]:
        path = next(self.home.rglob("download-history.json"), None)
        if path is None:
            return []
        return sorted((path.parent / "file-operations").glob("*.json"))

    def completed_journals(self) -> int:
        count = 0
        for journal in self.journals():
            try:
                if json.loads(journal.read_text("utf-8")).get("state") == "completed":
                    count += 1
            except (OSError, ValueError):
                pass
        return count

    def take_back(self, case: str, before: dict[str, str]) -> list[dict[str, Any]]:
        """Check each file the app recorded as trashed, then move it back out."""
        destination = self.returned / case
        destination.mkdir(parents=True, exist_ok=True)
        receipts = []
        for journal in self.journals():
            document = json.loads(journal.read_text("utf-8"))
            for i, item in enumerate(document.get("items", [])):
                for j, step in enumerate(item.get("delete_steps", [])):
                    key = (journal.name, i, j)
                    trash = step.get("trash_path")
                    if key in self.taken or not trash:
                        continue
                    self.taken.add(key)
                    path = Path(trash)
                    digest = sha256(path) if path.is_file() else None
                    receipts.append(
                        {
                            "source": step.get("source"),
                            "trash": trash,
                            "intact": digest is not None
                            and before.get(step.get("source", "")) == digest,
                        }
                    )
                    if path.is_file():
                        shutil.move(
                            str(path), destination / f"{len(receipts)}-{path.name}"
                        )
                        if sys.platform == "win32" and path.name.startswith("$R"):
                            # This file's own Recycle Bin entry.
                            path.with_name("$I" + path.name[2:]).unlink(missing_ok=True)
        return receipts

    # UI ----------------------------------------------------------------
    def go(self, name: str) -> None:
        # The format picker can leave the quick options panel open over the
        # window; close it as a user would before navigating.
        panel = self.driver.find("AXButton", ("Close options",))
        if panel is not None:
            self.driver.press(panel)
            time.sleep(1)
        try:
            button = self.control("AXButton", (name,), 20, name)
        except rj.JourneyError:
            # What the window showed instead, for the failure report.
            report: dict[str, Any] = {
                "app_running": self.driver.process.poll() is None,
                "controls": self.driver.describe(),
            }
            if sys.platform == "win32":
                from pywinauto import Desktop

                report["desktop_windows"] = [
                    {
                        "title": w.window_text(),
                        "pid": w.process_id(),
                        "visible": w.is_visible(),
                        "class": w.class_name(),
                    }
                    for w in Desktop(backend="uia").windows(visible_only=False)
                    if w.process_id() == self.driver.process.pid
                ]
            (self.output / f"controls-missing-{len(self.steps)}.json").write_text(
                json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            raise
        self.driver.press(button)
        time.sleep(1.5)

    def download(self, fmt: str) -> Path:
        self.dismiss_first_run()
        self.go("Forge")
        before = self.saved_media()
        self.submit(self.youtube_url, format_label=fmt)
        media = self.wait_for_new_media(before, 300, f"the YouTube {fmt} download")
        self.probe(media)
        if not self.title:
            self.title = json.loads(
                (media.parent / "metadata.json").read_text("utf-8")
            )["title"]
        return media.parent

    def open_details(self) -> None:
        """Open the only card in Library's Audio section (the item to delete)."""
        self.go("Library")
        section = rj.wait_for(
            lambda: next(
                (t for t in self.driver.texts() if t.startswith("Audio, ")), None
            ),
            20,
            "the Audio section",
        )
        if section != "Audio, 1":
            raise rj.JourneyError(f"Expected one audio item, Library shows {section!r}")
        self.go(section)
        name = (f"Details for {self.title}",)
        cards = rj.wait_for(
            lambda: self.driver.find_all("AXButton", name), 30, "the card"
        )
        self.driver.press(cards[0])
        time.sleep(2)

    def delete_in_app(self) -> None:
        self.dismiss_first_run()
        done_before = self.completed_journals()
        self.open_details()
        self.go("More actions")
        self.driver.press(
            self.control(
                "AXButton", ("Move media to Trash",), 20, "Move media to Trash"
            )
        )
        self.driver.press(self.control("AXButton", ("Move to Trash",), 60, "confirm"))
        rj.wait_for(
            lambda: self.completed_journals() > done_before or None,
            120,
            "the app to finish moving the files to Trash",
        )
        time.sleep(1)
        # On Windows the title bar's close button is also named "Close".
        close = "fileActionDismissButton" if sys.platform == "win32" else "Close"
        self.driver.press(self.control("AXButton", (close,), 20, "Close"))
        time.sleep(1)

    def check(self, problems: list[str], trash, before: dict[str, str], gone: Path):
        expected = sorted(p for p in before if Path(p).parent == gone)
        moved = sorted(r["source"] for r in trash)
        if moved != expected:
            problems.append(f"moved {moved}, expected the folder's files {expected}")
        if not all(r["intact"] for r in trash):
            problems.append(f"a file in Trash does not match the original: {trash}")
        if gone.exists():
            problems.append("the deleted item's folder is still there")
        if not self.downloads.is_dir():
            problems.append("Downloads itself was removed")
        if problems:
            raise rj.JourneyError("; ".join(problems))

    # Journey -----------------------------------------------------------
    def run(self) -> dict[str, Any]:
        if self.output.exists() and any(self.output.iterdir()):
            raise rj.JourneyError(f"Refusing a non-empty output folder: {self.output}")
        self.output.mkdir(parents=True, exist_ok=True)
        state: dict[str, Path] = {}

        def launch():
            self.driver.launch(self.app, self.environment(), self.output / "app.log")
            self.wait_ready()
            return {"dismissed": self.dismiss_first_run()}

        def shared_channel():
            state["mp4"] = self.download("MP4")
            gone = self.download("MP3")
            state["channel"] = gone.parents[1]
            before = self.files()
            self.delete_in_app()
            trash = self.take_back("shared_channel", before)
            problems = []
            kept = {p: h for p, h in before.items() if Path(p).parent == state["mp4"]}
            if any(
                not Path(p).is_file() or sha256(Path(p)) != h for p, h in kept.items()
            ):
                problems.append("the MP4 changed")
            self.check(problems, trash, before, gone)
            return {"channel": state["channel"].name, "trash": trash}

        def empty_sibling():
            gone = self.download("Original audio")
            for child in state["mp4"].iterdir():
                child.unlink()  # Removed outside the app, as in Finder/Explorer.
            before = self.files()
            self.delete_in_app()
            trash = self.take_back("empty_sibling", before)
            problems = []
            if state["channel"].exists():
                left = sorted(str(p) for p in state["channel"].rglob("*"))
                problems.append(f"channel folder remains with {left}")
            if not any(r.get("vodforge_output_type") == "MP4" for r in self.history()):
                problems.append("the emptied MP4 is no longer in the Library")
            self.check(problems, trash, before, gone)
            return {"trash": trash}

        def user_file():
            gone = self.download("MP3")
            note = gone.parents[1] / "my notes.txt"
            note.write_text(NOTE, encoding="utf-8")
            before = self.files()
            self.delete_in_app()
            trash = self.take_back("user_file", before)
            problems = []
            if not note.is_file() or note.read_text("utf-8") != NOTE:
                problems.append("the user's file in the channel folder changed")
            self.check(problems, trash, before, gone)
            return {
                "trash": trash,
                "channel": sorted(p.name for p in note.parent.iterdir()),
            }

        leftover: list[dict[str, Any]] = []
        try:
            for name, action in (
                ("launch", launch),
                ("shared_channel", shared_channel),
                ("empty_sibling", empty_sibling),
                ("user_file", user_file),
            ):
                if not self.step(name, action):
                    break
        finally:
            try:
                if (
                    self.driver.process is not None
                    and self.driver.process.poll() is None
                ):
                    self.driver.close()
                    self.driver.process.wait(timeout=60)
            except Exception as exc:  # noqa: BLE001 - stopped below
                print(f"Normal close failed ({exc}); stopping the app", flush=True)
                try:
                    self.driver.kill()
                except OSError:
                    pass
            # Anything a failed step left in the system Trash.
            leftover = self.take_back("after_run", {})
        result = {
            "passed": len(self.steps) == 4 and all(s["passed"] for s in self.steps),
            "machine": {"platform": sys.platform, "arch": rj.platform.machine()},
            "app": str(self.app),
            "steps": self.steps,
            "taken_back_after_run": leftover,
        }
        (self.output / "deletion-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--youtube-url", default=rj.DEFAULT_YOUTUBE_URL)
    parser.add_argument(
        "--arch",
        choices=["arm64", "x86_64"],
        help="macOS: run a universal app as this architecture (x86_64 uses Rosetta)",
    )
    args = parser.parse_args(argv)
    if args.arch is not None:
        rj.MacDriver.arch = args.arch
    result = DeletionJourney(args.app, args.output, args.youtube_url).run()
    print(
        ("PASSED" if result["passed"] else "FAILED")
        + f": {args.output / 'deletion-result.json'}"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
