#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The pinned macOS libVLC runtime must be installed on macOS."
  exit 1
fi

version="3.0.23"
case "$(uname -m)" in
  arm64)
    archive_name="vlc-${version}-arm64.dmg"
    expected_sha256="fc6fac08d87f538517d44aca0c5e7a244b67c8c4cb589bf478363a7315fd5e0d"
    ;;
  x86_64)
    archive_name="vlc-${version}-intel64.dmg"
    expected_sha256="ec01530ce69d849dd057fba8876e68ac39bf279dc28de4e9c04e4aec11fc98db"
    ;;
  *)
    echo "Unsupported macOS architecture: $(uname -m)"
    exit 1
    ;;
esac

temporary_dir="$(mktemp -d)"
archive="$temporary_dir/$archive_name"
mount_dir="$temporary_dir/mount"
mounted=0
cleanup() {
  if [[ "$mounted" == "1" ]]; then
    hdiutil detach "$mount_dir" -quiet || true
  fi
  rm -rf "$temporary_dir"
}
trap cleanup EXIT
mkdir -p "$mount_dir"

url="https://get.videolan.org/vlc/${version}/macosx/${archive_name}"
echo "Downloading pinned libVLC $version from VideoLAN"
curl --fail --location --retry 3 --output "$archive" "$url"
actual_sha256="$(shasum -a 256 "$archive" | awk '{print $1}')"
if [[ "$actual_sha256" != "$expected_sha256" ]]; then
  echo "VideoLAN archive checksum mismatch: expected $expected_sha256, got $actual_sha256"
  exit 1
fi

hdiutil attach "$archive" -nobrowse -readonly -mountpoint "$mount_dir" -quiet
mounted=1
source_app="$mount_dir/VLC.app"
source_runtime="$source_app/Contents/MacOS"
if [[ ! -f "$source_runtime/lib/libvlc.dylib" || ! -f "$source_runtime/lib/libvlccore.dylib" || ! -d "$source_runtime/plugins" ]]; then
  echo "The official VideoLAN image did not contain a complete libVLC runtime."
  exit 1
fi
/usr/bin/codesign --verify --deep --strict "$source_app"
team_identifier="$(/usr/bin/codesign -dv --verbose=4 "$source_app" 2>&1 | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
if [[ "$team_identifier" != "75GAHG3SZQ" ]]; then
  echo "The VideoLAN runtime has an unexpected signing team: ${team_identifier:-missing}."
  exit 1
fi

vendor="$PWD/vendor/vlc"
rm -rf "$vendor"
mkdir -p "$vendor/lib"
ditto "$source_runtime/lib/libvlc.dylib" "$vendor/lib/libvlc.dylib"
ditto "$source_runtime/lib/libvlccore.dylib" "$vendor/lib/libvlccore.dylib"
ditto "$source_runtime/plugins" "$vendor/plugins"
# VODForge supplies its own UI and notifications. These two VLC-app plugins
# require Sparkle/Growl frameworks that are intentionally not part of libVLC.
rm -f \
  "$vendor/plugins/libmacosx_plugin.dylib" \
  "$vendor/plugins/libosx_notifications_plugin.dylib"
printf '%s' "$version" > "$vendor/VODFORGE_VLC_VERSION"
echo "Installed verified libVLC $version to vendor/vlc"
