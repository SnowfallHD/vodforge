"""Drive one packaged VODForge app through the pre-release journey, unattended.

Runs on the machine under test (Apple silicon Mac, Intel Mac or Windows PC) and
operates the real app through the operating system's accessibility interface
(macOS Accessibility / Windows UI Automation): controls are found by their
accessible names and pressed or typed into, exactly as assistive technology
does. Nothing inside the app is replaced or called directly.

Journey (each step records pass/fail, timings and a window screenshot):

1. launch        - fresh isolated profile, window appears, first-run popups closed
2. interrupt     - start a slow local download, then hard-kill the app mid-transfer
3. relaunch      - the interrupted run comes back as Paused/Retry
4. not_blocked   - a NEW download starts and completes while that run is held
5. resume        - the interrupted run resumes and completes
6. youtube_mp4 / youtube_mp3 - a real YouTube video downloads in both formats
7. reopen        - normal quit, relaunch, Library shows the saved items

Every saved file is checked with the app's own bundled ffprobe.

    python engineering-quality/runners/release_journey.py \
        --app /Applications/VODForge.app --output journey-result

Telemetry is disabled and all state lives under the output folder; the user's
real profile and Downloads are never touched.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))

from quality_harness.fault_server import FixtureHTTPServer
from quality_harness.fixtures import generate_fixtures

# Short, public, long-standing YouTube upload used by earlier QA rounds.
DEFAULT_YOUTUBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
# Prompts a user would dismiss: welcome tour, social invitation, rating request
# (shown after three completed downloads, once the app is idle).
FIRST_RUN_DISMISS = (
    "Get started",
    "Start using VODForge",
    "Skip tour",
    "Not now",
    "No thanks",
)
MEDIA_SUFFIXES = {".mp4", ".mp3", ".m4a", ".opus", ".webm"}


class JourneyError(RuntimeError):
    pass


def wait_for(
    check: Callable[[], Any], timeout: float, what: str, interval: float = 0.5
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(interval)
    raise JourneyError(f"Timed out after {timeout:.0f}s waiting for {what}")


# --- Platform drivers -------------------------------------------------------


class MacDriver:
    """macOS Accessibility. Reads only the VODForge window, never the menu bar."""

    source: Path | None = None  # Development: run main.py from this checkout.
    arch: str | None = None  # Run a universal app as this architecture.

    def __init__(self) -> None:
        import ApplicationServices as ax

        if not ax.AXIsProcessTrusted():
            raise JourneyError(
                "This process needs Accessibility permission "
                "(System Settings > Privacy & Security > Accessibility)."
            )
        self.ax = ax
        self.process: subprocess.Popen | None = None
        self.app = None

    def command(self, app: Path) -> list[str]:
        if self.source is not None:
            return [sys.executable, str(self.source / "main.py")]
        binary = [str(app / "Contents/MacOS/VODForge")]
        # arch replaces itself with the app, so the PID stays the app's.
        return ["/usr/bin/arch", f"-{self.arch}", *binary] if self.arch else binary

    def translated(self) -> bool | None:
        """Whether the running app is Intel code under Rosetta (P_TRANSLATED)."""
        if self.process is None or self.process.poll() is not None:
            return None
        out = subprocess.run(
            ["/bin/ps", "-o", "flags=", "-p", str(self.process.pid)],
            capture_output=True,
            check=False,
            text=True,
        ).stdout.strip()
        return bool(int(out, 16) & 0x20000) if out else None

    def helper(self, app: Path, name: str) -> Path:
        if self.source is not None:
            return Path(shutil.which(name) or name)
        for folder in ("Frameworks", "Resources", "MacOS"):
            candidate = app / "Contents" / folder / name
            if candidate.is_file():
                return candidate
        return app / "Contents/Frameworks" / name

    def launch(self, app: Path, env: dict[str, str], log: Path) -> None:
        handle = log.open("ab")
        self.process = subprocess.Popen(
            self.command(app),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
        )
        self.app = self.ax.AXUIElementCreateApplication(self.process.pid)

    def _attr(self, element, name):
        error, value = self.ax.AXUIElementCopyAttributeValue(element, name, None)
        return value if error == 0 else None

    def windows(self) -> list:
        """All app windows, the main window first (popups can be separate)."""
        windows = list(self._attr(self.app, "AXWindows") or [])
        main = self._attr(self.app, "AXMainWindow")
        if main is not None and main in windows:
            windows.remove(main)
            windows.insert(0, main)
        return windows

    def window(self):
        windows = self.windows()
        return windows[0] if windows else None

    def _walk(self, element, depth=0):
        yield element
        if depth < 40:
            for child in self._attr(element, "AXChildren") or []:
                yield from self._walk(child, depth + 1)

    def _label(self, element) -> str:
        for name in ("AXTitle", "AXDescription", "AXValue"):
            value = self._attr(element, name)
            if isinstance(value, str) and value:
                return value
        return ""

    def find(self, role: str, names: tuple[str, ...]):
        for window in self.windows():
            for element in self._walk(window):
                if (
                    self._attr(element, "AXRole") == role
                    and self._label(element) in names
                    and self._attr(element, "AXEnabled") is not False
                ):
                    return element
        return None

    def find_all(self, role: str, names: tuple[str, ...]) -> list:
        return [
            element
            for window in self.windows()
            for element in self._walk(window)
            if self._attr(element, "AXRole") == role
            and self._label(element) in names
            and self._attr(element, "AXEnabled") is not False
        ]

    def texts(self) -> list[str]:
        return [self._label(e) for window in self.windows() for e in self._walk(window)]

    def describe(self) -> list[dict[str, str]]:
        return [
            {"type": str(self._attr(e, "AXRole")), "name": self._label(e)}
            for window in self.windows()
            for e in self._walk(window)
        ]

    def press(self, element) -> None:
        if self.ax.AXUIElementPerformAction(element, "AXPress") != 0:
            raise JourneyError("Accessibility press failed")

    def set_text(self, element, text: str) -> None:
        self.ax.AXUIElementSetAttributeValue(element, "AXFocused", True)
        self.ax.AXUIElementSetAttributeValue(element, "AXValue", text)

    def text_of(self, element) -> str:
        value = self._attr(element, "AXValue")
        return value if isinstance(value, str) else ""

    def screenshot(self, path: Path) -> bool:
        import Quartz

        assert self.process is not None
        for info in Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
        ):
            if (
                info.get("kCGWindowOwnerPID") == self.process.pid
                and info.get("kCGWindowLayer") == 0
            ):
                result = subprocess.run(
                    [
                        "/usr/sbin/screencapture",
                        "-x",
                        "-o",
                        f"-l{info['kCGWindowNumber']}",
                        str(path),
                    ],
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                return result.returncode == 0 and path.exists()
        return False

    def close(self) -> None:
        window = self.window()
        button = self._attr(window, "AXCloseButton") if window is not None else None
        if button is None:
            raise JourneyError("Window close button not found")
        self.press(button)

    def kill(self) -> None:
        assert self.process is not None
        os.killpg(self.process.pid, signal.SIGKILL)


class WindowsDriver:
    """Windows UI Automation through pywinauto."""

    # Controls whose macOS accessible name comes from a placeholder have no UIA
    # name; match them by the QML objectName at the end of their automation ID.
    OBJECT_NAMES: ClassVar[dict[str, str]] = {
        "Paste a video URL": "forgeUrlInput",
        # Not "Close": that is also the window's own title-bar button.
        "fileActionDismissButton": "fileActionDismissButton",
    }

    def __init__(self) -> None:
        from pywinauto import Application, keyboard

        self.Application = Application
        self.keyboard = keyboard
        self.process: subprocess.Popen | None = None
        self.app = None

    @staticmethod
    def executable(app: Path) -> Path:
        return app / "VODForge.exe"

    @staticmethod
    def helper(app: Path, name: str) -> Path:
        for candidate in (app / "_internal" / f"{name}.exe", app / f"{name}.exe"):
            if candidate.is_file():
                return candidate
        return app / "_internal" / f"{name}.exe"

    @staticmethod
    def _label(element) -> str:
        return element.window_text()

    def launch(self, app: Path, env: dict[str, str], log: Path) -> None:
        handle = log.open("ab")
        self.process = subprocess.Popen(
            [str(self.executable(app))],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.app = self.Application(backend="uia")
        wait_for(self._connect, 60, "UI Automation connection")

    def _connect(self) -> bool:
        try:
            self.app.connect(process=self.process.pid, timeout=1)
            return True
        except Exception:  # noqa: BLE001 - window not there yet
            return False

    def window(self):
        try:
            windows = self.app.windows()
            if not windows and self.process is not None:
                # After a popup closes, the connected application can briefly
                # list no windows; ask the desktop for this process's windows.
                from pywinauto import Desktop

                windows = Desktop(backend="uia").windows(process=self.process.pid)
            return windows[0] if windows else None
        except Exception:  # noqa: BLE001 - process exiting
            return None

    def find(self, role: str, names: tuple[str, ...]):
        window = self.window()
        if window is None:
            return None
        control = {"AXButton": "Button", "AXTextField": "Edit"}[role]
        object_names = {self.OBJECT_NAMES[n] for n in names if n in self.OBJECT_NAMES}
        for element in window.descendants(control_type=control):
            automation_id = element.element_info.automation_id or ""
            if (
                element.window_text() in names
                or automation_id.rsplit(".", 1)[-1] in object_names
            ) and element.is_enabled():
                return element
        return None

    def find_all(self, role: str, names: tuple[str, ...]) -> list:
        window = self.window()
        if window is None:
            return []
        control = {"AXButton": "Button", "AXTextField": "Edit"}[role]
        return [
            e
            for e in window.descendants(control_type=control)
            if e.window_text() in names and e.is_enabled()
        ]

    def texts(self) -> list[str]:
        window = self.window()
        if window is None:
            return []
        return [e.window_text() for e in window.descendants()]

    def describe(self) -> list[dict[str, str]]:
        rows = []
        for window in self.app.windows():
            rows.append({"window": window.window_text(), "class": window.class_name()})
            for e in window.descendants():
                info = e.element_info
                rows.append(
                    {
                        "type": info.control_type,
                        "name": info.name,
                        "id": info.automation_id,
                    }
                )
        return rows

    def press(self, element) -> None:
        element.invoke()

    def set_text(self, element, text: str) -> None:
        element.set_edit_text(text)

    def text_of(self, element) -> str:
        return element.get_value() or ""

    def screenshot(self, path: Path) -> bool:
        window = self.window()
        if window is None:
            return False
        window.capture_as_image().save(path)
        return True

    def close(self) -> None:
        window = self.window()
        if window is None:
            raise JourneyError("Window not found")
        window.close()

    def kill(self) -> None:
        assert self.process is not None
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(self.process.pid)], check=False
        )


# --- Journey ----------------------------------------------------------------


class Journey:
    def __init__(self, app: Path, output: Path, youtube_url: str) -> None:
        self.app = app.resolve()
        self.output = output.resolve()
        self.youtube_url = youtube_url
        self.driver = WindowsDriver() if sys.platform == "win32" else MacDriver()
        self.home = self.output / "home"
        self.downloads = self.home / "Downloads"
        self.steps: list[dict[str, Any]] = []
        self.server: FixtureHTTPServer | None = None
        self.ffprobe = self.driver.helper(self.app, "ffprobe")

    # Environment -------------------------------------------------------
    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        tmp = self.output / "tmp"
        for folder in (self.home, tmp, self.downloads):
            folder.mkdir(parents=True, exist_ok=True)
        env.update(
            HOME=str(self.home),
            TMPDIR=str(tmp),
            TMP=str(tmp),
            TEMP=str(tmp),
            XDG_DATA_HOME=str(self.home / ".local/share"),
            VODFORGE_DISABLE_TELEMETRY="1",
        )
        if sys.platform == "win32":
            env.update(
                USERPROFILE=str(self.home),
                LOCALAPPDATA=str(self.home / "AppData/Local"),
                APPDATA=str(self.home / "AppData/Roaming"),
            )
        for name in ("VODFORGE_QUALITY_E2E", "VODFORGE_QA_PREVIEW_TELEMETRY"):
            env.pop(name, None)
        return env

    # Helpers -----------------------------------------------------------
    def saved_media(self) -> list[Path]:
        if not self.downloads.exists():
            return []
        return sorted(
            p
            for p in self.downloads.rglob("*")
            if p.is_file()
            and p.suffix.lower() in MEDIA_SUFFIXES
            and ".vfstage" not in p.parts
        )

    def probe(self, path: Path) -> dict[str, Any]:
        result = subprocess.run(
            [
                str(self.ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise JourneyError(
                f"ffprobe rejected {path.name}: {result.stderr.strip()[:200]}"
            )
        data = json.loads(result.stdout)
        streams = sorted({s.get("codec_type", "") for s in data.get("streams", [])})
        return {
            "file": path.name,
            "bytes": path.stat().st_size,
            "duration": round(float(data.get("format", {}).get("duration", 0) or 0), 2),
            "streams": streams,
        }

    def dismiss_first_run(self) -> list[str]:
        dismissed = []
        for _ in range(6):
            button = self.driver.find("AXButton", FIRST_RUN_DISMISS)
            if button is None:
                break
            dismissed.append(self.driver._label(button))
            self.driver.press(button)
            time.sleep(1.0)
        return dismissed

    def control(self, role: str, names: tuple[str, ...], timeout: float, what: str):
        """Wait for a control, dismissing prompts that may cover it meanwhile."""

        def look():
            found = self.driver.find(role, names)
            if found is None:
                self.dismiss_first_run()
            return found

        return wait_for(look, timeout, what)

    def wait_ready(self) -> None:
        wait_for(self.driver.window, 90, "the VODForge window")
        self.control("AXTextField", ("Paste a video URL",), 60, "the URL field")

    def submit(self, url: str, *, format_label: str | None = None) -> str:
        field = self.control("AXTextField", ("Paste a video URL",), 30, "the URL field")
        self.driver.set_text(field, url)
        wait_for(lambda: self.driver.text_of(field) == url, 10, "the URL to be entered")
        if format_label is not None:
            self.choose_format(format_label)
        button = self.control(
            "AXButton", ("Download", "Queue"), 20, "the Download button"
        )
        label = self.driver._label(button)
        self.driver.press(button)
        return label

    def choose_format(self, label: str) -> None:
        formats = ("MP4", "MP3", "Original audio")
        current = next(
            (
                t.removesuffix("▾").strip()
                for t in self.driver.texts()
                if t.endswith("▾") and t.removesuffix("▾").strip() in formats
            ),
            "",
        )
        if current == label:
            return
        selector = wait_for(
            lambda: next(
                (
                    b
                    for b in [
                        self.driver.find("AXButton", (f"{name}  ▾",))
                        for name in formats
                    ]
                    if b is not None
                ),
                None,
            ),
            10,
            "the format selector",
        )
        self.driver.press(selector)
        option = wait_for(
            lambda: self.driver.find("AXButton", (label,)), 10, f"the {label} option"
        )
        self.driver.press(option)
        wait_for(
            lambda: self.driver.find("AXButton", (f"{label}  ▾",)),
            10,
            f"{label} to be selected",
        )

    def wait_for_new_media(self, before: list[Path], timeout: float, what: str) -> Path:
        known = set(before)
        return wait_for(
            lambda: next(
                (p for p in self.saved_media() if p not in known and self._settled(p)),
                None,
            ),
            timeout,
            what,
            interval=1.0,
        )

    @staticmethod
    def _settled(path: Path) -> bool:
        try:
            first = path.stat().st_size
            time.sleep(0.5)
            return first > 0 and path.stat().st_size == first
        except OSError:
            return False

    # Steps -------------------------------------------------------------
    def step(self, name: str, action: Callable[[], dict[str, Any] | None]) -> bool:
        started = time.monotonic()
        record: dict[str, Any] = {"step": name}
        try:
            record.update(action() or {})
            record["passed"] = True
        except Exception as exc:  # noqa: BLE001 - record and continue to evidence
            record["passed"] = False
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["seconds"] = round(time.monotonic() - started, 1)
        shot = self.output / f"{len(self.steps) + 1:02d}-{name}.png"
        try:
            record["screenshot"] = shot.name if self.driver.screenshot(shot) else None
        except Exception:  # noqa: BLE001 - screenshot is evidence, not the check
            record["screenshot"] = None
        self.steps.append(record)
        print(
            f"{'PASS' if record['passed'] else 'FAIL'} {name} ({record['seconds']}s)"
            + (f": {record.get('error')}" if not record["passed"] else ""),
            flush=True,
        )
        return record["passed"]

    def run(self) -> dict[str, Any]:
        if self.output.exists() and any(self.output.iterdir()):
            raise JourneyError(f"Refusing a non-empty output folder: {self.output}")
        self.output.mkdir(parents=True, exist_ok=True)
        fixtures = generate_fixtures(
            self.output / "fixtures",
            ffmpeg_path=str(self.driver.helper(self.app, "ffmpeg")),
            ffprobe_path=str(self.ffprobe),
        )
        self.server = FixtureHTTPServer(
            self.output / "fixtures", slow_chunk_delay=0.1
        ).start()
        env = self.environment()
        log = self.output / "app.log"
        held: dict[str, Any] = {}
        launched: list[subprocess.Popen] = []

        def start_app():
            # One instance at a time: a copy left by a failed step would make the
            # next launch exit ("finishing an update") and fail every later step.
            for process in launched:
                if process.poll() is None:
                    self.driver.process = process
                    self.driver.kill()
                    process.wait(timeout=30)
            self.driver.launch(self.app, env, log)
            launched.append(self.driver.process)

        def launch():
            start_app()
            self.wait_ready()
            details = {"dismissed": self.dismiss_first_run()}
            if hasattr(self.driver, "translated"):
                details["rosetta"] = self.driver.translated()
                if MacDriver.arch == "x86_64" and details["rosetta"] is not True:
                    raise JourneyError("The app is not running under Rosetta")
            return details

        def interrupt():
            label = self.submit(self.server.url("/slow/page"))
            wait_for(
                lambda: (
                    sum(
                        count
                        for route, count in self.server.state.snapshot()[
                            "requests"
                        ].items()
                        if route.startswith("/slow/hls/") and route.endswith(".ts")
                    )
                    >= 3
                ),
                90,
                "the slow download to start transferring",
            )
            time.sleep(2)
            self.driver.kill()
            self.driver.process.wait(timeout=30)
            held["partial"] = [str(p) for p in self.downloads.rglob("*") if p.is_file()]
            return {"pressed": label, "files_in_flight": len(held["partial"])}

        def relaunch():
            start_app()
            self.wait_ready()
            self.dismiss_first_run()
            state = wait_for(
                lambda: next(
                    (
                        t
                        for t in self.driver.texts()
                        if t in {"Resume", "Retry", "Retry run", "Paused"}
                    ),
                    None,
                ),
                45,
                "the interrupted run to be offered for Resume/Retry",
            )
            return {"interrupted_state": state}

        def not_blocked():
            before = self.saved_media()
            label = self.submit(self.server.url("/page/normal"))
            media = self.wait_for_new_media(before, 180, "the new download to finish")
            return {"pressed": label, "media": self.probe(media)}

        def resume():
            before = self.saved_media()
            button = self.control(
                "AXButton", ("Resume", "Retry", "Retry run"), 20, "Resume"
            )
            self.driver.press(button)
            media = self.wait_for_new_media(
                before, 240, "the interrupted download to finish"
            )
            return {"media": self.probe(media)}

        def youtube(fmt: str):
            def action():
                before = self.saved_media()
                self.submit(self.youtube_url, format_label=fmt)
                media = self.wait_for_new_media(
                    before, 300, f"the YouTube {fmt} download"
                )
                info = self.probe(media)
                expected = "video" if fmt == "MP4" else "audio"
                if expected not in info["streams"]:
                    raise JourneyError(f"{media.name} has no {expected} stream")
                return {"media": info}

            return action

        def reopen():
            saved = len(self.saved_media())
            self.driver.close()
            code = self.driver.process.wait(timeout=60)
            staging = [str(p) for p in self.downloads.rglob(".vfstage") if p.exists()]
            start_app()
            self.wait_ready()
            self.dismiss_first_run()
            time.sleep(3)
            stale = [
                t
                for t in self.driver.texts()
                if t in {"Resume", "Retry run"} or t.endswith(", Paused")
            ]
            library = self.control("AXButton", ("Library",), 20, "Library")
            self.driver.press(library)
            time.sleep(2)
            if code != 0:
                raise JourneyError(f"Normal quit exited with code {code}")
            if staging:
                raise JourneyError(
                    f"Staging left in Downloads after a normal quit: {staging}"
                )
            if stale:
                raise JourneyError(
                    f"A finished run is still offered as Paused/Resume: {stale}"
                )
            return {"exit_code": code, "saved_media": saved}

        try:
            for name, action in (
                ("launch", launch),
                ("interrupt", interrupt),
                ("relaunch", relaunch),
                ("not_blocked", not_blocked),
                ("resume", resume),
                ("youtube_mp4", youtube("MP4")),
                ("youtube_mp3", youtube("MP3")),
                ("reopen", reopen),
            ):
                self.step(name, action)
        finally:
            try:
                if (
                    self.driver.process is not None
                    and self.driver.process.poll() is None
                ):
                    self.driver.close()
                    self.driver.process.wait(timeout=60)
            except Exception as exc:  # noqa: BLE001 - every launch is stopped below
                print(f"Normal close failed ({exc}); stopping the app", flush=True)
            for process in launched:
                if process.poll() is None:
                    self.driver.process = process
                    self.driver.kill()
            self.server.stop()
        result = {
            "passed": all(s["passed"] for s in self.steps),
            "machine": {
                "platform": sys.platform,
                "arch": platform.machine(),
                "os": platform.platform(),
            },
            "app": str(self.app),
            "app_arch": MacDriver.arch or "native",
            "steps": self.steps,
            "saved_media": [self.probe(p) for p in self.saved_media()],
            "fixtures": {
                k: v for k, v in fixtures.items() if isinstance(v, (str, int, float))
            },
        }
        (self.output / "journey-result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result


def main(argv: list[str] | None = None) -> int:
    # Control labels contain symbols like "▾"; Windows consoles default to cp1252.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--app",
        type=Path,
        required=True,
        help="VODForge.app (macOS) or the VODForge folder (Windows)",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--youtube-url", default=DEFAULT_YOUTUBE_URL)
    parser.add_argument(
        "--source",
        type=Path,
        help="Development only: run main.py from this checkout (macOS)",
    )
    parser.add_argument(
        "--arch",
        choices=["arm64", "x86_64"],
        help="macOS: run a universal app as this architecture (x86_64 uses Rosetta)",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Launch, list every control's type and name to controls.json, then quit",
    )
    args = parser.parse_args(argv)
    if args.source is not None:
        MacDriver.source = args.source.resolve()
    if args.arch is not None:
        MacDriver.arch = args.arch
    if args.inspect:
        journey = Journey(args.app, args.output, args.youtube_url)
        journey.output.mkdir(parents=True, exist_ok=True)
        journey.driver.launch(
            journey.app, journey.environment(), journey.output / "app.log"
        )
        try:
            wait_for(journey.driver.window, 90, "the VODForge window")
            time.sleep(8)
            rows = journey.driver.describe()
        finally:
            journey.driver.kill()
        (journey.output / "controls.json").write_text(
            json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        print(f"{len(rows)} controls: {journey.output / 'controls.json'}")
        return 0
    result = Journey(args.app, args.output, args.youtube_url).run()
    print(
        ("PASSED" if result["passed"] else "FAILED")
        + f": {args.output / 'journey-result.json'}"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
