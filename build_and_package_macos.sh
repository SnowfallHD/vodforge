#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

version="${1:-}"
./build_macos.sh

mkdir -p dist/release
if [[ -n "$version" ]]; then
  archive="dist/release/VODForge-macOS-v${version}.zip"
else
  archive="dist/release/VODForge-macOS.zip"
fi
rm -f "$archive"
ditto -c -k --sequesterRsrc --keepParent "dist/VODForge.app" "$archive"

echo "Packaged unsigned application: $archive"
