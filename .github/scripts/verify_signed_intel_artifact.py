"""Verify an existing signed candidate; never build, sign, install or publish it."""
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

SOURCE = "6282b1f42b7ab9ac3580327bac27191e8da8e0ec"
ARCHIVE = "c62d5a0bc7a19eaf0d29ad7724d20896ecca1bfa6e70b4c2ea873b6bbce00560"
EXECUTABLE = "a7cf86ab6c03668a87628508caa9679955159b8d65eed8d315262b61ba58d7cd"
archive, evidence = map(Path, sys.argv[1:])
evidence.mkdir(exist_ok=True)
receipt = {"candidate_source": SOURCE, "verifier_commit": os.environ.get("GITHUB_SHA"),
           "run_id": os.environ.get("GITHUB_RUN_ID"), "architecture": platform.machine(),
           "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
           "build_performed": False, "publication": False, "status": "running"}

def command(label, args, env=None, timeout=90):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, timeout=timeout, check=False)
    (evidence / (label + ".log")).write_bytes(result.stdout)
    receipt[label + "_exit"] = result.returncode
    if result.returncode:
        raise RuntimeError(label + " failed with exit " + str(result.returncode))
    return result.stdout.decode(errors="replace")

try:
    assert platform.machine() == "x86_64", "Intel runner required"
    assert receipt["archive_sha256"] == ARCHIVE, "Archive identity mismatch"
    staging = Path(os.environ["RUNNER_TEMP"]) / "signed628-extracted"
    staging.mkdir()
    command("extract", ["/usr/bin/ditto", "-x", "-k", str(archive), str(staging)])
    app = staging / "VODForge.app"
    exe = app / "Contents/MacOS/VODForge"
    receipt["executable_sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
    assert receipt["executable_sha256"] == EXECUTABLE, "Executable identity mismatch"
    resources = app / "Contents/Resources"
    assert (resources / "VODFORGE_BUILD_REVISION").read_text().strip() == SOURCE
    assert (resources / "VODFORGE_VERSION").read_text().strip() == "0.2.3"
    assert (resources / "VODFORGE_TELEMETRY_POLICY").read_text().strip() == "production"
    command("codesign_verify", ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    details = command("codesign_details", ["/usr/bin/codesign", "-dv", "--verbose=4", str(app)])
    assert "TeamIdentifier=76G5W4954G" in details
    assert "Authority=Developer ID Application: Kryden Ventures, LLC (76G5W4954G)" in details
    command("staple_validate", ["/usr/bin/xcrun", "stapler", "validate", str(app)])
    assessment = command("gatekeeper", ["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=2", str(app)])
    assert "source=Notarized Developer ID" in assessment
    home = staging / "isolated-home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), VODFORGE_DISABLE_TELEMETRY="1",
               XDG_DATA_HOME=str(home / ".local/share"))
    output = command("signed_runtime_smoke", [str(exe), "--runtime-smoke"], env, 120)
    assert "VODFORGE_RUNTIME_SMOKE_OK" in output, "Maintained smoke marker missing"
    receipt["status"] = "passed"
except BaseException as error:
    receipt["status"] = "failed"
    receipt["error"] = str(error)
    raise
finally:
    receipt["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (evidence / "verification-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
