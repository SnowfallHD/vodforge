#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The macOS application must be built on macOS."
  exit 1
fi

python_bin="${VODFORGE_PYTHON:-}"
if [[ -z "$python_bin" && -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
fi
if [[ -z "$python_bin" ]] && command -v python3.13 >/dev/null 2>&1; then
  python_bin="$(command -v python3.13)"
fi
if [[ -z "$python_bin" && -x "/opt/homebrew/opt/python@3.13/bin/python3.13" ]]; then
  python_bin="/opt/homebrew/opt/python@3.13/bin/python3.13"
fi
if [[ -z "$python_bin" ]]; then
  echo "Python 3.13 with Tk was not found. Run ./install_macos_dependencies.sh first."
  exit 1
fi

if ! "$python_bin" -c 'import tkinter' >/dev/null 2>&1; then
  echo "The selected Python does not include Tk: $python_bin"
  echo "Run ./install_macos_dependencies.sh or set VODFORGE_PYTHON to a Tk-enabled Python 3.11+."
  exit 1
fi

if [[ "$python_bin" != ".venv/bin/python" ]]; then
  "$python_bin" -m venv .venv
  python_bin=".venv/bin/python"
fi

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -r requirements-dev.txt
"$python_bin" -m compileall -q yt_downloader main.py macos_smoke_test.py
"$python_bin" -m pytest -q

build_version="${VODFORGE_BUILD_VERSION:-0.1.0-dev}"
if [[ ! "$build_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  echo "VODFORGE_BUILD_VERSION must use semantic versioning, for example 1.2.3."
  exit 1
fi
build_version_dir="build/version"
mkdir -p "$build_version_dir"
build_version_file="$build_version_dir/VODFORGE_VERSION"
printf '%s' "$build_version" > "$build_version_file"
icon_file="assets/VODForge.icns"
icon_png="assets/VODForge.png"
macos_icon_source="assets/VODForge-macos.png"
icon_asset_dir="assets/icons/lucide"
if [[ ! -f "$icon_file" || ! -f "$icon_png" || ! -f "$macos_icon_source" || ! -d "$icon_asset_dir" ]]; then
  echo "VODForge icon assets are missing."
  exit 1
fi

ffmpeg="$(command -v ffmpeg || true)"
ffprobe="$(command -v ffprobe || true)"
deno="$(command -v deno || true)"
if [[ -z "$ffmpeg" || -z "$ffprobe" || -z "$deno" ]]; then
  echo "FFmpeg, ffprobe, and Deno are required for a self-contained app."
  echo "Run ./install_macos_dependencies.sh first."
  exit 1
fi

"$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "VODForge" \
  --collect-all yt_dlp \
  --osx-bundle-identifier "com.snowfallhd.vodforge" \
  --icon "$icon_file" \
  --add-data "$build_version_file:." \
  --add-data "$icon_png:assets" \
  --add-data "$icon_asset_dir:assets/icons/lucide" \
  --add-binary "$ffmpeg:." \
  --add-binary "$ffprobe:." \
  --add-binary "$deno:." \
  main.py

app_binary="dist/VODForge.app/Contents/MacOS/VODForge"
if [[ ! -x "$app_binary" ]]; then
  echo "Expected application executable was not created: $app_binary"
  exit 1
fi

app_plist="dist/VODForge.app/Contents/Info.plist"
bundle_version="${build_version%%-*}"
for version_key in CFBundleShortVersionString CFBundleVersion; do
  if /usr/libexec/PlistBuddy -c "Print :$version_key" "$app_plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$version_key $bundle_version" "$app_plist"
  else
    /usr/libexec/PlistBuddy -c "Add :$version_key string $bundle_version" "$app_plist"
  fi
done

if [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app_plist")" != "$bundle_version" ]] || \
   [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app_plist")" != "$bundle_version" ]]; then
  echo "Packaged macOS version metadata does not match $bundle_version."
  exit 1
fi

bundle_icon_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIconFile' "$app_plist")"
bundle_icon="dist/VODForge.app/Contents/Resources/$bundle_icon_name"
if [[ "$bundle_icon_name" != "VODForge.icns" ]] || [[ ! -f "$bundle_icon" ]] || ! cmp -s "$icon_file" "$bundle_icon"; then
  echo "Packaged macOS Finder and Dock icon must both use the exact VODForge.icns asset."
  exit 1
fi

# PyInstaller ad-hoc signs the initial bundle, but the version metadata above is
# intentionally finalized afterward. Re-sign only after every local bundle
# mutation so the test application is structurally valid on disk. Public
# releases still replace this ad-hoc signature with Developer ID signing.
/usr/bin/codesign --force --deep --sign - "dist/VODForge.app"
/usr/bin/codesign --verify --deep --strict "dist/VODForge.app"

"$app_binary" --runtime-smoke
echo "Built ad-hoc signed local VODForge v${build_version}: dist/VODForge.app"
echo "Developer ID signing and notarization are still required before public distribution."
