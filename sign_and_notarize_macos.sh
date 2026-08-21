#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS signing and notarization must run on macOS."
  exit 1
fi

app_path="${1:-}"
archive_path="${2:-}"
identity="${VODFORGE_MACOS_SIGN_IDENTITY:-Developer ID Application: Kryden Ventures, LLC (76G5W4954G)}"
notary_profile="${VODFORGE_NOTARY_PROFILE:-kryden}"

if [[ -z "$app_path" || -z "$archive_path" ]]; then
  echo "Usage: ./sign_and_notarize_macos.sh path/to/VODForge.app path/to/release.zip"
  exit 1
fi
if [[ ! -d "$app_path" || "$app_path" != *.app ]]; then
  echo "Expected an application bundle: $app_path"
  exit 1
fi
if [[ "$archive_path" != *.zip ]]; then
  echo "The release archive must use a .zip extension: $archive_path"
  exit 1
fi
if ! security find-identity -v -p codesigning | grep -Fq "\"$identity\""; then
  echo "Developer ID signing identity is unavailable: $identity"
  exit 1
fi
if ! xcrun notarytool history --keychain-profile "$notary_profile" --output-format json >/dev/null; then
  echo "Notarization keychain profile is unavailable: $notary_profile"
  exit 1
fi

codesign --force --deep --strict --options runtime --timestamp --sign "$identity" "$app_path"
codesign --verify --deep --strict --verbose=2 "$app_path"

notary_dir="$(mktemp -d "${TMPDIR:-/tmp}/vodforge-notary.XXXXXX")"
cleanup() {
  rm -rf "$notary_dir"
}
trap cleanup EXIT

notary_archive="$notary_dir/VODForge-notary.zip"
ditto -c -k --sequesterRsrc --keepParent "$app_path" "$notary_archive"
notary_result="$notary_dir/notary-result.json"
xcrun notarytool submit "$notary_archive" \
  --keychain-profile "$notary_profile" \
  --wait \
  --output-format json > "$notary_result"

notary_status="$(plutil -extract status raw -o - "$notary_result")"
if [[ "$notary_status" != "Accepted" ]]; then
  submission_id="$(plutil -extract id raw -o - "$notary_result" 2>/dev/null || true)"
  if [[ -n "$submission_id" ]]; then
    xcrun notarytool log "$submission_id" --keychain-profile "$notary_profile" || true
  fi
  echo "Apple notarization was not accepted: $notary_status"
  exit 1
fi

xcrun stapler staple "$app_path"
xcrun stapler validate "$app_path"
codesign --verify --deep --strict --verbose=2 "$app_path"
spctl --assess --type execute --verbose=2 "$app_path"

mkdir -p "$(dirname "$archive_path")"
rm -f "$archive_path"
ditto -c -k --sequesterRsrc --keepParent "$app_path" "$archive_path"
echo "Signed, notarized, stapled, and packaged application: $archive_path"
