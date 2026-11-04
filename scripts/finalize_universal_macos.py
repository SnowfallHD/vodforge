"""Turn the unsigned universal review app into the signed Mac release files.

Called by `finalize_macos_release.sh` on the signing Mac. In order:

1. Developer ID sign, notarize and staple VODForge.app (empty entitlements on
   both architectures), then run the packaged smoke test natively and under
   Rosetta.
2. Archive it as `VODForge-macOS-universal2-v<version>.zip` (in-app updates from
   0.2.6 on) and copy that archive, byte for byte, to the legacy
   `VODForge-macOS-arm64-...zip` and `-x64-...zip` names that 0.2.5 and earlier
   updaters ask for.
3. Build the single-icon "Install VODForge" app around the signed app, then
   sign, notarize and staple it. The nested app is not re-signed.
4. Build the branded DMG around the installer, then sign, notarize and staple
   the DMG and check Gatekeeper accepts it.

Every step refuses to overwrite an existing output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from scripts.build_macos_dmg import build_dmg, require_installer_app
from scripts.build_macos_installer import build_installer
from scripts.sign_universal_macos import sign as sign_app

IDENTITY = "Developer ID Application: Kryden Ventures, LLC (76G5W4954G)"
PROFILE = "kryden"
LEGACY_ARCHITECTURES = ("arm64", "x64")


def release_names(version: str) -> dict[str, str]:
    names = {
        "dmg": f"VODForge-macOS-universal2-v{version}.dmg",
        "universal_zip": f"VODForge-macOS-universal2-v{version}.zip",
    }
    for arch in LEGACY_ARCHITECTURES:
        names[f"legacy_{arch}_zip"] = f"VODForge-macOS-{arch}-v{version}.zip"
    return names


def _run(args) -> str:
    return subprocess.check_output(args, text=True)


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def notarize(path: Path, receipt: Path, *, profile: str, run=None) -> dict:
    """Submit to Apple, wait, and keep the result. Refuses anything but Accepted."""
    run = run or _run
    result = json.loads(
        run(
            [
                "/usr/bin/xcrun",
                "notarytool",
                "submit",
                str(path),
                "--keychain-profile",
                profile,
                "--wait",
                "--output-format",
                "json",
            ]
        )
    )
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    if result.get("status") != "Accepted":
        raise ValueError(
            f"Apple notarization not accepted for {path.name}; see {receipt}"
        )
    return result


def sign_installer(
    installer: Path, work: Path, *, identity: str, profile: str, run=None
) -> dict:
    run = run or _run
    # No --deep: the nested VODForge.app is already signed, notarized and
    # stapled, and re-signing it would invalidate its ticket. The installer's
    # own signature seals it as a resource.
    run(
        [
            "/usr/bin/codesign",
            "--force",
            "--options",
            "runtime",
            "--timestamp",
            "--sign",
            identity,
            str(installer),
        ]
    )
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(installer)])
    archive = work / "Install-VODForge-notary.zip"
    run(
        [
            "/usr/bin/ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(installer),
            str(archive),
        ]
    )
    result = notarize(
        archive, work / "installer-notary-result.json", profile=profile, run=run
    )
    archive.unlink()
    run(["/usr/bin/xcrun", "stapler", "staple", str(installer)])
    run(
        [
            "/usr/sbin/spctl",
            "--assess",
            "--type",
            "execute",
            "--verbose=2",
            str(installer),
        ]
    )
    audit = require_installer_app(installer, run)
    return {"notary": result, "audit_layout": audit["layout"]}


def sign_dmg(dmg: Path, work: Path, *, identity: str, profile: str, run=None) -> dict:
    run = run or _run
    run(["/usr/bin/codesign", "--force", "--timestamp", "--sign", identity, str(dmg)])
    run(["/usr/bin/codesign", "--verify", "--strict", str(dmg)])
    result = notarize(dmg, work / "dmg-notary-result.json", profile=profile, run=run)
    run(["/usr/bin/xcrun", "stapler", "staple", str(dmg)])
    run(["/usr/bin/xcrun", "stapler", "validate", str(dmg)])
    run(["/usr/bin/hdiutil", "verify", str(dmg)])
    run(
        [
            "/usr/sbin/spctl",
            "--assess",
            "--type",
            "open",
            "--context",
            "context:primary-signature",
            "--verbose=2",
            str(dmg),
        ]
    )
    return {"notary": result}


def smoke_test(app: Path, run=None) -> None:
    run = run or _run
    executable = app / "Contents/MacOS/VODForge"
    run([str(executable), "--runtime-smoke"])
    run(["/usr/bin/arch", "-x86_64", str(executable), "--runtime-smoke"])


def write_update_archives(
    app: Path, output: Path, version: str, run=None
) -> dict[str, str]:
    run = run or _run
    names = release_names(version)
    universal = output / names["universal_zip"]
    run(
        [
            "/usr/bin/ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(app),
            str(universal),
        ]
    )
    digest = _sha256(universal)
    for arch in LEGACY_ARCHITECTURES:
        legacy = output / names[f"legacy_{arch}_zip"]
        shutil.copyfile(universal, legacy)
        if _sha256(legacy) != digest:
            raise ValueError(
                f"Legacy archive {legacy.name} does not match the universal archive"
            )
    return {
        names["universal_zip"]: digest,
        **{names[f"legacy_{arch}_zip"]: digest for arch in LEGACY_ARCHITECTURES},
    }


def finalize(
    unsigned_zip: Path,
    output: Path,
    version: str,
    *,
    identity: str = IDENTITY,
    profile: str = PROFILE,
    logo: Path = Path("assets/brand/vf-mark.png"),
) -> dict:
    if output.exists():
        raise ValueError(f"Refusing existing output: {output}")
    work = output / "work"
    work.mkdir(parents=True)
    extracted = work / "app"
    extracted.mkdir()
    _run(["/usr/bin/ditto", "-x", "-k", str(unsigned_zip), str(extracted)])
    app = extracted / "VODForge.app"
    if not app.is_dir():
        raise ValueError(f"VODForge.app was not found in {unsigned_zip.name}")

    signing = sign_app(app, work / "app-signing", identity=identity, profile=profile)
    smoke_test(app)
    archives = write_update_archives(app, output, version)

    installer = work / "installer" / "Install VODForge.app"
    build_installer(app, installer)
    installer_receipt = sign_installer(
        installer, work, identity=identity, profile=profile
    )

    dmg = output / release_names(version)["dmg"]
    build_dmg(installer, dmg, logo.resolve())
    dmg_receipt = sign_dmg(dmg, work, identity=identity, profile=profile)

    receipt = {
        "version": version,
        "unsigned_input": {"name": unsigned_zip.name, "sha256": _sha256(unsigned_zip)},
        "app_notary": signing["notary"],
        "installer_notary": installer_receipt["notary"],
        "dmg_notary": dmg_receipt["notary"],
        "files": {dmg.name: _sha256(dmg), **archives},
    }
    (output / "macos-release-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--unsigned-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--identity", default=IDENTITY)
    parser.add_argument("--profile", default=PROFILE)
    args = parser.parse_args(argv)
    receipt = finalize(
        args.unsigned_zip.resolve(),
        args.output.absolute(),
        args.version,
        identity=args.identity,
        profile=args.profile,
    )
    for name, digest in receipt["files"].items():
        print(f"{digest}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
