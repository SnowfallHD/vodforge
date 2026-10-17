import json
import plistlib

import pytest

from scripts.sign_universal_macos import sign


@pytest.mark.parametrize(
    "unexpected,notary,accepted",
    [(False, "Accepted", True), (True, "Accepted", False), (False, "Invalid", False)],
)
def test_universal_signing_never_broadens_permissions(
    tmp_path, monkeypatch, unexpected, notary, accepted
):
    monkeypatch.setattr(
        "scripts.sign_universal_macos.audit_payload", lambda *_: {"qualified": True}
    )
    calls = []

    def run(args):
        calls.append(args)
        if "--display" in args:
            return plistlib.dumps(
                {"com.apple.security.cs.allow-unsigned-executable-memory": True}
                if unexpected
                else {}
            ).decode()
        if "notarytool" in args:
            return json.dumps({"status": notary, "id": "fixture"})
        return ""

    output = tmp_path / "signing"
    if accepted:
        receipt = sign(
            tmp_path / "VODForge.app",
            output,
            identity="existing",
            profile="existing",
            run=run,
        )
        assert receipt["entitlements"] == {"arm64": {}, "x86_64": {}}
        assert any("stapler" in row and "validate" in row for row in calls)
    else:
        with pytest.raises(ValueError):
            sign(
                tmp_path / "VODForge.app",
                output,
                identity="existing",
                profile="existing",
                run=run,
            )
        assert not any("stapler" in row for row in calls)
    assert plistlib.loads((output / "empty-entitlements.plist").read_bytes()) == {}
    signing = [row for row in calls if "--sign" in row]
    assert len(signing) == 1 and "--options" in signing[0]
    if unexpected:
        assert not any("notarytool" in row for row in calls)


def test_signing_preserves_existing_evidence_and_refuses_bad_closure(
    tmp_path, monkeypatch
):
    output = tmp_path / "retained"
    output.mkdir()
    with pytest.raises(ValueError, match="existing"):
        sign(
            tmp_path,
            output,
            identity="x",
            profile="x",
            run=lambda _: pytest.fail("no command"),
        )
    monkeypatch.setattr(
        "scripts.sign_universal_macos.audit_payload", lambda *_: {"qualified": False}
    )
    with pytest.raises(ValueError, match="closure"):
        sign(
            tmp_path,
            tmp_path / "new",
            identity="x",
            profile="x",
            run=lambda _: pytest.fail("no signing"),
        )
    assert not (tmp_path / "new").exists()
