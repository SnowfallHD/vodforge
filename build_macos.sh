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
  --osx-bundle-identifier "com.snowfallhd.vodforge" \
  --add-binary "$ffmpeg:." \
  --add-binary "$ffprobe:." \
  --add-binary "$deno:." \
  main.py

app_binary="dist/VODForge.app/Contents/MacOS/VODForge"
if [[ ! -x "$app_binary" ]]; then
  echo "Expected application executable was not created: $app_binary"
  exit 1
fi

"$app_binary" --runtime-smoke
echo "Built unsigned local application: dist/VODForge.app"
echo "Developer ID signing and notarization are still required before public distribution."
