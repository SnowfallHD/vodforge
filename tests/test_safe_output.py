from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.app import package_downloaded_media_from_staging
from yt_downloader.safe_output import UnsafeOutputPathError, is_symlink_or_reparse


def _symlink_directory_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable on this host: {exc}")


def _staged_media(tmp_path: Path) -> tuple[Path, Path]:
    staging_dir = tmp_path / "staging"
    staged = staging_dir / "id123.mp4"
    staging_dir.mkdir()
    staged.write_bytes(b"synthetic staged media")
    return staging_dir, staged


@pytest.mark.parametrize(
    "link_parts",
    [
        ("Creator",),
        ("Creator", "videos - no playlist"),
        ("Creator", "videos - no playlist", "Title [id123]"),
    ],
)
def test_packaging_rejects_symlink_at_every_output_directory_depth(
    tmp_path: Path,
    link_parts: tuple[str, ...],
):
    output_root = tmp_path / "chosen-output"
    outside = tmp_path / "outside"
    output_root.mkdir()
    outside.mkdir()
    staging_dir, staged = _staged_media(tmp_path)
    link = output_root.joinpath(*link_parts)
    link.parent.mkdir(parents=True, exist_ok=True)
    _symlink_directory_or_skip(link, outside)
    info = {"id": "id123", "title": "Title", "uploader": "Creator"}

    with pytest.raises(UnsafeOutputPathError, match="safe directory|redirects"):
        package_downloaded_media_from_staging(
            staging_dir,
            output_root,
            info,
            expected_extension=".mp4",
            staged_media=[(info, staged)],
        )

    assert staged.read_bytes() == b"synthetic staged media"
    assert not list(outside.rglob("*"))
    assert "_vodforge_output_dir" not in info


def test_packaging_rejects_descendant_symlink_even_when_it_points_inside_root(
    tmp_path: Path,
):
    output_root = tmp_path / "chosen-output"
    inside_target = output_root / "safe-real-directory"
    output_root.mkdir()
    inside_target.mkdir()
    staging_dir, staged = _staged_media(tmp_path)
    _symlink_directory_or_skip(output_root / "Creator", inside_target)
    info = {"id": "id123", "title": "Title", "uploader": "Creator"}

    with pytest.raises(UnsafeOutputPathError):
        package_downloaded_media_from_staging(
            staging_dir,
            output_root,
            info,
            expected_extension=".mp4",
            staged_media=[(info, staged)],
        )

    assert staged.exists()
    assert not list(inside_target.rglob("*"))
    assert "_vodforge_output_dir" not in info


def test_packaging_rechecks_directory_chain_after_cancellation_barrier(tmp_path: Path):
    output_root = tmp_path / "chosen-output"
    outside = tmp_path / "outside"
    output_root.mkdir()
    outside.mkdir()
    staging_dir, staged = _staged_media(tmp_path)
    info = {"id": "id123", "title": "Title", "uploader": "Creator"}
    target_dir = output_root / "Creator" / "videos - no playlist" / "Title [id123]"
    displaced = output_root / "displaced-target"

    def swap_created_directory_for_symlink() -> None:
        target_dir.rename(displaced)
        _symlink_directory_or_skip(target_dir, outside)

    with pytest.raises(UnsafeOutputPathError):
        package_downloaded_media_from_staging(
            staging_dir,
            output_root,
            info,
            expected_extension=".mp4",
            staged_media=[(info, staged)],
            control_check=swap_created_directory_for_symlink,
        )

    assert staged.exists()
    assert not list(outside.rglob("*"))
    assert "_vodforge_output_dir" not in info


def test_packaging_rejects_preexisting_symlink_output_file(tmp_path: Path):
    output_root = tmp_path / "chosen-output"
    outside = tmp_path / "outside"
    outside.mkdir()
    staging_dir, staged = _staged_media(tmp_path)
    info = {"id": "id123", "title": "Title", "uploader": "Creator"}
    target = (
        output_root / "Creator" / "videos - no playlist" / "Title [id123]" / "Title.mp4"
    )
    target.parent.mkdir(parents=True)
    outside_file = outside / "existing.mp4"
    outside_file.write_bytes(b"outside bytes")
    try:
        target.symlink_to(outside_file)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable on this host: {exc}")

    with pytest.raises(UnsafeOutputPathError, match="filename"):
        package_downloaded_media_from_staging(
            staging_dir,
            output_root,
            info,
            expected_extension=".mp4",
            staged_media=[(info, staged)],
        )

    assert staged.exists()
    assert outside_file.read_bytes() == b"outside bytes"
    assert "_vodforge_output_dir" not in info


def test_user_selected_symlink_root_remains_a_valid_anchor(tmp_path: Path):
    real_output = tmp_path / "real-output"
    selected_output = tmp_path / "selected-output"
    real_output.mkdir()
    _symlink_directory_or_skip(selected_output, real_output)
    staging_dir, staged = _staged_media(tmp_path)
    info = {"id": "id123", "title": "Title", "uploader": "Creator"}

    packaged = package_downloaded_media_from_staging(
        staging_dir,
        selected_output,
        info,
        expected_extension=".mp4",
        staged_media=[(info, staged)],
    )

    expected = (
        selected_output
        / "Creator"
        / "videos - no playlist"
        / "Title [id123]"
        / "Title.mp4"
    )
    assert packaged == [expected]
    assert expected.read_bytes() == b"synthetic staged media"
    assert expected.resolve().is_relative_to(real_output.resolve())
    assert info["_vodforge_output_dir"] == str(expected.parent)


def test_windows_reparse_attribute_is_treated_as_redirect():
    fake_stat = SimpleNamespace(
        st_mode=stat.S_IFDIR,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )

    assert is_symlink_or_reparse(fake_stat)


def test_abandoned_cleanup_removes_only_recorded_transactions(tmp_path: Path):
    from yt_downloader.safe_output import cleanup_abandoned_staging_transactions

    root = tmp_path / ".vfstage"
    first = root / "first"
    second = root / "second"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "partial.mp4").write_bytes(b"partial")
    (second / "partial.webm").write_bytes(b"partial")

    cleanup_abandoned_staging_transactions([first, second])

    assert not root.exists()


def test_abandoned_cleanup_rejects_paths_outside_staging_root(tmp_path: Path):
    from yt_downloader.safe_output import (
        UnsafeOutputPathError,
        cleanup_abandoned_staging_transactions,
    )

    outside = tmp_path / "ordinary" / "transaction"
    outside.mkdir(parents=True)

    with pytest.raises(UnsafeOutputPathError, match="outside"):
        cleanup_abandoned_staging_transactions([outside])

    assert outside.exists()


def test_abandoned_cleanup_preserves_unknown_staging_entries(tmp_path: Path):
    from yt_downloader.safe_output import cleanup_abandoned_staging_transactions

    root = tmp_path / ".vfstage"
    recorded = root / "recorded"
    unknown = root / "unrelated"
    recorded.mkdir(parents=True)
    unknown.mkdir()

    cleanup_abandoned_staging_transactions([recorded])

    assert not recorded.exists()
    assert unknown.exists()


@pytest.mark.parametrize("kind", ["metadata", "thumbnail"])
def test_optional_sidecar_never_overwrites_a_symlink_target(
    tmp_path, monkeypatch, kind
):
    from io import BytesIO

    from PIL import Image

    from yt_downloader import app

    output = tmp_path / "selected"
    output.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated original")
    info = {
        "id": "sidecar",
        "title": "Sidecar",
        "thumbnail": "https://fixture.invalid/image",
    }
    name = app.safe_metadata_filename(info) if kind == "metadata" else "thumbnail.jpeg"
    try:
        (output / name).symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")
    encoded = BytesIO()
    Image.new("RGB", (24, 24), "blue").save(encoded, format="PNG")
    monkeypatch.setattr(
        app, "download_bounded_url_bytes", lambda *_a, **_k: encoded.getvalue()
    )
    try:
        if kind == "metadata":
            app.write_compact_video_metadata(output, info, [])
        else:
            app.save_thumbnail_image(output, info)
    except UnsafeOutputPathError:
        pass
    assert outside.read_bytes() == b"unrelated original"
    assert (output / name).is_symlink()
    assert not (output / ".vfstage").exists()


@pytest.mark.parametrize("owned", [False, True])
@pytest.mark.parametrize("inside", [False, True])
def test_reuse_does_not_adopt_descendant_directory_links(
    tmp_path, monkeypatch, owned, inside
):
    from yt_downloader import app
    from yt_downloader.models import OutputType

    root = tmp_path / "selected"
    root.mkdir()
    target = (root if inside else tmp_path) / "unrelated"
    target.mkdir()
    info = {"id": "link123", "title": "Linked", "uploader": "Creator"}
    candidate = app.video_output_dir(root, info)
    candidate.parent.mkdir(parents=True)
    _symlink_directory_or_skip(candidate, target)
    media = candidate / app.video_file_name(info, ".mp4")
    media.write_bytes(b"independent media")
    monkeypatch.setattr(
        app, "_validate_existing_output_candidate", lambda *_a, **_k: {"format": {}}
    )
    found = app.find_valid_existing_output(
        root,
        info,
        OutputType.MP4,
        "ffprobe",
        owned_legacy_paths=(media,) if owned else (),
    )
    assert found is None
    assert (target / media.name).read_bytes() == b"independent media"


@pytest.mark.parametrize("kind", ["metadata", "thumbnail"])
@pytest.mark.parametrize("linked_root", [False, True])
def test_sidecar_root_and_child_link_policy(tmp_path, monkeypatch, kind, linked_root):
    from io import BytesIO

    from PIL import Image

    from yt_downloader import app

    real = tmp_path / "real"
    real.mkdir()
    selected = tmp_path / "chosen"
    _symlink_directory_or_skip(selected, real)
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = selected / "item"
    if linked_root:
        destination.mkdir()
    else:
        _symlink_directory_or_skip(destination, outside)
    info = {"id": "root", "title": "Root", "thumbnail": "https://fixture.invalid/image"}
    encoded = BytesIO()
    Image.new("RGB", (24, 24), "blue").save(encoded, format="PNG")
    monkeypatch.setattr(
        app, "download_bounded_url_bytes", lambda *_a, **_k: encoded.getvalue()
    )

    def write():
        if kind == "metadata":
            return app.write_compact_video_metadata(
                destination, info, [], output_root=selected
            )
        return app.save_thumbnail_image(destination, info, output_root=selected)

    if linked_root:
        result = write()
        assert result.is_file()
        assert result.resolve().is_relative_to(real)
        if kind == "metadata":
            import json

            assert json.loads(result.read_text())["id"] == "root"
        else:
            with Image.open(result) as image:
                assert image.size == (24, 24)
    else:
        with pytest.raises(UnsafeOutputPathError):
            write()
    assert not list(outside.iterdir())
    assert not (real / ".vfstage").exists()


def test_failed_optional_write_preserves_previous_file_and_cleans_stage(tmp_path):
    from yt_downloader.safe_output import write_file_beneath

    destination = tmp_path / "metadata.json"
    destination.write_bytes(b"previous")

    def interrupted(staged):
        staged.write_bytes(b"partial")
        raise OSError("controlled writer interruption")

    with pytest.raises(OSError, match="controlled writer interruption"):
        write_file_beneath(tmp_path, destination, interrupted)
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [destination]


def test_optional_commit_rechecks_parent_after_writer(tmp_path):
    from yt_downloader.safe_output import write_file_beneath

    root = tmp_path / "selected"
    item = root / "item"
    item.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "metadata.json"
    target.write_bytes(b"unrelated original")

    def swap_after_encode(staged):
        staged.write_bytes(b"new sidecar")
        item.rmdir()
        _symlink_directory_or_skip(item, outside)

    with pytest.raises(UnsafeOutputPathError):
        write_file_beneath(root, item / "metadata.json", swap_after_encode)
    assert target.read_bytes() == b"unrelated original"
    assert not (root / ".vfstage").exists()
