"""Exercise the maintained build's real plist finalization without packaging."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Native PlistBuddy metadata writer"
)
@pytest.mark.parametrize(
    ("existing", "configured", "expected"),
    [
        (None, None, "15.0"),
        ("26.0", None, "15.0"),
        ("14.0", None, "15.0"),
        (None, "16.0", "16.0"),
        ("15.0", "16.0", "16.0"),
    ],
)
def test_build_finalizes_the_configured_macos_minimum(
    tmp_path, existing, configured, expected
):
    script = (Path(__file__).resolve().parents[1] / "build_macos.sh").read_text()
    block = script[script.index('app_plist="$app_bundle/Contents/Info.plist"') :]
    block = block[: block.index("bundle_icon_name=")]
    app = tmp_path / "Fixture.app"
    plist = app / "Contents/Info.plist"
    plist.parent.mkdir(parents=True)
    initial = {
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "FixturePreserved": "unchanged",
    }
    if existing is not None:
        initial["LSMinimumSystemVersion"] = existing
    plist.write_bytes(plistlib.dumps(initial))
    env = os.environ.copy()
    env.pop("VODFORGE_MACOS_MIN_VERSION", None)
    env.update(app_bundle=str(app), build_version="0.2.6-dev.fixture")
    if configured is not None:
        env["VODFORGE_MACOS_MIN_VERSION"] = configured
    subprocess.run(
        ["/bin/bash", "-eu", "-c", block],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    actual = plistlib.loads(plist.read_bytes())
    assert actual["LSMinimumSystemVersion"] == expected
    assert actual["CFBundleVersion"] == "0.2.6"
    assert actual["FixturePreserved"] == "unchanged"
