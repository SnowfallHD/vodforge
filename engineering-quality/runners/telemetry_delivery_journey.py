"""One signed-build install with analytics on, to prove production delivery.

Unlike release_journey.py this run leaves telemetry enabled: it sends real
events to production D1 and PostHog. Use it once per release candidate, with
an isolated profile, and add the printed installation ID to the website's QA
exclusions afterwards (it is not a real user).

Journey: launch, accept "Share analytics" if asked, dismiss other prompts,
visit Library/Watch/Activity, download one YouTube video as MP4, normal quit,
relaunch, normal quit. The result records the installation ID, every event the
app queued and which of them the first-party server and PostHog acknowledged.

    python engineering-quality/runners/telemetry_delivery_journey.py \
        --app /Applications/VODForge.app --output delivery-result
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_journey as rj


class DeliveryJourney(rj.Journey):
    def environment(self) -> dict[str, str]:
        env = super().environment()
        env.pop("VODFORGE_DISABLE_TELEMETRY", None)
        for name in list(env):
            # Any QA marker switches production transport off by design.
            if name.startswith(("VODFORGE_QA", "VODFORGE_POSTHOG_QA")):
                env.pop(name)
        return env

    def profile(self) -> Path | None:
        found = next(self.home.rglob("installation.json"), None)
        return found.parent if found else None

    def sample_outbox(self, stop: threading.Event, seen: dict[str, dict]) -> None:
        """Record every queued event and when it leaves the outbox."""
        while not stop.is_set():
            profile = self.profile()
            path = profile / "product-telemetry.json" if profile else None
            present: set[str] = set()
            try:
                if path is not None and path.is_file():
                    data = json.loads(path.read_text("utf-8"))
                    events = data.get("events", []) if isinstance(data, dict) else []
                    for event in events:
                        key = event.get("event_id")
                        if not key:
                            continue
                        present.add(key)
                        row = seen.setdefault(
                            key,
                            {
                                "event": event.get("event_name"),
                                "feature": event.get("feature"),
                                "action": event.get("action"),
                                "first_seen": time.time(),
                            },
                        )
                        row["posthog_queued"] = row.get("posthog_queued") or (
                            event.get("posthog_epoch") is not None
                        )
                        row["d1_delivered"] = bool(event.get("d1_delivered"))
                        row["posthog_attempted"] = bool(event.get("posthog_attempted"))
                        row["posthog_failures"] = event.get("posthog_failures", 0)
                        row.pop("left_outbox", None)
            except (OSError, ValueError):
                pass
            for key, row in seen.items():
                if key not in present and "left_outbox" not in row:
                    row["left_outbox"] = time.time()
            stop.wait(0.2)

    def run(self) -> dict[str, Any]:
        if self.output.exists() and any(self.output.iterdir()):
            raise rj.JourneyError(f"Refusing a non-empty output folder: {self.output}")
        self.output.mkdir(parents=True, exist_ok=True)
        env = self.environment()
        consent: dict[str, Any] = {}

        def start():
            self.driver.launch(self.app, env, self.output / "app.log")
            self.wait_ready()

        def accept_analytics(wait: float):
            button = None
            deadline = time.monotonic() + wait
            while button is None and time.monotonic() < deadline:
                button = self.driver.find("AXButton", ("Share analytics",))
                time.sleep(0.5)
            if button is not None:
                self.driver.press(button)
                time.sleep(1)
            return button is not None

        def launch():
            start()
            consent["prompted"] = accept_analytics(15)
            return {
                "consent_prompt": consent["prompted"],
                "dismissed": self.dismiss_first_run(),
            }

        def browse():
            for name in ("Library", "Watch", "Activity", "Forge"):
                self.driver.press(self.control("AXButton", (name,), 20, name))
                time.sleep(2)

        def download():
            before = self.saved_media()
            self.submit(self.youtube_url, format_label="MP4")
            media = self.wait_for_new_media(before, 300, "the YouTube MP4 download")
            panel = self.driver.find("AXButton", ("Close options",))
            if panel is not None:
                self.driver.press(panel)
            return {"media": self.probe(media)}

        def quit_and_reopen():
            time.sleep(20)  # Let the outbox deliver while the app is open.
            self.driver.close()
            first = self.driver.process.wait(timeout=60)
            start()
            accept_analytics(5)
            self.dismiss_first_run()
            time.sleep(25)
            self.driver.close()
            second = self.driver.process.wait(timeout=60)
            if first or second:
                raise rj.JourneyError(f"Quit exit codes {first}, {second}")
            return {"exit_codes": [first, second]}

        seen: dict[str, dict] = {}
        stop = threading.Event()
        sampler = threading.Thread(target=self.sample_outbox, args=(stop, seen))
        sampler.start()
        try:
            for name, action in (
                ("launch", launch),
                ("browse", browse),
                ("download", download),
                ("quit_and_reopen", quit_and_reopen),
            ):
                if not self.step(name, action):
                    break
        finally:
            if self.driver.process is not None and self.driver.process.poll() is None:
                try:
                    self.driver.close()
                    self.driver.process.wait(timeout=60)
                except Exception:  # noqa: BLE001 - stopped below
                    self.driver.kill()
            time.sleep(1)
            stop.set()
            sampler.join()
        profile = self.profile()
        installation = (
            json.loads((profile / "installation.json").read_text("utf-8"))
            if profile
            else {}
        )
        settings = (
            json.loads((profile / "settings.json").read_text("utf-8"))
            if profile and (profile / "settings.json").is_file()
            else {}
        )
        state_files = (
            sorted(
                str(p.relative_to(profile))
                for p in profile.rglob("*")
                if p.is_file() and "logs" not in p.parts
            )
            if profile
            else []
        )
        install_id = installation.get("install_id")
        remaining = []
        if profile and (profile / "product-telemetry.json").is_file():
            data = json.loads((profile / "product-telemetry.json").read_text("utf-8"))
            remaining = data.get("events", []) if isinstance(data, dict) else []
        diagnostics = []
        if profile:
            for log in (profile / "logs").glob("*.log"):
                diagnostics += [
                    line.strip()
                    for line in log.read_text("utf-8", errors="replace").splitlines()
                    if "analytics delivery" in line.lower()
                    or "telemetry event" in line.lower()
                ]
        result = {
            "passed": len(self.steps) == 4 and all(s["passed"] for s in self.steps),
            "machine": {"platform": sys.platform, "arch": rj.platform.machine()},
            "app": str(self.app),
            "steps": self.steps,
            "profile": str(profile) if profile else None,
            "installation_id": install_id,
            "posthog_distinct_id": (
                "vf_install_"
                + hashlib.sha256(
                    f"vodforge:posthog:installation:{install_id}".encode()
                ).hexdigest()
                if install_id
                else None
            ),
            "events_seen": seen,
            "events_left_in_outbox": len(remaining),
            "delivery_diagnostics": diagnostics,
            "analytics_choice": settings.get("values", {}).get("analytics_consent"),
            "profile_files": state_files,
            "telemetry_disabled_in_env": "VODFORGE_DISABLE_TELEMETRY" in env,
            "qa_markers": [k for k in env if k.startswith("VODFORGE_")],
        }
        (self.output / "delivery-result.json").write_text(
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
    args = parser.parse_args(argv)
    os.environ.pop("VODFORGE_DISABLE_TELEMETRY", None)
    result = DeliveryJourney(args.app, args.output, args.youtube_url).run()
    print(json.dumps({k: result[k] for k in ("passed", "installation_id")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
