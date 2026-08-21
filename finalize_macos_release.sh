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

arm_unsigned="VODForge-macOS-arm64-v${version}-unsigned-review.zip"
x64_unsigned="VODForge-macOS-x64-v${version}-unsigned-review.zip"
windows_installer="VODForge-Windows-Setup-v${version}.exe"
windows_portable="VODForge-Windows-Portable-v${version}.zip"

gh release download "$tag" --repo "$repo" --dir "$finalize_dir" \
  --pattern "$arm_unsigned" \
  --pattern "$x64_unsigned" \
  --pattern "$windows_installer" \
  --pattern "$windows_portable"

for arch in arm64 x64; do
  unsigned_name="VODForge-macOS-${arch}-v${version}-unsigned-review.zip"
  signed_name="VODForge-macOS-${arch}-v${version}.zip"
  extract_dir="$finalize_dir/${arch}"
  mkdir -p "$extract_dir"
  ditto -x -k "$finalize_dir/$unsigned_name" "$extract_dir"
  app_path="$extract_dir/VODForge.app"
  if [[ ! -d "$app_path" ]]; then
    echo "Expected VODForge.app was not found in $unsigned_name"
    exit 1
  fi
  ./sign_and_notarize_macos.sh "$app_path" "$finalize_dir/$signed_name"
  if [[ "$arch" == "arm64" ]]; then
    "$app_path/Contents/MacOS/VODForge" --runtime-smoke
  else
    arch -x86_64 "$app_path/Contents/MacOS/VODForge" --runtime-smoke
  fi
done

(
  cd "$finalize_dir"
  shasum -a 256 \
    "$windows_installer" \
    "$windows_portable" \
    "VODForge-macOS-arm64-v${version}.zip" \
    "VODForge-macOS-x64-v${version}.zip" \
    | sort -k2 > SHA256SUMS.txt
)

gh release upload "$tag" --repo "$repo" --clobber \
  "$finalize_dir/VODForge-macOS-arm64-v${version}.zip" \
  "$finalize_dir/VODForge-macOS-x64-v${version}.zip" \
  "$finalize_dir/SHA256SUMS.txt"
gh release delete-asset "$tag" "$arm_unsigned" --repo "$repo" --yes
gh release delete-asset "$tag" "$x64_unsigned" --repo "$repo" --yes

echo "Final signed artifacts and checksums uploaded to draft release $tag."
echo "Review the release assets and checksums before publishing."
