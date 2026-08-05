#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

version="${1:-}"
export VODFORGE_BUILD_VERSION="${version:-0.1.0-dev}"
./build_macos.sh

mkdir -p dist/release
machine_arch="$(uname -m)"
if [[ "$machine_arch" == "x86_64" ]]; then
  release_arch="x64"
else
  release_arch="$machine_arch"
fi
if [[ -n "$version" ]]; then
  archive="dist/release/VODForge-macOS-${release_arch}-v${version}.zip"
else
  archive="dist/release/VODForge-macOS-${release_arch}.zip"
fi
rm -f "$archive"
ditto -c -k --sequesterRsrc --keepParent "dist/VODForge.app" "$archive"

echo "Packaged unsigned application: $archive"
