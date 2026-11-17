"""Update a signed install through the app's own update path, with analytics on.

Runs a previous signed build (the baseline) in an isolated folder against the
local QA update feed, which serves the signed candidate. Telemetry goes to the
preview service only, never production.

1. Baseline: launch with analytics on (region US), let the automatic update
   download and verify, quit normally. The update must install on quit.
2. Candidate: open the updated app; it must report the new version.
3. Update window: serve the candidate again as a newer version and reopen. The
   update window must appear on launch; choose Later, then quit.

With --scenario repair the first download fails (the feed answers 503), as the
0.2.7 Mac update did. The app must show "Update needs attention" by itself, and
Repair VODForge must install the candidate and reopen it.

On a Mac, the developer tools (Xcode, Command Line Tools) are made unavailable
to the app, as they are on most people's Macs: before 0.2.9 the updater needed
them and failed everywhere else, while every QA Mac had them. The journey first
proves the simulation works. On Windows, the helper's ready file is held open
the moment it appears, as an antivirus scan can, which failed a 0.2.6 handoff.

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
    """The asset the published release offers this platform's updater."""
    if sys.platform == "win32":
        return f"VODForge-Windows-Setup-v{version}.exe"
    return f"VODForge-macOS-universal2-v{version}.zip"


SCENARIOS = ("install_on_quit", "repair")
REPAIR_HEADING = "Update needs attention"
REPAIR_BUTTON = "Repair VODForge"


class UpdateJourney(rj.Journey):
    def __init__(
        self,
        root: Path,
        app: Path,
        candidate: Path,
        candidate_version: str,
        qa_key: str,
        output: Path | None = None,
        scenario: str = "install_on_quit",
        developer_tools: bool = False,
    ) -> None:
        super().__init__(app, output or root / "journey", rj.DEFAULT_YOUTUBE_URL)
        if scenario not in SCENARIOS:
            raise rj.JourneyError(f"Unknown scenario {scenario!r}")
        self.scenario = scenario
        # Only a Mac has developer tools to take away; Windows reports none.
        self.developer_tools = developer_tools and sys.platform != "win32"
        self.ready_locks: list[str] = []
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
        if sys.platform != "win32":
            # Builds from 0.2.9 never open the first-launch welcome page in
            # test mode. Older Qt builds open it through macOS, which ignores
            # BROWSER, so a public-release baseline still opens one preview tab
            # in the tester's browser; close it. BROWSER only covers older apps
            # that used Python's webbrowser module.
            env["BROWSER"] = "/usr/bin/true"
            if not self.developer_tools:
                # xcrun, stapler and the other developer-tool placeholders
                # fail here exactly as on a Mac without Xcode installed.
                env["DEVELOPER_DIR"] = str(self.root / "no-developer-tools")
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

    def developer_tools_present(self) -> bool:
        """Whether the app's environment can run Apple's developer tools."""
        if sys.platform == "win32":
            return False
        found = subprocess.run(
            ["/usr/bin/xcrun", "--find", "stapler"],
            env=self.environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.launches -= 1  # environment() counted a launch that didn't happen
        return found.returncode == 0

    def hold_ready_files(self, stop: threading.Event) -> None:
        """Hold each helper ready file open as soon as it appears (Windows).

        A scanner opening the new file is what made Windows refuse the app's
        delete in 0.2.6 (WinError 32). Python opens files without delete
        sharing, so holding one reproduces that refusal.
        """
        if sys.platform != "win32":
            return
        held: set[Path] = set()
        while not stop.is_set():
            for path in self.profile_dir.rglob("handoff-*.ready"):
                if path in held:
                    continue
                try:
                    handle = path.open("rb")
                except OSError:
                    continue
                held.add(path)
                self.ready_locks.append(path.name)
                threading.Timer(5, handle.close).start()
            time.sleep(0.005)

    def relaunched_pid(self, previous: int | None) -> int | None:
        """The VODForge the update helper reopened from this folder, if any."""
        import psutil

        executable = (
            self.app / "VODForge.exe"
            if sys.platform == "win32"
            else self.app / "Contents/MacOS/VODForge"
        ).resolve()
        for process in psutil.process_iter(["pid", "exe"]):
            try:
                exe = process.info["exe"]
                if (
                    exe
                    and Path(exe).resolve() == executable
                    and process.pid != previous
                ):
                    return process.pid
            except (psutil.Error, OSError):
                continue
        return None

    def adopt(self, pid: int) -> None:
        """Drive a VODForge this journey didn't start (reopened after Repair)."""
        import psutil

        class Adopted:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._process = psutil.Process(pid)
                self.returncode: int | None = None

            def poll(self) -> int | None:
                if self.returncode is None and not self._process.is_running():
                    self.returncode = 0
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                code = self._process.wait(timeout=timeout)
                self.returncode = 0 if code is None else code
                return self.returncode

        self.driver.process = Adopted(pid)  # type: ignore[assignment]
        if sys.platform == "win32":
            self.driver.app = self.driver.Application(backend="uia")
            rj.wait_for(self.driver._connect, 60, "UI Automation connection")
        else:
            self.driver.app = self.driver.ax.AXUIElementCreateApplication(pid)

    def wait_until_verified(self) -> None:
        """Wait for the update window's "Update verified" status."""
        if sys.platform == "win32":
            # UI Automation doesn't expose the window's status text; the
            # installer verifies in a few seconds there.
            time.sleep(60)
            return
        # macOS doesn't expose the window's status text either. The app unpacks
        # the update into a staged-* folder and checks it with ditto, codesign
        # and spctl; a failed check deletes the folder. A staged app with no
        # checker left running has passed.
        import psutil

        checkers = {"ditto", "codesign", "spctl"}
        quiet_since: list[float] = []

        def verified() -> bool:
            staged = list(self.profile_dir.glob("updates/*/staged-*/VODForge.app"))
            try:
                children = psutil.Process(self.driver.process.pid).children(
                    recursive=True
                )
                busy = any(child.name() in checkers for child in children)
            except psutil.Error:
                busy = True
            if not staged or busy:
                quiet_since.clear()
                return False
            quiet_since.append(time.monotonic())
            return quiet_since[-1] - quiet_since[0] >= 5

        rj.wait_for(verified, 600, "the app to verify the downloaded update")

    @staticmethod
    def set_unavailable(feed: Path, unavailable: bool) -> None:
        """Make only the download fail; the release itself is still found."""
        marker = feed / "assets-unavailable"
        if unavailable:
            marker.touch()
        else:
            marker.unlink(missing_ok=True)

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
        # Both of the update window's buttons; Windows doesn't expose its
        # heading text, so the heading is only a fallback for the Later button.
        # The relabelled "newer" release fails its version check once
        # downloaded, so the window may already be offering Repair.
        if (
            self.offer_control("updatePrimary", OFFER_BUTTONS + (REPAIR_BUTTON,))
            is None
        ):
            return False
        if self.offer_control("updateDismiss", ("Later",)) is not None:
            return True
        texts = self.all_texts()
        return any(heading in texts for heading in OFFER_HEADINGS + (REPAIR_HEADING,))

    # Journey ---------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        if self.output.exists():
            raise rj.JourneyError(f"Refusing an existing output folder: {self.output}")
        self.output.mkdir(parents=True)
        facts: dict[str, Any] = {
            "baseline_version": self.installed_version(),
            "scenario": self.scenario,
            "developer_tools_available": self.developer_tools_present(),
        }
        if facts["developer_tools_available"] != self.developer_tools:
            raise rj.JourneyError(
                "The developer-tools setting did not take effect for the app"
            )
        log = self.output / "app.log"
        stop_locks = threading.Event()
        threading.Thread(
            target=self.hold_ready_files, args=(stop_locks,), daemon=True
        ).start()

        def repair():
            feed = self.start_feed(self.candidate_version)
            self.set_unavailable(feed, True)
            self.driver.launch(self.app, self.environment(), log)
            self.wait_ready()
            dismissed = self.dismiss_first_run()
            name = fixture_name(self.candidate_version)
            rj.wait_for(
                lambda: any(
                    r["path"].endswith("/" + name) and r["status"] == 503
                    for r in self.requests(feed)
                ),
                300,
                "the failed first download",
            )
            self.set_unavailable(feed, False)

            def repair_offered():
                # The primary button reads Repair VODForge only when the update
                # needs attention. Windows doesn't expose the heading text.
                button = self.offer_control("updatePrimary", (REPAIR_BUTTON,))
                if button is not None:
                    return button
                dismissed.extend(self.dismiss_first_run())
                return None

            try:
                button = rj.wait_for(repair_offered, 120, "Update needs attention")
            except rj.JourneyError as exc:
                seen = [t for t in self.all_texts() if t][-40:]
                raise rj.JourneyError(f"{exc}; shown {seen}")
            self.driver.screenshot(self.output / "repair-offered.png")
            previous = self.driver.process.pid
            process = self.driver.process
            self.driver.press(button)

            def repaired() -> bool:
                # Collect the app's exit as macOS does for a real launch. An
                # uncollected child stays a zombie that still answers kill -0,
                # so the install script would wait for it until it gives up.
                process.poll()
                return self.installed_version() == self.candidate_version

            installed = rj.wait_for(
                repaired,
                600,
                f"Repair to install {self.candidate_version}",
            )
            rj.wait_for(
                lambda: any(
                    r["status"] in {"installed", "relaunched"} for r in self.receipts()
                ),
                180,
                "the repair helper's receipt",
            )
            # Repair reopens VODForge itself; that app must be the new version.
            pid = rj.wait_for(
                lambda: self.relaunched_pid(previous), 120, "VODForge to reopen"
            )
            self.adopt(pid)
            self.wait_ready()
            self.dismiss_first_run()
            time.sleep(20)  # Report the install and let the outbox deliver.
            self.quit()
            time.sleep(15)
            return {
                "reopened_by_repair": True,
                "dismissed": dismissed,
                "installed": bool(installed),
                "receipts": self.receipts(),
                "feed_requests": self.requests(feed),
            }

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
            # Unpacking and verifying the signature and notarization run after
            # the download; on the Intel test Mac that alone takes over a
            # minute. Quitting earlier leaves nothing to install.
            self.wait_until_verified()
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

        steps = (
            (("repair_after_failed_download", repair),)
            if self.scenario == "repair"
            else (("baseline_install_on_quit", baseline),)
        ) + (
            ("candidate_reopen", candidate),
            ("update_window_on_launch", update_window),
        )
        try:
            for name, action in steps:
                if not self.step(name, action):
                    break
        finally:
            stop_locks.set()
            if self.driver.process is not None and self.driver.process.poll() is None:
                try:
                    self.quit()
                except Exception:  # noqa: BLE001 - stopped below
                    self.driver.kill()
        result = {
            "passed": len(self.steps) == len(steps)
            and all(s["passed"] for s in self.steps),
            "format": "vodforge-update-journey/v2",
            "ready_files_held_open": self.ready_locks,
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
    parser.add_argument("--scenario", choices=SCENARIOS, default="install_on_quit")
    parser.add_argument(
        "--with-developer-tools",
        action="store_true",
        help="Leave Xcode available to the app (Mac); the release gate needs both",
    )
    # The Windows journey script passes --output to every runner.
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    key = args.qa_key_file.read_text("utf-8").strip()
    if re.fullmatch(r"[0-9a-f]{64}", key) is None:
        raise SystemExit("The QA key file does not hold a preview key")
    result = UpdateJourney(
        args.root,
        args.app,
        args.candidate,
        args.candidate_version,
        key,
        args.output,
        scenario=args.scenario,
        developer_tools=args.with_developer_tools,
    ).run()
    print(json.dumps({k: result[k] for k in ("passed", "installation_id")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
