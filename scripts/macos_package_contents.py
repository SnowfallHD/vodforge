"""What goes into the macOS app bundle, shared by the regular and universal builds.

`build_macos.sh` (one architecture) and `scripts/build_universal_macos.py`
(universal2) both take their PyInstaller options from here, so the two apps
carry the same files. Print the options with:

    python -m scripts.macos_package_contents --version-dir DIR --native-helper LIB \
        --ffmpeg PATH --ffprobe PATH --deno PATH [--extra-binary PATH ...]

Options are printed NUL-separated so shell callers can read them safely.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.build_macos_fullscreen import (
    PACKAGE_DESTINATION as NATIVE_HELPER_DESTINATION,
)

ROOT = Path(__file__).resolve().parent.parent

# (source relative to the repository, destination folder inside the bundle).
DATA = (
    ("assets/VODForge.png", "assets"),
    ("assets/posthog-public-config.json", "assets"),
    ("assets/brand", "assets/brand"),
    ("assets/materials", "assets/materials"),
    ("assets/icons/lucide", "assets/icons/lucide"),
    ("assets/watch-welcome-scenic.png", "assets"),
    ("assets/preview_thumbnails/alpine-lake.jpg", "assets/preview_thumbnails"),
    ("assets/whats-new/forge-feedback.mp4", "assets/whats-new"),
    ("assets/whats-new/forge-feedback.jpg", "assets/whats-new"),
    ("assets/whats-new/watch-player.mp4", "assets/whats-new"),
    ("assets/whats-new/watch-player.jpg", "assets/whats-new"),
    ("assets/whats-new/library-actions.mp4", "assets/whats-new"),
    ("assets/whats-new/library-actions.jpg", "assets/whats-new"),
    ("assets/whats-new/captions-player.mp4", "assets/whats-new"),
    ("assets/whats-new/captions-player.jpg", "assets/whats-new"),
    ("assets/whats-new/manifest.json", "assets/whats-new"),
    ("assets/onboarding/library.png", "assets/onboarding"),
    ("assets/onboarding/watch.png", "assets/onboarding"),
    ("assets/onboarding/forge.png", "assets/onboarding"),
    ("THIRD_PARTY_NOTICES.md", "."),
)
VERSION_FILES = (
    "VODFORGE_VERSION",
    "VODFORGE_BUILD_REVISION",
    "VODFORGE_TELEMETRY_POLICY",
)
QML_DIR = "yt_downloader/qt_quick"
ICON = "assets/VODForge.icns"
BUNDLE_IDENTIFIER = "com.snowfallhd.vodforge"


def pyinstaller_options(
    *,
    version_dir: Path,
    native_helper: Path,
    helpers: list[Path],
    root: Path = ROOT,
) -> list[str]:
    """PyInstaller options describing the bundle's contents and identity."""
    options = [
        "--windowed",
        "--onedir",
        "--name",
        "VODForge",
        "--osx-bundle-identifier",
        BUNDLE_IDENTIFIER,
        "--icon",
        str(root / ICON),
        "--collect-all",
        "yt_dlp",
        "--collect-all",
        "curl_cffi",
        "--collect-data",
        "certifi",
        "--hidden-import",
        "PySide6.QtMultimedia",
        "--hidden-import",
        "PySide6.QtQuickControls2",
        "--exclude-module",
        "vlc",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "PIL.ImageTk",
        # Source-run FFmpeg fallback; the app bundles its own FFmpeg, and
        # PyInstaller would otherwise add imageio's 47 MB copy.
        "--exclude-module",
        "imageio_ffmpeg",
    ]
    for name in VERSION_FILES:
        path = version_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing build metadata file: {path}")
        options += ["--add-data", f"{path}:."]
    for source, destination in DATA:
        path = root / source
        if not path.exists():
            raise FileNotFoundError(f"Missing packaged asset: {path}")
        options += ["--add-data", f"{path}:{destination}"]
    qml = sorted((root / QML_DIR).glob("*.qml"))
    if not qml:
        raise FileNotFoundError("No QML files found")
    for path in qml:
        options += ["--add-data", f"{path}:{QML_DIR}"]
    for path in helpers:
        if not path.is_file():
            raise FileNotFoundError(f"Missing helper binary: {path}")
        options += ["--add-binary", f"{path}:."]
    if not native_helper.is_file():
        raise FileNotFoundError(f"Missing native helper: {native_helper}")
    options += ["--add-binary", f"{native_helper}:{NATIVE_HELPER_DESTINATION}"]
    return options


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-dir", type=Path, required=True)
    parser.add_argument("--native-helper", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--deno", type=Path, required=True)
    parser.add_argument("--extra-binary", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    options = pyinstaller_options(
        version_dir=args.version_dir,
        native_helper=args.native_helper,
        helpers=[args.ffmpeg, args.ffprobe, args.deno, *args.extra_binary],
    )
    sys.stdout.write("\0".join(options) + "\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
