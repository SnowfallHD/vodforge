from __future__ import annotations

import hashlib
import json
import os
import platform
import plistlib
import re
import shutil

# Update verification uses fixed executables or injected argv-only runners, never a shell.
import subprocess  # nosec B404
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .windows_update_recovery import RECOVERY_FUNCTIONS

GITHUB_REPOSITORY = "SnowfallHD/vodforge"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPOSITORY}/releases/latest"
MAX_RELEASE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_UPDATE_ASSET_BYTES = 4 * 1024 * 1024 * 1024
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")
SHA256_RE = re.compile(r"^([0-9a-fA-F]{64})\s+[ *](.+)$")
MACOS_BUNDLE_ID = "com.snowfallhd.vodforge"
MACOS_TEAM_ID = "76G5W4954G"
WINDOWS_PUBLISHER = "Kryden Ventures, LLC"
# A PowerShell 7 -> Python -> Windows PowerShell launch can inherit incompatible
# PS7 modules. Update scripts need only the selected runtime's built-in modules.
WINDOWS_POWERSHELL_MODULE_PATH = "$env:PSModulePath = $PSHOME + '/Modules';"

MACOS_STAGING_PREFIX = "staged-"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag_name: str
    name: str
    html_url: str
    notes: str
    assets: tuple[ReleaseAsset, ...]


@dataclass(frozen=True)
class MacUpdatePlan:
    source_app: Path
    target_app: Path
    staging_root: Path


def semantic_version_key(version: str) -> tuple[int, int, int, int, str]:
    match = SEMVER_RE.fullmatch(str(version).strip())
    if not match:
        raise ValueError(f"Unsupported release version: {version!r}")
    major, minor, patch = (int(match.group(index)) for index in range(1, 4))
    prerelease = match.group(4) or ""
    return major, minor, patch, 1 if not prerelease else 0, prerelease


def is_newer_release(current_version: str, release_version: str) -> bool:
    return semantic_version_key(release_version) > semantic_version_key(current_version)


def _trusted_github_page(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "github.com",
        "www.github.com",
    }:
        raise ValueError("GitHub returned an invalid release page URL.")
    return url


def _trusted_github_download(
    url: str,
    *,
    tag_name: str,
    asset_name: str,
) -> str:
    expected_url = (
        f"https://github.com/{GITHUB_REPOSITORY}/releases/download/"
        f"{urllib.parse.quote(tag_name, safe='')}/{urllib.parse.quote(asset_name, safe='')}"
    )
    if url != expected_url:
        raise ValueError("GitHub returned an invalid release download URL.")
    return url


def parse_release_payload(payload: dict[str, Any]) -> ReleaseInfo:
    if payload.get("draft") or payload.get("prerelease"):
        raise ValueError("GitHub's latest release is not a public stable release.")
    tag_name = str(payload.get("tag_name") or "").strip()
    version_match = SEMVER_RE.fullmatch(tag_name)
    if not version_match:
        raise ValueError("GitHub's latest release does not use a semantic version tag.")
    if version_match.group(4):
        raise ValueError("GitHub's latest release is not a stable semantic version.")
    version = ".".join(version_match.group(index) for index in range(1, 4))
    assets: list[ReleaseAsset] = []
    for raw_asset in payload.get("assets") or []:
        if not isinstance(raw_asset, dict):
            continue
        name = str(raw_asset.get("name") or "").strip()
        download_url = str(raw_asset.get("browser_download_url") or "").strip()
        try:
            size = int(raw_asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not name or not download_url:
            continue
        assets.append(
            ReleaseAsset(
                name=name,
                download_url=_trusted_github_download(
                    download_url,
                    tag_name=tag_name,
                    asset_name=name,
                ),
                size=size,
            )
        )
    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        name=str(payload.get("name") or tag_name).strip(),
        html_url=_trusted_github_page(str(payload.get("html_url") or "").strip()),
        notes=str(payload.get("body") or "").strip(),
        assets=tuple(assets),
    )


def fetch_latest_release(*, timeout: float = 15) -> ReleaseInfo:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"VODForge update checker ({GITHUB_REPOSITORY})",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        # LATEST_RELEASE_API is a fixed HTTPS endpoint owned by this repository.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                "No packaged VODForge release is available yet."
            ) from exc
        raise RuntimeError(
            f"GitHub could not check for updates (HTTP {exc.code})."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "VODForge could not reach GitHub to check for updates."
        ) from exc
    if len(raw) > MAX_RELEASE_RESPONSE_BYTES:
        raise RuntimeError("GitHub returned an unexpectedly large release response.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub returned an unreadable release response.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(  # noqa: TRY004 - remote protocol failures use RuntimeError
            "GitHub returned an invalid release response."
        )
    return parse_release_payload(payload)


def release_asset_for_platform(
    release: ReleaseInfo,
    *,
    platform_name: str | None = None,
    machine: str | None = None,
) -> ReleaseAsset | None:
    platform_name = sys.platform if platform_name is None else platform_name
    machine = platform.machine().lower() if machine is None else machine.lower()
    if platform_name.startswith("win"):
        expected = f"VODForge-Windows-Setup-v{release.version}.exe"
    elif platform_name == "darwin":
        architecture = "arm64" if machine in {"arm64", "aarch64"} else "x64"
        expected = f"VODForge-macOS-{architecture}-v{release.version}.zip"
    else:
        return None
    return next((asset for asset in release.assets if asset.name == expected), None)


def parse_sha256sums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in text.splitlines():
        match = SHA256_RE.fullmatch(raw_line.strip())
        if match:
            checksums[match.group(2)] = match.group(1).lower()
    return checksums


def _fetch_small_text(url: str, *, timeout: float) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": f"VODForge updater ({GITHUB_REPOSITORY})"}
    )
    try:
        # The only caller passes an exact URL returned by _trusted_github_download.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError(
            "VODForge could not download the release checksums."
        ) from exc
    if len(raw) > MAX_RELEASE_RESPONSE_BYTES:
        raise RuntimeError("The release checksum file is unexpectedly large.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("The release checksum file is unreadable.") from exc


def download_verified_update(
    release: ReleaseInfo,
    destination_dir: Path,
    *,
    platform_name: str | None = None,
    machine: str | None = None,
    timeout: float = 60,
) -> Path:
    version_match = SEMVER_RE.fullmatch(str(release.tag_name).strip())
    normalized_tag_version = (
        ".".join(version_match.group(index) for index in range(1, 4))
        if version_match is not None and not version_match.group(4)
        else None
    )
    if normalized_tag_version != release.version:
        raise RuntimeError("This release contains invalid version metadata.")
    asset = release_asset_for_platform(
        release, platform_name=platform_name, machine=machine
    )
    if asset is None:
        raise RuntimeError("This release does not include an update for this computer.")
    if asset.size <= 0 or asset.size > MAX_UPDATE_ASSET_BYTES:
        raise RuntimeError("The release update has an invalid file size.")
    checksum_asset = next(
        (item for item in release.assets if item.name == "SHA256SUMS.txt"), None
    )
    if checksum_asset is None:
        raise RuntimeError("This release is missing its SHA-256 checksum manifest.")
    try:
        checksum_url = _trusted_github_download(
            checksum_asset.download_url,
            tag_name=release.tag_name,
            asset_name=checksum_asset.name,
        )
        asset_url = _trusted_github_download(
            asset.download_url,
            tag_name=release.tag_name,
            asset_name=asset.name,
        )
    except ValueError as exc:
        raise RuntimeError("This release contains an invalid download URL.") from exc
    expected_hash = parse_sha256sums(
        _fetch_small_text(checksum_url, timeout=timeout)
    ).get(asset.name)
    if not expected_hash:
        raise RuntimeError(
            "This release is missing the update file's SHA-256 checksum."
        )

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / asset.name
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    downloaded = 0
    request = urllib.request.Request(
        asset_url, headers={"User-Agent": f"VODForge updater ({GITHUB_REPOSITORY})"}
    )
    try:
        # asset_url was exact-canonicalized immediately above, before any network access.
        with (
            urllib.request.urlopen(request, timeout=timeout) as response,  # nosec B310
            temporary.open("wb") as output,
        ):
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > asset.size or downloaded > MAX_UPDATE_ASSET_BYTES:
                    raise RuntimeError(
                        "The release update exceeded its declared file size."
                    )
                digest.update(chunk)
                output.write(chunk)
        if downloaded != asset.size:
            raise RuntimeError(
                "The release update did not match its declared file size."
            )
        if digest.hexdigest().lower() != expected_hash:
            raise RuntimeError(
                "The release update failed SHA-256 verification and was not opened."
            )
        temporary.replace(destination)
        if os.name != "nt":
            destination.chmod(0o700)
        return destination
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError("VODForge could not download the release update.") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def running_macos_app(executable: Path | None = None) -> Path | None:
    """Return the enclosing installed .app bundle for a frozen macOS executable."""
    candidate = Path(sys.executable if executable is None else executable)
    for parent in (candidate, *candidate.parents):
        if parent.suffix.lower() == ".app":
            return parent
    return None


def _run_checked(
    command: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    result = runner(
        list(command),
        capture_output=True,
        text=True,
        check=False,
        **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "verification failed").strip()
        raise RuntimeError(detail)
    return result


def verify_macos_app(
    app_path: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Require the exact signed, notarized VODForge application identity."""
    app_path = Path(app_path)
    if not app_path.is_dir() or app_path.is_symlink():
        raise RuntimeError(
            "The macOS update did not contain a regular VODForge.app bundle."
        )
    plist_path = app_path / "Contents" / "Info.plist"
    try:
        with plist_path.open("rb") as handle:
            bundle_id = str(plistlib.load(handle).get("CFBundleIdentifier") or "")
    except (OSError, plistlib.InvalidFileException, TypeError, ValueError) as exc:
        raise RuntimeError(
            "The macOS update has an unreadable application identity."
        ) from exc
    if bundle_id != MACOS_BUNDLE_ID:
        raise RuntimeError("The macOS update has the wrong application identifier.")

    _run_checked(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app_path)],
        runner=runner,
    )
    details = _run_checked(
        ["/usr/bin/codesign", "-d", "--verbose=4", str(app_path)], runner=runner
    )
    signing_details = f"{details.stdout}\n{details.stderr}"
    fields = {}
    for line in signing_details.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key.strip()] = value.strip()
    if (
        fields.get("Identifier") != MACOS_BUNDLE_ID
        or fields.get("TeamIdentifier") != MACOS_TEAM_ID
    ):
        raise RuntimeError(
            "The macOS update is not signed for VODForge by Kryden Ventures."
        )
    _run_checked(
        ["/usr/bin/xcrun", "stapler", "validate", str(app_path)], runner=runner
    )
    _run_checked(
        [
            "/usr/sbin/spctl",
            "--assess",
            "--type",
            "execute",
            "--verbose=2",
            str(app_path),
        ],
        runner=runner,
    )


def prepare_macos_update(
    archive_path: Path,
    target_app: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> MacUpdatePlan:
    """Extract and verify a downloaded macOS update before the running app exits."""
    archive_path = Path(archive_path)
    target_app = Path(target_app)
    if archive_path.suffix.lower() != ".zip":
        raise RuntimeError("The macOS update is not a ZIP archive.")
    if (
        target_app.suffix.lower() != ".app"
        or not target_app.is_dir()
        or target_app.is_symlink()
    ):
        raise RuntimeError(
            "VODForge must be running from an installed application bundle to update itself."
        )
    if not os.access(target_app.parent, os.W_OK):
        raise RuntimeError(
            "VODForge cannot replace the installed app at its current location."
        )

    staging_root = archive_path.parent / f"{MACOS_STAGING_PREFIX}{uuid.uuid4().hex}"
    staging_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        _run_checked(
            ["/usr/bin/ditto", "-x", "-k", str(archive_path), str(staging_root)],
            runner=runner,
        )
        source_app = staging_root / "VODForge.app"
        verify_macos_app(source_app, runner=runner)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    return MacUpdatePlan(
        source_app=source_app, target_app=target_app, staging_root=staging_root
    )


def cleanup_stale_macos_updates(update_root: Path, *, keep: Path | None = None) -> None:
    """Remove only VODForge-created staging directories from previous update attempts."""
    update_root = Path(update_root)
    if not update_root.is_dir():
        return
    keep = keep.resolve() if keep is not None else None
    for child in update_root.iterdir():
        if (
            not child.name.startswith(MACOS_STAGING_PREFIX)
            or not child.is_dir()
            or child.is_symlink()
        ):
            continue
        if keep is not None and child.resolve() == keep:
            continue
        shutil.rmtree(child, ignore_errors=True)


def write_macos_swap_script(
    plan: MacUpdatePlan, *, repair: bool = False, telemetry_permitted: bool = False
) -> Path:
    """Write the detached, rollback-capable macOS app replacement script."""
    script_path = plan.staging_root / "install-update.sh"
    receipt_token = uuid.uuid4().hex
    script = textwrap.dedent(
        f"""\
        #!/bin/bash
        set -u
        parent_pid="$1"
        source_app="$2"
        target_app="$3"
        staging_root="$4"
        new_app="${{target_app}}.vodforge-update-new"
        old_app="${{target_app}}.vodforge-update-old"
        telemetry_receipt="${{staging_root%/*}}/handoff-{receipt_token}.json"
        umask 077
        stage="verifying"

        fail() {{
          message="$1"
          /usr/bin/logger -t VODForge "update failed: $message"
          if [[ ! -e "$target_app" && -e "$old_app" ]]; then /bin/mv "$old_app" "$target_app"; fi
          if [[ -d "$target_app" ]]; then
            path_digest=$(printf '%s' "$target_app/Contents/MacOS/VODForge" | /usr/bin/shasum -a 256)
            path_digest="${{path_digest%% *}}"
            printf '%s\n' '{{"status":"failed","stage":"'"$stage"'","executable_path_sha256":"'"$path_digest"'","telemetry_permitted":{str(telemetry_permitted).lower()}}}' > "$telemetry_receipt.tmp"
            /bin/mv "$telemetry_receipt.tmp" "$telemetry_receipt"
            /usr/bin/open --env "VODFORGE_UPDATE_RECEIPT=$telemetry_receipt" "$target_app"
          fi
          exit 1
        }}

        [[ "$source_app" == "$staging_root/VODForge.app" ]] || fail "unexpected source path"
        [[ "$target_app" == *.app ]] || fail "unexpected target path"
        [[ "$staging_root" == *"/{MACOS_STAGING_PREFIX}"* ]] || fail "unexpected staging path"
        stage="waiting_for_exit"
        for _ in $(/usr/bin/seq 1 240); do
          /bin/kill -0 "$parent_pid" 2>/dev/null || break
          /bin/sleep 0.5
        done
        /bin/kill -0 "$parent_pid" 2>/dev/null && fail "running app did not exit"

        [[ "$new_app" == "$target_app.vodforge-update-new" ]] || fail "unsafe new path"
        [[ "$old_app" == "$target_app.vodforge-update-old" ]] || fail "unsafe backup path"
        /bin/rm -rf -- "$new_app" "$old_app"
        stage="verifying"
        /usr/bin/ditto "$source_app" "$new_app" || fail "could not stage replacement"
        /usr/bin/codesign --verify --deep --strict "$new_app" || fail "signature verification failed"
        identity=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$new_app/Contents/Info.plist" 2>/dev/null) || fail "bundle identity missing"
        [[ "$identity" == "{MACOS_BUNDLE_ID}" ]] || fail "bundle identity mismatch"
        signing=$(/usr/bin/codesign -d --verbose=4 "$new_app" 2>&1) || fail "signing identity missing"
        /usr/bin/grep -Fqx 'Identifier={MACOS_BUNDLE_ID}' <<<"$signing" || fail "signed identifier mismatch"
        /usr/bin/grep -Fqx 'TeamIdentifier={MACOS_TEAM_ID}' <<<"$signing" || fail "team identifier mismatch"
        /usr/bin/xcrun stapler validate "$new_app" >/dev/null 2>&1 || fail "notarization ticket missing"
        /usr/sbin/spctl --assess --type execute "$new_app" >/dev/null 2>&1 || fail "Gatekeeper rejected update"

        stage="installing"
        /bin/mv "$target_app" "$old_app" || fail "could not preserve current app"
        if /bin/mv "$new_app" "$target_app"; then
          stage="relaunching"
          if /usr/bin/open --env "VODFORGE_UPDATE_RECEIPT=$telemetry_receipt" "$target_app"; then
            digest=$(/usr/bin/shasum -a 256 "$target_app/Contents/MacOS/VODForge")
            digest="${{digest%% *}}"
            printf '%s\n' '{{"status":"relaunched","stage":"relaunching","executable_sha256":"'"$digest"'","repair":{str(repair).lower()},"telemetry_permitted":{str(telemetry_permitted).lower()}}}' > "$telemetry_receipt.tmp"
            /bin/mv "$telemetry_receipt.tmp" "$telemetry_receipt"
            /bin/rm -rf -- "$old_app"
            /usr/bin/logger -t VODForge "update installed successfully"
            /bin/rm -rf -- "$staging_root"
            exit 0
          fi
          /bin/rm -rf -- "$target_app"
          /bin/mv "$old_app" "$target_app" 2>/dev/null || true
          fail "could not relaunch updated app"
        fi
        /bin/mv "$old_app" "$target_app" 2>/dev/null || true
        fail "could not activate replacement"
        """
    )
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o700)
    return script_path


def launch_macos_update(
    plan: MacUpdatePlan,
    *,
    parent_pid: int | None = None,
    repair: bool = False,
    telemetry_permitted: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> None:
    """Launch the verified macOS swapper; the caller must then exit."""
    verify_macos_app(plan.source_app, runner=runner)
    script_path = write_macos_swap_script(
        plan, repair=repair, telemetry_permitted=telemetry_permitted
    )
    process = popen(
        [
            "/bin/bash",
            str(script_path),
            str(os.getpid() if parent_pid is None else parent_pid),
            str(plan.source_app),
            str(plan.target_app),
            str(plan.staging_root),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    if process.poll() is not None and process.returncode:
        raise RuntimeError("The macOS update installer could not be started.")


def verify_windows_authenticode(
    installer_path: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Require VODForge's exact valid, timestamped Windows publisher signature."""
    installer_path = Path(installer_path)
    if installer_path.suffix.lower() != ".exe" or not installer_path.is_file():
        raise RuntimeError("The Windows update is not an installer executable.")
    literal_path = str(installer_path).replace("'", "''")
    command = (
        WINDOWS_POWERSHELL_MODULE_PATH
        + f"$signature=Get-AuthenticodeSignature -LiteralPath '{literal_path}';"
        "$result=[pscustomobject]@{Status=[string]$signature.Status;"
        "Subject=[string]$signature.SignerCertificate.Subject;"
        "Timestamp=[string]$signature.TimeStamperCertificate.Subject};"
        "$result | ConvertTo-Json -Compress"
    )
    result = _run_checked(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        runner=runner,
    )
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Windows could not read the update's publisher signature."
        ) from exc
    subject = str(payload.get("Subject") or "")
    if str(payload.get("Status") or "") != "Valid":
        raise RuntimeError("Windows rejected the update's Authenticode signature.")
    if (
        f'CN="{WINDOWS_PUBLISHER}"' not in subject
        or f'O="{WINDOWS_PUBLISHER}"' not in subject
    ):
        raise RuntimeError(
            "The Windows update was not published by Kryden Ventures, LLC."
        )
    if not str(payload.get("Timestamp") or "").strip():
        raise RuntimeError("The Windows update is missing its trusted timestamp.")


def windows_update_script(
    installer: Path,
    executable: Path,
    parent_pid: int,
    receipt: Path,
    ready: Path,
    *,
    data_dir: Path | None = None,
    repair: bool = False,
    telemetry_permitted: bool = False,
    window_bounds: tuple[int, int, int, int] | None = None,
) -> str:
    """Detached handoff: wait for graceful exit, install, then explicitly relaunch."""

    def literal(value: object) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    version = re.fullmatch(
        r"VODForge-Windows-Setup-v(\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?)\.exe",
        installer.name,
    )
    if version is None:
        raise ValueError(
            "The Windows installer name does not identify its release version."
        )
    expected_version = version.group(1)
    data_expression = (
        literal(data_dir)
        if data_dir is not None
        else "(Join-Path $env:LOCALAPPDATA 'VODForge')"
    )
    bounds_expression = (
        "@(" + ",".join(str(int(value)) for value in window_bounds) + ")"
        if window_bounds
        else "$null"
    )
    return RECOVERY_FUNCTIONS + textwrap.dedent(f"""\
        {WINDOWS_POWERSHELL_MODULE_PATH}
        $ErrorActionPreference = 'Stop'
        $installer = {literal(installer)}
        $executable = {literal(executable)}
        $receipt = {literal(receipt)}
        $ready = {literal(ready)}
        $windowBounds = {bounds_expression}
        $dataRoot = {data_expression}
        $backup = $receipt + '.data-backup'
        $directory = Split-Path -Parent $executable
        $expectedVersion = {literal(expected_version)}
        $repairRequested = ${str(repair).lower()}
        $setup = $null
        $manifest = $null
        do {{
        $stage = 'waiting_for_exit'
        $result = @{{ status = 'failed'; stage = $stage; executable = $executable; repair = $repairRequested; telemetry_permitted = ${str(telemetry_permitted).lower()} }}
        try {{
            $parent = Get-Process -Id {int(parent_pid)} -ErrorAction SilentlyContinue
            Set-Content -LiteralPath $ready -Value 'ready' -Encoding UTF8
            if ($parent -and !$parent.WaitForExit(120000)) {{ throw 'VODForge did not close. Close it normally and retry the update.' }}
            if ($setup -and !$setup.HasExited) {{ throw 'The previous installer is still running. Finish or close it before repair.' }}
            if ($null -ne $manifest) {{
                $stage = 'checking_data'
                Confirm-VODForgeData $dataRoot $manifest
            }}
            if ($repairRequested) {{
                $stage = 'downloading_repair'
                $fresh = Get-VODForgeRepairInstaller (Split-Path -Parent $installer)
                $installer = $fresh.Path
                $expectedVersion = $fresh.Version
            }}
            $stage = 'backing_up'
            if ($null -eq $manifest) {{ $manifest = Save-VODForgeData $dataRoot $backup }}
            $result.data_backup = $backup
            $stage = 'verifying'
            $signature = Get-AuthenticodeSignature -LiteralPath $installer
            if ($signature.Status -ne 'Valid' -or !$signature.TimeStamperCertificate -or !$signature.SignerCertificate.Subject.Contains('CN="Kryden Ventures, LLC"') -or !$signature.SignerCertificate.Subject.Contains('O="Kryden Ventures, LLC"')) {{ throw 'Installer signature verification failed. Download a fresh installer from the official release.' }}
            $directory = Split-Path -Parent $executable
            $arguments = @('/SP-', '/SILENT', '/NORESTART', '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/VODFORGEHANDOFF=1', ('/DIR="' + $directory + '"'), ('/LOG="' + $receipt + '.install.log"'))
            $stage = 'installing'
            $setup = Start-Process -FilePath $installer -ArgumentList $arguments -PassThru
            if (!$setup.WaitForExit(900000)) {{ throw 'Installer is still running. Finish or close the installer before retrying.' }}
            $setup.Refresh()
            $result.installer_exit_code = $setup.ExitCode
            if ($setup.ExitCode -ne 0) {{ throw ('Installation did not complete (exit code ' + $setup.ExitCode + '). Run the downloaded installer manually; see the installation log.') }}
            $stage = 'verifying_install'
            if (!(Test-Path -LiteralPath $executable -PathType Leaf)) {{ throw 'Installed application is missing. Run the downloaded installer manually.' }}
            $installedVersion = (Get-Item -LiteralPath $executable).VersionInfo.ProductVersion
            if ($installedVersion -ne $expectedVersion) {{ throw ('Installed version does not match the update: ' + $installedVersion + '. Run the installer manually.') }}
            $stage = 'checking_data'
            Confirm-VODForgeData $dataRoot $manifest
            $result.data_preserved_before_relaunch = $true
            $result.installed_version = $installedVersion
            $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
            $stage = 'relaunching'
            $env:VODFORGE_UPDATE_RECEIPT = $receipt
            $app = Start-Process -FilePath $executable -WorkingDirectory $directory -PassThru
            if ($app.WaitForExit(3000)) {{ throw 'VODForge exited immediately after installation. Open it from the Start menu; see the update log if it fails again.' }}
            $result.status = 'relaunched'
            $result.pid = $app.Id
            $result.executable = $executable
            $result.executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
        }} catch {{
            $result.error = $_.Exception.Message
            if ($null -ne $manifest) {{
                try {{ Confirm-VODForgeData $dataRoot $manifest }}
                catch {{ $stage = 'checking_data'; $result.error += "`r`n" + $_.Exception.Message }}
            }}
            $result.stage = $stage
            $result | ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8
            $choice = Show-VODForgeRecovery $stage ($result.error + "`r`nUpdate log: " + $receipt) $directory $backup
            $repairRequested = $choice -eq 'repair'
            if ($repairRequested) {{
                Copy-Item -LiteralPath $receipt -Destination ($receipt + '.' + [guid]::NewGuid().ToString('N') + '.failed.json')
            }}
        }} finally {{
            $result.stage = $stage
            $result | ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8
        }}
        }} while ($result.status -ne 'relaunched' -and $repairRequested)
        if ($result.status -ne 'relaunched') {{ exit 1 }}
        """)


def launch_windows_update(
    installer: Path,
    *,
    executable: Path | None = None,
    parent_pid: int | None = None,
    repair: bool = False,
    telemetry_permitted: bool = False,
    window_bounds: tuple[int, int, int, int] | None = None,
    popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> Path:
    """Start a hidden helper and confirm readiness before the UI closes."""
    import time

    installer = installer.resolve()
    target = Path(sys.executable) if executable is None else executable
    target = target.resolve()
    if target.name.lower() != "vodforge.exe" or not target.is_file():
        raise RuntimeError("Run the installed VODForge app before updating.")
    if installer.suffix.lower() != ".exe" or not installer.is_file():
        raise RuntimeError(
            "The verified installer is missing. Download the update again."
        )
    if not os.access(target.parent, os.W_OK):
        raise RuntimeError(
            "The app folder is not writable. Close VODForge and run the installer manually."
        )
    token = uuid.uuid4().hex
    receipt = installer.parent / f"handoff-{token}.json"
    ready = installer.parent / f"handoff-{token}.ready"
    script = windows_update_script(
        installer,
        target,
        os.getpid() if parent_pid is None else parent_pid,
        receipt,
        ready,
        window_bounds=window_bounds,
        repair=repair,
        telemetry_permitted=telemetry_permitted,
    )
    script_path = installer.parent / f"handoff-{token}.ps1"
    # A file avoids Windows' 32K command-line ceiling as recovery grows.
    with script_path.open("x", encoding="utf-8-sig") as handle:
        handle.write(script)
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    process = popen(
        [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if ready.is_file():
            ready.unlink(missing_ok=True)
            return receipt
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
    raise RuntimeError(
        "The update helper could not start. VODForge remains open; run the downloaded installer manually."
    )


def confirmed_update_telemetry_receipt(
    path: Path, executable: Path
) -> tuple[str, bool, str, str] | None:
    """Read a bounded helper receipt; current executable must match installed bytes.

    Return an opaque operation token and repair flag only, never paths or errors.
    The caller supplies the helper's inherited receipt path, not a broad log scan.
    """
    match = re.fullmatch(
        r"handoff-([0-9a-f]{32})(?:\.[0-9a-f]{32}\.failed)?\.json", path.name
    )
    try:
        if match is None or path.is_symlink() or path.stat().st_size > 16384:
            return None
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        from .telemetry_features import DIMENSION_CHOICES

        stage = value.get("stage", "unknown")
        if not isinstance(stage, str) or stage not in DIMENSION_CHOICES["update_stage"]:
            stage = "unknown"
        if value.get("telemetry_permitted") is not True or value.get("status") not in {
            "relaunched",
            "failed",
        }:
            return None
        if value["status"] == "failed":
            path_digest = hashlib.sha256(str(executable.resolve()).encode()).hexdigest()
            same_target = value.get("executable_path_sha256") == path_digest or (
                isinstance(value.get("executable"), str)
                and Path(value["executable"]).resolve() == executable.resolve()
            )
            return (match.group(1), False, "failed", stage) if same_target else None
        if value.get("pid") is not None and value["pid"] != os.getpid():
            return None
        with executable.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if str(value.get("executable_sha256", "")).lower() != digest:
            return None
        return match.group(1), value.get("repair") is True, "relaunched", stage
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def pending_update_telemetry_receipts(update_root: Path, executable: Path):
    """Bounded recovery observations for the next app open, including Later.

    Companion markers mean queued in the existing telemetry outbox, not delivered.
    Original helper receipts remain untouched for support and update verification.
    """
    import time

    try:
        candidates = sorted(
            update_root.glob("*/handoff-*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:64]
    except OSError:
        return
    for path in candidates:
        try:
            if time.time() - path.stat().st_mtime > 30 * 86400:
                continue
            receipt = confirmed_update_telemetry_receipt(path, executable)
            if (
                receipt is not None
                and not path.with_suffix(
                    "." + receipt[2] + ".telemetry-queued"
                ).exists()
                and not path.with_suffix(
                    "." + receipt[2] + ".telemetry-discarded"
                ).exists()
            ):
                yield path, receipt
        except OSError:
            continue
