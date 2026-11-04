"""The signing step that turns the universal review app into the Mac release files."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import scripts.finalize_universal_macos as finalize_module
from scripts.finalize_universal_macos import (
    finalize,
    notarize,
    release_names,
    sign_dmg,
    sign_installer,
)


def _accepted(args):
    if args[:3] == ["/usr/bin/xcrun", "notarytool", "submit"]:
        return json.dumps({"status": "Accepted", "id": "fixture"})
    return ""


def test_release_names_cover_the_dmg_and_every_updater_generation():
    assert release_names("0.2.6") == {
        "dmg": "VODForge-macOS-universal2-v0.2.6.dmg",
        "universal_zip": "VODForge-macOS-universal2-v0.2.6.zip",
        "legacy_arm64_zip": "VODForge-macOS-arm64-v0.2.6.zip",
        "legacy_x64_zip": "VODForge-macOS-x64-v0.2.6.zip",
    }


def test_notarization_that_is_not_accepted_stops_and_keeps_the_result(tmp_path):
    receipt = tmp_path / "result.json"
    with pytest.raises(ValueError, match="not accepted"):
        notarize(
            tmp_path / "x.dmg",
            receipt,
            profile="kryden",
            run=lambda args: json.dumps({"status": "Invalid"}),
        )
    assert json.loads(receipt.read_text())["status"] == "Invalid"


def test_installer_is_signed_without_resigning_the_notarized_app_inside(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        finalize_module,
        "require_installer_app",
        lambda app, run: {"layout": "single installer icon"},
    )
    installer = tmp_path / "Install VODForge.app"
    installer.mkdir()

    def run(args):
        calls.append(args)
        if args[0] == "/usr/bin/ditto":
            Path(args[-1]).write_bytes(b"zip")
        return _accepted(args)

    sign_installer(
        installer, tmp_path, identity="Developer ID", profile="kryden", run=run
    )

    sign = next(c for c in calls if c[:2] == ["/usr/bin/codesign", "--force"])
    assert "--deep" not in sign
    assert "--options" in sign and "runtime" in sign and "--timestamp" in sign
    order = [c[1] if c[0].endswith("xcrun") else c[0] for c in calls]
    assert (
        order.index("notarytool")
        < order.index("stapler")
        < order.index("/usr/sbin/spctl")
    )


def test_dmg_is_signed_notarized_stapled_and_accepted_for_opening(tmp_path):
    calls = []
    sign_dmg(
        tmp_path / "v.dmg",
        tmp_path,
        identity="Developer ID",
        profile="kryden",
        run=lambda args: calls.append(args) or _accepted(args),
    )
    flat = [" ".join(c) for c in calls]
    assert flat[0].startswith(
        "/usr/bin/codesign --force --timestamp --sign Developer ID"
    )
    assert any("stapler staple" in c for c in flat)
    assert any("stapler validate" in c for c in flat)
    assert any(
        "spctl --assess --type open --context context:primary-signature" in c
        for c in flat
    )


def test_finalize_builds_every_file_in_order_and_legacy_names_match(
    tmp_path, monkeypatch
):
    unsigned = tmp_path / "review.zip"
    with zipfile.ZipFile(unsigned, "w") as archive:
        archive.writestr("VODForge.app/Contents/MacOS/VODForge", b"app")
    events = []

    def run(args):
        events.append(("run", Path(args[0]).name, *args[1:2]))
        if args[0] == "/usr/bin/ditto" and args[1] == "-x":
            with zipfile.ZipFile(args[3]) as archive:
                archive.extractall(args[4])
        elif args[0] == "/usr/bin/ditto":
            Path(args[-1]).write_bytes(b"signed universal app archive")
        return ""

    def fake_sign(app, output, *, identity, profile):
        events.append(("sign app",))
        return {"notary": {"status": "Accepted", "id": "app"}}

    def fake_installer(app, output):
        events.append(("build installer",))
        output.mkdir(parents=True)

    def fake_installer_sign(installer, work, *, identity, profile):
        events.append(("sign installer",))
        return {"notary": {"status": "Accepted", "id": "installer"}}

    def fake_dmg(installer, output, logo):
        events.append(("build dmg",))
        output.write_bytes(b"dmg")

    def fake_dmg_sign(dmg, work, *, identity, profile):
        events.append(("sign dmg",))
        return {"notary": {"status": "Accepted", "id": "dmg"}}

    monkeypatch.setattr(finalize_module, "_run", run)
    monkeypatch.setattr(finalize_module, "sign_app", fake_sign)
    monkeypatch.setattr(finalize_module, "build_installer", fake_installer)
    monkeypatch.setattr(finalize_module, "sign_installer", fake_installer_sign)
    monkeypatch.setattr(finalize_module, "build_dmg", fake_dmg)
    monkeypatch.setattr(finalize_module, "sign_dmg", fake_dmg_sign)
    monkeypatch.setattr(
        finalize_module,
        "smoke_test",
        lambda app, run=None: events.append(("smoke both architectures",)),
    )

    output = tmp_path / "out"
    receipt = finalize(unsigned, output, "0.2.6")

    steps = [e[0] for e in events if e[0] != "run"]
    assert steps == [
        "sign app",
        "smoke both architectures",
        "build installer",
        "sign installer",
        "build dmg",
        "sign dmg",
    ]
    names = release_names("0.2.6")
    universal = (output / names["universal_zip"]).read_bytes()
    assert (output / names["legacy_arm64_zip"]).read_bytes() == universal
    assert (output / names["legacy_x64_zip"]).read_bytes() == universal
    assert set(receipt["files"]) == set(names.values())
    assert (
        json.loads((output / "macos-release-receipt.json").read_text())["dmg_notary"][
            "id"
        ]
        == "dmg"
    )


def test_finalize_refuses_an_existing_output(tmp_path):
    (tmp_path / "out").mkdir()
    with pytest.raises(ValueError, match="Refusing existing output"):
        finalize(tmp_path / "review.zip", tmp_path / "out", "0.2.6")
