"""Update a signed install through the app's own update path, with analytics on.

Runs a previous signed build (the baseline) in an isolated folder against the
local QA update feed, which serves the signed candidate. Telemetry goes to the
preview service only, never production.

1. Baseline: launch with analytics on (region US), let the automatic update
   download and verify, quit normally. The update must install on quit.
2. Candidate: open the updated app; it must report the new version.
3. Update window: serve the candidate again as a newer version and reopen. The
   update window must appear on launch; choose Later, then quit.

Everything stays under --root, which the QA feed requires: home, temporary
files, the app and the profile. The QA key is read from --qa-key-file and passed
only to the app's environment; it is never printed or written to the result.

    python engineering-quality/runners/update_journey.py \
        --root <run> --app <run>/app/VODForge.app \
        --candidate VODForge-macOS-arm64-v0.2.7.zip --candidate-version 0.2.7 \
        --qa-key-file <file>
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import release_journey as rj
from quality_harness import update_fixture

OFFER_BUTTONS = ("Install now", "Download update")
OFFER_HEADINGS = ("Update available", "Downloading update", "Waiting to restart")


def fixture_name(version: str) -> str:
    if sys.platform == "win32":
        return f"VODForge-Windows-Setup-v{version}.exe"
    return f"VODForge-macOS-arm64-v{version}.zip"


class UpdateJourney(rj.Journey):
    def __init__(
        self,
        root: Path,
        app: Path,
        candidate: Path,
        candidate_version: str,
        qa_key: str,
        output: Path | None = None,
    ) -> None:
        super().__init__(app, output or root / "journey", rj.DEFAULT_YOUTUBE_URL)
        self.root = root.resolve()
        self.home = self.root / "home"
        self.downloads = self.home / "Downloads"
        self.tmp = self.root / "tmp"
        self.profile_dir = self.home / "VODForge-profile"
        self.candidate = candidate.resolve(strict=True)
        self.candidate_version = candidate_version
        self.qa_key = qa_key
        self.feed_url = ""
        self.feeds: list[Path] = []
        self.launches = 0
        if not self.app.is_relative_to(self.root):
            raise rj.JourneyError("The app must be inside --root for the QA feed")

    # Environment -------------------------------------------------------
    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        for folder in (self.home, self.tmp, self.downloads, self.profile_dir):
            folder.mkdir(parents=True, exist_ok=True)
        for name in list(env):
            if name.startswith(("VODFORGE_", "SSL_CERT")):
                env.pop(name)
        env.update(
            HOME=str(self.home),
            TMPDIR=str(self.tmp),
            TMP=str(self.tmp),
            TEMP=str(self.tmp),
            XDG_DATA_HOME=str(self.home / ".local" / "share"),
            VODFORGE_QUALITY_E2E="1",
            VODFORGE_QA_PREVIEW_TELEMETRY="1",
            VODFORGE_QA_ACCESS_KEY=self.qa_key,
            VODFORGE_QA_PROFILE=str(self.profile_dir),
            VODFORGE_QA_COUNTRY="US",
            VODFORGE_QUALITY_E2E_ISOLATION_ROOT=str(self.root),
            VODFORGE_QA_UPDATE_FEED=self.feed_url,
            # Test-mode startup requires these on every platform.
            LOCALAPPDATA=str(self.home / "AppData" / "Local"),
        )
        # Each launch is attested once, so each gets its own session nonce.
        self.launches += 1
        nonce = uuid.uuid4().hex
        env.update(
            VODFORGE_QUALITY_E2E_SESSION_NONCE=nonce,
            VODFORGE_QUALITY_E2E_WINDOW_TOKEN=f"VFQ-{nonce[:12]}-L{self.launches}",
            VODFORGE_QUALITY_E2E_LAUNCH_ID=uuid.uuid4().hex,
        )
        if sys.platform == "win32":
            env.update(
                USERPROFILE=str(self.home),
                APPDATA=str(self.home / "AppData" / "Roaming"),
            )
        return env

    # Feed ----------------------------------------------------------------
    def start_feed(self, version: str) -> Path:
        assets = self.root / f"feed-assets-{version}"
        assets.mkdir()
        asset = assets / fixture_name(version)
        shutil.copy2(self.candidate, asset)
        output = self.root / f"feed-{version}"
        threading.Thread(
            target=update_fixture.serve,
            args=(version, [asset], output),
            daemon=True,
        ).start()
        feed = rj.wait_for(
            lambda: (output / "feed.json").is_file() and output / "feed.json",
            20,
            "the QA update feed",
        )
        self.feed_url = json.loads(feed.read_text("utf-8"))["url"]
        self.feeds.append(output)
        return output

    @staticmethod
    def requests(feed: Path) -> list[dict[str, Any]]:
        ledger = feed / "requests.jsonl"
        if not ledger.is_file():
            return []
        return [json.loads(line) for line in ledger.read_text().splitlines() if line]

    def asset_served(self, feed: Path, version: str) -> bool:
        name = fixture_name(version)
        return any(
            r["path"].endswith("/" + name) and r["status"] == 200
            for r in self.requests(feed)
        )

    # App facts -----------------------------------------------------------
    def installed_version(self) -> str:
        if sys.platform == "win32":
            exe = self.app / "VODForge.exe"
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Item -LiteralPath '{exe}').VersionInfo.ProductVersion",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            return out.strip()
        with (self.app / "Contents/Info.plist").open("rb") as handle:
            return str(plistlib.load(handle).get("CFBundleShortVersionString", ""))

    def receipts(self) -> list[dict[str, Any]]:
        found = []
        for path in sorted(self.profile_dir.rglob("handoff-*.json")):
            try:
                data = json.loads(path.read_text("utf-8-sig"))
            except (OSError, ValueError):
                continue
            found.append(
                {
                    "file": path.name,
                    "status": data.get("status"),
                    "installed_version": data.get("installed_version"),
                    "telemetry_permitted": data.get("telemetry_permitted"),
                    "error": data.get("error"),
                }
            )
        return found

    def outbox(self) -> list[dict[str, Any]]:
        path = self.profile_dir / "product-telemetry.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return []
        events = data.get("events", []) if isinstance(data, dict) else []
        return [
            {
                "event": e.get("event_name"),
                "feature": e.get("feature"),
                "action": e.get("action"),
            }
            for e in events
        ]

    def install_id(self) -> str | None:
        path = self.profile_dir / "installation.json"
        try:
            return json.loads(path.read_text("utf-8")).get("install_id")
        except (OSError, ValueError):
            return None

    def quit(self) -> int:
        self.driver.close()
        code = self.driver.process.wait(timeout=120)
        if code:
            raise rj.JourneyError(f"Quit exit code {code}")
        return code

    def _windows_elements(self) -> list[Any]:
        """Every element of every window this process owns.

        On Windows the update window is its own top-level window, so the main
        window's descendants don't include it.
        """
        from pywinauto import Desktop

        if self.driver.process is None:
            return []
        elements = []
        try:
            for window in Desktop(backend="uia").windows(
                process=self.driver.process.pid
            ):
                elements.append(window)
                elements.extend(window.descendants())
        except Exception:  # noqa: BLE001 - windows come and go while starting
            return []
        return elements

    def offer_control(self, object_name: str, labels: tuple[str, ...]):
        if sys.platform != "win32":
            return self.driver.find("AXButton", labels)
        for element in self._windows_elements():
            try:
                automation_id = element.element_info.automation_id or ""
                if (
                    automation_id.rsplit(".", 1)[-1] == object_name
                    or (
                        element.element_info.control_type == "Button"
                        and element.window_text() in labels
                    )
                ) and element.is_enabled():
                    return element
            except Exception:  # noqa: BLE001, S112 - element went away
                continue
        return None

    def all_texts(self) -> list[str]:
        if sys.platform != "win32":
            return self.driver.texts()
        texts = []
        for element in self._windows_elements():
            try:
                texts.append(element.window_text())
            except Exception:  # noqa: BLE001, S112 - element went away
                continue
        return texts

    def offer_visible(self) -> bool:
        if self.offer_control("updatePrimary", OFFER_BUTTONS) is None:
            return False
        texts = self.all_texts()
        return any(heading in texts for heading in OFFER_HEADINGS)

    # Journey ---------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        if self.output.exists():
            raise rj.JourneyError(f"Refusing an existing output folder: {self.output}")
        self.output.mkdir(parents=True)
        facts: dict[str, Any] = {"baseline_version": self.installed_version()}
        log = self.output / "app.log"

        def baseline():
            feed = self.start_feed(self.candidate_version)
            self.driver.launch(self.app, self.environment(), log)
            self.wait_ready()
            dismissed = self.dismiss_first_run()
            rj.wait_for(
                lambda: self.asset_served(feed, self.candidate_version),
                300,
                "the candidate download from the QA feed",
            )
            # Verification (signature, notarization) runs after the download.
            time.sleep(60)
            self.quit()
            installed = rj.wait_for(
                lambda: self.installed_version() == self.candidate_version,
                600,
                f"version {self.candidate_version} to be installed on quit",
            )
            # The update helper holds the update lock until it has written its
            # receipt; opening the app before then is refused ("finishing an
            # update"), as it is for a person who reopens straight away.
            rj.wait_for(
                lambda: any(r["status"] == "installed" for r in self.receipts()),
                180,
                "the update helper's installed receipt",
            )
            time.sleep(15)
            return {
                "dismissed": dismissed,
                "installed": bool(installed),
                "receipts": self.receipts(),
                "feed_requests": self.requests(feed),
            }

        def candidate():
            started = time.monotonic()
            self.driver.launch(self.app, self.environment(), log)
            self.wait_ready()
            ready = round(time.monotonic() - started, 1)
            self.dismiss_first_run()
            time.sleep(30)  # Report the install and let the outbox deliver.
            offered = self.offer_visible()
            version = self.installed_version()
            self.quit()
            if version != self.candidate_version:
                raise rj.JourneyError(f"Reopened app reports {version}")
            if offered:
                raise rj.JourneyError("An update window opened with no newer release")
            return {"version": version, "ready_seconds": ready}

        def update_window():
            newer = re.sub(
                r"(\d+)$", lambda m: str(int(m.group(1)) + 1), self.candidate_version
            )
            feed = self.start_feed(newer)
            started = time.monotonic()
            self.driver.launch(self.app, self.environment(), log)
            rj.wait_for(self.driver.window, 90, "the VODForge window")
            window_seconds = round(time.monotonic() - started, 1)
            dismissed: list[str] = []

            def offer_shown() -> bool:
                # The update window waits for any other open prompt to close.
                if self.offer_visible():
                    return True
                dismissed.extend(self.dismiss_first_run())
                return False

            try:
                rj.wait_for(offer_shown, 90, "the update window")
            except rj.JourneyError as exc:
                seen = [t for t in self.all_texts() if t][-40:]
                raise rj.JourneyError(f"{exc}; dismissed {dismissed}; shown {seen}")
            offer_seconds = round(time.monotonic() - started, 1)
            shot = self.output / "update-window.png"
            self.driver.screenshot(shot)
            texts = [t for t in self.all_texts() if t]
            later = rj.wait_for(
                lambda: self.offer_control("updateDismiss", ("Later",)), 10, "Later"
            )
            self.driver.press(later)
            rj.wait_for(lambda: not self.offer_visible(), 10, "the window to close")
            time.sleep(20)  # Let the shown/later observations deliver.
            self.quit()
            # The automatic download installs on quit; it is the same bytes under
            # a newer name, so the result is recorded rather than required.
            time.sleep(60)
            return {
                "offered_version": newer,
                "dismissed_before_offer": dismissed,
                "window_seconds": window_seconds,
                "offer_seconds_after_launch": offer_seconds,
                "offer_seconds_after_window": round(offer_seconds - window_seconds, 1),
                "offer_texts": [t for t in texts if t in OFFER_HEADINGS + OFFER_BUTTONS]
                + [t for t in texts if t.startswith(("It installs", "VODForge 0."))][
                    :4
                ],
                "receipts_after_quit": self.receipts(),
                "feed_requests": self.requests(feed),
            }

        try:
            for name, action in (
                ("baseline_install_on_quit", baseline),
                ("candidate_reopen", candidate),
                ("update_window_on_launch", update_window),
            ):
                if not self.step(name, action):
                    break
        finally:
            if self.driver.process is not None and self.driver.process.poll() is None:
                try:
                    self.quit()
                except Exception:  # noqa: BLE001 - stopped below
                    self.driver.kill()
        result = {
            "passed": len(self.steps) == 3 and all(s["passed"] for s in self.steps),
            "machine": {"platform": sys.platform, "arch": rj.platform.machine()},
            "app": str(self.app),
            "candidate": self.candidate.name,
            "candidate_version": self.candidate_version,
            **facts,
            "steps": self.steps,
            "installation_id": self.install_id(),
            "receipts": self.receipts(),
            "events_left_in_outbox": self.outbox(),
            "telemetry_target": "preview",
            "qa_markers": sorted(
                k for k in self.environment() if k.startswith("VODFORGE_")
            ),
        }
        (self.output / "update-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-version", required=True)
    parser.add_argument("--qa-key-file", type=Path, required=True)
    # The Windows journey script passes --output to every runner.
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    key = args.qa_key_file.read_text("utf-8").strip()
    if re.fullmatch(r"[0-9a-f]{64}", key) is None:
        raise SystemExit("The QA key file does not hold a preview key")
    result = UpdateJourney(
        args.root, args.app, args.candidate, args.candidate_version, key, args.output
    ).run()
    print(json.dumps({k: result[k] for k in ("passed", "installation_id")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
