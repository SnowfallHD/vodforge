#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS."
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and run this script again."
  exit 1
fi

echo "Installing the macOS Python/Tk runtime, FFmpeg, Deno, and libVLC..."
brew install python@3.13 python-tk@3.13 ffmpeg deno
./install_vlc_macos.sh

python_bin="$(brew --prefix python@3.13)/bin/python3.13"
if [[ ! -x "$python_bin" ]]; then
  echo "Homebrew Python 3.13 was not found at $python_bin"
  exit 1
fi

"$python_bin" -c 'import tkinter; print(f"Tk {tkinter.TkVersion} ready")'
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

echo "macOS dependencies are ready. Run: .venv/bin/python main.py"
