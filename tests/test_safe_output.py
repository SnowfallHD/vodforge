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


def test_packaging_rejects_descendant_symlink_even_when_it_points_inside_root(tmp_path: Path):
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
    target = output_root / "Creator" / "videos - no playlist" / "Title [id123]" / "Title.mp4"
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

    expected = selected_output / "Creator" / "videos - no playlist" / "Title [id123]" / "Title.mp4"
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
