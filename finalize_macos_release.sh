#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

version="${1:-}"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: ./finalize_macos_release.sh 1.2.3"
  exit 1
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Release finalization must run on the signing Mac."
  exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Release finalization must run from main."
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Release finalization requires a clean worktree."
  exit 1
fi

repo="SnowfallHD/vodforge"
tag="v${version}"
head_sha="$(git rev-parse HEAD)"
release_json="$(gh release view "$tag" --repo "$repo" --json isDraft,targetCommitish)"
if [[ "$(plutil -extract isDraft raw -o - - <<<"$release_json")" != "true" ]]; then
  echo "The release must still be a draft: $tag"
  exit 1
fi
if [[ "$(plutil -extract targetCommitish raw -o - - <<<"$release_json")" != "$head_sha" ]]; then
  echo "The draft release does not target current main: $head_sha"
  exit 1
fi

finalize_dir="$(mktemp -d "${TMPDIR:-/tmp}/vodforge-release-${version}.XXXXXX")"
cleanup() {
  rm -rf "$finalize_dir"
}
trap cleanup EXIT

universal_unsigned="VODForge-macOS-universal2-v${version}-unsigned-review.zip"
windows_installer="VODForge-Windows-Setup-v${version}.exe"
windows_portable="VODForge-Windows-Portable-v${version}.zip"
dmg="VODForge-macOS-universal2-v${version}.dmg"
universal_zip="VODForge-macOS-universal2-v${version}.zip"
# Same universal app under the names VODForge 0.2.5 and earlier update from.
# See docs/release.md before removing these.
legacy_arm_zip="VODForge-macOS-arm64-v${version}.zip"
legacy_intel_zip="VODForge-macOS-x64-v${version}.zip"

gh release download "$tag" --repo "$repo" --dir "$finalize_dir" \
  --pattern "$universal_unsigned" \
  --pattern "$windows_installer" \
  --pattern "$windows_portable"

python_bin=".venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "Run ./install_macos_dependencies.sh first so the release tools can run."
  exit 1
fi
mac_dir="$finalize_dir/mac"
"$python_bin" -m scripts.finalize_universal_macos \
  --unsigned-zip "$finalize_dir/$universal_unsigned" \
  --output "$mac_dir" \
  --version "$version"
for file in "$dmg" "$universal_zip" "$legacy_arm_zip" "$legacy_intel_zip"; do
  mv "$mac_dir/$file" "$finalize_dir/$file"
done

(
  cd "$finalize_dir"
  shasum -a 256 \
    "$windows_installer" \
    "$windows_portable" \
    "$dmg" \
    "$universal_zip" \
    "$legacy_arm_zip" \
    "$legacy_intel_zip" \
    | sort -k2 > SHA256SUMS.txt
)

gh release upload "$tag" --repo "$repo" --clobber \
  "$finalize_dir/$dmg" \
  "$finalize_dir/$universal_zip" \
  "$finalize_dir/$legacy_arm_zip" \
  "$finalize_dir/$legacy_intel_zip" \
  "$finalize_dir/SHA256SUMS.txt"
gh release delete-asset "$tag" "$universal_unsigned" --repo "$repo" --yes
python3 .github/scripts/render_release_notes.py "$version" > "$finalize_dir/release-notes.md"
gh release edit "$tag" --repo "$repo" --notes-file "$finalize_dir/release-notes.md"

# Keep the notarization receipt; the temporary folder is removed on exit.
mkdir -p build
cp "$mac_dir/macos-release-receipt.json" "build/macos-release-receipt-v${version}.json"
echo "Signed Mac DMG, update archives and checksums uploaded to draft release $tag."
echo "Apple notarization results: build/macos-release-receipt-v${version}.json"
echo "Review the release assets and checksums before publishing."
