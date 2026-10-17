"""Private universal signing with no entitlements on either architecture."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
from pathlib import Path

from scripts.macos_native_closure import audit_payload


def sign(app: Path, output: Path, *, identity: str, profile: str, run=None):
    if output.exists():
        raise ValueError("Refusing existing signing output")
    if run is None:
        run = lambda args: subprocess.check_output(args, text=True)
    closure = audit_payload(app, run)
    if not closure["qualified"]:
        raise ValueError("Universal dependency closure failed")
    output.mkdir(parents=True)
    empty = output / "empty-entitlements.plist"
    empty.write_bytes(plistlib.dumps({}))
    # Explicitly empty, including on Intel. Do not run the historical script
    # which applies Intel's compatibility entitlement to the entire fat binary.
    run(
        [
            "/usr/bin/codesign",
            "--force",
            "--deep",
            "--strict",
            "--options",
            "runtime",
            "--timestamp",
            "--entitlements",
            str(empty),
            "--sign",
            identity,
            str(app),
        ]
    )
    entitlements = {}
    for arch in ["arm64", "x86_64"]:
        text = run(
            [
                "/usr/bin/codesign",
                "--display",
                "--arch",
                arch,
                "--entitlements",
                ":-",
                str(app),
            ]
        )
        value = plistlib.loads(text.encode()) if text.strip() else {}
        if value:
            raise ValueError("Unexpected universal executable entitlement")
        entitlements[arch] = value
    run(
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--all-architectures",
            str(app),
        ]
    )
    archive = output / "VODForge-notary.zip"
    run(
        [
            "/usr/bin/ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(app),
            str(archive),
        ]
    )
    result = json.loads(
        run(
            [
                "/usr/bin/xcrun",
                "notarytool",
                "submit",
                str(archive),
                "--keychain-profile",
                profile,
                "--wait",
                "--output-format",
                "json",
            ]
        )
    )
    (output / "notary-result.json").write_text(json.dumps(result, indent=2) + "\n")
    if result.get("status") != "Accepted":
        raise ValueError("Apple notarization not accepted; result preserved")
    run(["/usr/bin/xcrun", "stapler", "staple", str(app)])
    run(["/usr/bin/xcrun", "stapler", "validate", str(app)])
    run(
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--all-architectures",
            str(app),
        ]
    )
    run(["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=2", str(app)])
    receipt = {
        "app": str(app),
        "identity": identity,
        "entitlements": entitlements,
        "notary": result,
        "scope": "Private Developer ID/notarized candidate with empty entitlements; native/Intel runtime compatibility not established",
    }
    (output / "signing-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--identity",
        default="Developer ID Application: Kryden Ventures, LLC (76G5W4954G)",
    )
    parser.add_argument("--profile", default="kryden")
    args = parser.parse_args()
    sign(
        args.app.resolve(),
        args.output.absolute(),
        identity=args.identity,
        profile=args.profile,
    )
