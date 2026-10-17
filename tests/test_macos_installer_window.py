import plistlib
import sys
from pathlib import Path

import pytest

from scripts.macos_installer_window import (
    BACKGROUND,
    ENTRY,
    ICON_POSITION,
    decorate_volume,
    write_assets,
)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin FinderInfo metadata")
def test_installer_window_roundtrips_single_entry_and_complete_icon_view(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    DSStore = pytest.importorskip("ds_store", reason="Optional DMG tooling").DSStore
    Alias = pytest.importorskip("mac_alias", reason="Optional DMG tooling").Alias
    from PIL import Image

    # This unit case checks serialized view metadata, not HFS alias resolution.
    # Host APFS fixture inode numbers can exceed the Carbon alias format.
    monkeypatch.setattr(
        Alias, "for_file", lambda path: SimpleNamespace(to_bytes=lambda: b"unit-alias")
    )

    volume = tmp_path / "Install VODForge"
    volume.mkdir()
    (volume / ENTRY).mkdir()
    Image.new("RGB", (640, 440), "#302e34").save(volume / BACKGROUND)
    decorate_volume(volume)
    with DSStore.open(str(volume / ".DS_Store"), "r") as store:
        assert store["."]["icvl"] == (b"type", b"icnv")
        assert store[ENTRY]["Iloc"] == ICON_POSITION
        bounds = store["."]["bwsp"]
        assert bounds["WindowBounds"] == "{{120, 120}, {640, 440}}"
        assert not bounds["ShowToolbar"]
        assert not bounds["ShowPathbar"]
        assert not bounds["ShowTabView"]
        options = store["."]["icvp"]
        assert options["backgroundType"] == 2
        assert options["backgroundImageAlias"]
        assert all(
            options["backgroundColor" + channel] < 0.3
            for channel in ("Red", "Green", "Blue")
        )
        assert not options["showIconPreview"]
        assert options["scrollPositionX"] == options["scrollPositionY"] == 0
    assert sorted(p.name for p in volume.iterdir() if not p.name.startswith(".")) == [
        ENTRY
    ]


@pytest.mark.parametrize("extra", ["Applications", "Compatibility.txt", "VODForge.app"])
def test_old_drag_layout_is_refused_before_writing_finder_metadata(tmp_path, extra):
    (tmp_path / ENTRY).mkdir()
    (tmp_path / BACKGROUND).write_bytes(b"fixture")
    (tmp_path / extra).touch()
    with pytest.raises(ValueError, match="exactly"):
        decorate_volume(tmp_path)
    assert not (tmp_path / ".DS_Store").exists()


def test_installer_entry_must_not_be_a_symlink(tmp_path):
    target = tmp_path / ".target"
    target.mkdir()
    (tmp_path / ENTRY).symlink_to(target)
    with pytest.raises(ValueError, match="real"):
        decorate_volume(tmp_path)


@pytest.mark.skipif(sys.platform != "darwin", reason="Native tiffutil/Font artwork")
def test_retina_tiff_keeps_both_point_equivalent_representations(tmp_path):
    from PIL import Image

    output = tmp_path / "artwork"
    write_assets(output, Path("assets/brand/vf-mark.png"))
    with Image.open(output / BACKGROUND) as image:
        frames = []
        for index in range(image.n_frames):
            image.seek(index)
            frames.append((image.size, tuple(round(n) for n in image.info["dpi"])))
        assert frames == [((640, 440), (72, 72)), ((1280, 880), (144, 144))]
    with pytest.raises(ValueError, match="overwrite"):
        write_assets(output, Path("assets/brand/vf-mark.png"))


def test_ordinary_app_cannot_be_renamed_to_become_an_installer(tmp_path):
    from scripts.build_macos_dmg import require_installer_app

    app = tmp_path / ENTRY
    (app / "Contents").mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": "com.snowfallhd.vodforge"})
    )
    with pytest.raises(ValueError, match="identity"):
        require_installer_app(app, lambda _: pytest.fail("must refuse before commands"))


def test_mismatched_payload_refused_before_outer_signature_or_mount(
    tmp_path, monkeypatch
):
    from scripts import build_macos_dmg as owner

    app = tmp_path / ENTRY
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/VODForgeInstaller").write_bytes(b"fixture")
    executable = app / "Contents/Resources/VODForge.app/Contents/MacOS/VODForge"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"changed-payload")
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "com.snowfallhd.vodforge.installer",
                "CFBundleExecutable": "VODForgeInstaller",
                "VFExecutableSHA256": "0" * 64,
            }
        )
    )
    # Payload signature admission is separate; this regression isolates the
    # installer's immutable binding to the exact admitted executable.
    monkeypatch.setattr(owner, "require_universal_app", lambda *args: {})
    with pytest.raises(ValueError, match="bound executable"):
        owner.require_installer_app(
            app, lambda _: pytest.fail("must refuse before outer commands")
        )


def test_assembly_refuses_nonempty_evidence_directory_before_payload_work(tmp_path):
    from scripts.build_macos_installer import build_installer

    retained = tmp_path / "retained-evidence"
    retained.write_bytes(b"keep")
    with pytest.raises(ValueError, match="fresh empty"):
        build_installer(tmp_path / "absent.app", tmp_path / ENTRY)
    assert retained.read_bytes() == b"keep"
