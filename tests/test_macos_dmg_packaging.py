import plistlib

import pytest

from scripts.build_macos_dmg import build_dmg, require_universal_app


@pytest.fixture
def app(tmp_path):
    path = tmp_path / "VODForge.app"
    (path / "Contents/MacOS").mkdir(parents=True)
    (path / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "com.snowfallhd.vodforge",
                "CFBundleShortVersionString": "0.2.6",
            }
        )
    )
    (path / "Contents/MacOS/VODForge").write_bytes(
        bytes.fromhex("cafebabe") + b"fixture-not-an-executable"
    )
    return path


@pytest.mark.parametrize("slices", ["arm64", "x86_64", "arm64 x86_64"])
def test_dmg_rejects_incomplete_architectures_before_signing_or_staging(app, slices):
    calls = []

    def run(args):
        calls.append(args)
        return slices if "lipo" in args[0] else "verified"

    if len(slices.split()) == 1:
        with pytest.raises(ValueError, match="slices missing"):
            require_universal_app(app, run)
        assert not any("codesign" in row[0] or "stapler" in row for row in calls)
    else:
        assert len(require_universal_app(app, run)["native_files"]) == 1
        assert any("codesign" in row[0] for row in calls)
        assert any("stapler" in row for row in calls)


def test_dmg_checks_nested_extension_not_just_entrypoint(app):
    extension = app / "Contents/MacOS/thin.so"
    extension.write_bytes(bytes.fromhex("feedfacf"))
    with pytest.raises(ValueError, match="thin.so"):
        require_universal_app(
            app,
            lambda args: "arm64" if args[-1].endswith("thin.so") else "arm64 x86_64",
        )


def test_dmg_refuses_existing_output_before_any_bundle_work(app, tmp_path):
    output = tmp_path / "retained.dmg"
    output.write_bytes(b"preserved")
    with pytest.raises(ValueError, match="refusing overwrite"):
        build_dmg(app, output, tmp_path / "unused.png")
    assert output.read_bytes() == b"preserved"


def test_dmg_rejects_symlinked_entrypoint(app, tmp_path):
    executable = app / "Contents/MacOS/VODForge"
    outside = tmp_path / "foreign"
    outside.write_bytes(executable.read_bytes())
    executable.unlink()
    executable.symlink_to(outside)
    with pytest.raises(ValueError, match="Missing app executable"):
        require_universal_app(app, lambda _: pytest.fail("must refuse before commands"))


def test_dmg_accepts_only_the_installer_app(app, tmp_path):
    # A plain VODForge.app (the old drag-to-Applications layout) is refused.
    with pytest.raises(ValueError, match="Install VODForge.app"):
        build_dmg(app, tmp_path / "new.dmg", tmp_path / "unused.png")
    assert not (tmp_path / "new.dmg").exists()
