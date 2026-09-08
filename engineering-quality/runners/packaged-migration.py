"""Exercise real packaged startup over isolated v0.1.8-format profiles.

This is an on-disk upgrade-contract test, not a test of the updater download UI.
All networking uses the build-bound preview service; no production profile is read.
"""

import argparse
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path


def write(path, value):
    path.write_text(json.dumps(value, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("key", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    key = args.key.read_text().strip()
    assert len(key) == 64
    cases = [
        ("default", "", "none"),
        ("opt-in", "DE", "allow"),
        ("unknown", "XX", "deny"),
    ]
    results = []
    try:
        for name, country, choice in cases:
            profile = args.output / name
            profile.mkdir()
            install_id = str(uuid.uuid4())
            # Exact v0.1.8 schema: no onboarding/consent markers. Deliberately
            # unconfirmed launch catches accidental browser activation on upgrade.
            write(
                profile / "installation.json",
                {
                    "schema_version": 1,
                    "install_id": install_id,
                    "first_launch_confirmed": False,
                    "cloud_seen_confirmed": False,
                    "heycatch_first_launch_confirmed": False,
                    "attribution_claim_opened": False,
                    "attribution_claim_confirmed": False,
                    "attribution_claim_token": None,
                    "product_telemetry_allowed": False,
                },
            )
            write(
                profile / "settings.json",
                {
                    "schema_version": 1,
                    "values": {
                        "anonymous_usage_analytics": True,
                        "appearance_theme": "Violet",
                        "whats_new_seen": "library-and-local-video",
                    },
                },
            )
            write(
                profile / "before.json",
                {
                    "installation": json.loads(
                        (profile / "installation.json").read_text()
                    ),
                    "settings": json.loads((profile / "settings.json").read_text()),
                },
            )
            env = dict(os.environ)
            env.pop("VODFORGE_DISABLE_TELEMETRY", None)
            env.update(
                VODFORGE_QA_ACCESS_KEY=key,
                VODFORGE_QA_PROFILE=str(profile.resolve()),
                VODFORGE_QA_COUNTRY=country,
            )
            for launch in range(2):
                # Flip the injected country on relaunch: persisted policy must win.
                if launch:
                    env["VODFORGE_QA_COUNTRY"] = "DE" if not country else "US"
                log = profile / f"launch-{launch}.log"
                with log.open("w") as stream:
                    process = subprocess.Popen(
                        [
                            str(args.exe.resolve()),
                            "--analytics-qa",
                            choice if not launch else "none",
                            "3",
                            "8",
                        ],
                        env=env,
                        stdout=stream,
                        stderr=stream,
                    )
                    try:
                        code = process.wait(timeout=90)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                        raise AssertionError("Owned candidate did not finish")
                assert code == 0, log.read_text()[-2000:]
                journey = json.loads((profile / "startup-journey.json").read_text())
                state = json.loads((profile / "installation.json").read_text())
                settings = json.loads((profile / "settings.json").read_text())["values"]
                snapshot = {
                    "journey": journey,
                    "installation": state,
                    "settings": settings,
                }
                write(profile / f"after-{launch}.json", snapshot)
                events = journey["events"]
                assert not any(e["kind"] == "browser_requested" for e in events)
                prompts = [
                    e for e in events if e["kind"] == "permission_prompt_visible"
                ]
                assert len(prompts) == int(not launch and bool(country)), (
                    name,
                    prompts,
                )
                assert state["install_id"] == install_id
                assert state["attribution_claim_token"] is None
                onboarding = state["onboarding"]
                assert (
                    onboarding["region_checked"]
                    and onboarding["region_policy_version"] == 1
                )
                assert (
                    not onboarding["browser_eligible"]
                    and onboarding["welcome_attempted"]
                )
                expected = {
                    "default": "default-on",
                    "opt-in": "opt-in",
                    "unknown": "unknown",
                }[name]
                assert onboarding["mode"] == expected, (name, onboarding)
                assert "anonymous_usage_analytics" not in settings
                consent = settings.get("analytics_consent", {})
                assert not set(consent) & {
                    "mode",
                    "region_checked",
                    "prompted",
                    "welcome_attempted",
                }
                assert (
                    consent.get("choice")
                    == {"default": None, "opt-in": "granted", "unknown": "denied"}[name]
                )
                results.append(
                    {"case": name, "launch": launch, "pid": process.pid, "passed": True}
                )
    finally:
        write(
            args.output / "results.json",
            {
                "cases": results,
                "expected": 6,
                "passed": len(results) == 6,
                "executable_sha256": hashlib.sha256(args.exe.read_bytes()).hexdigest(),
                "scope": "packaged startup over v0.1.8 schema fixtures; not updater UI",
            },
        )


if __name__ == "__main__":
    main()
