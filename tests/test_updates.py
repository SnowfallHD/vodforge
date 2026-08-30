from __future__ import annotations

import hashlib
import io
import json
import plistlib
import subprocess
from pathlib import Path

import pytest

from yt_downloader.updates import (
    ReleaseAsset,
    ReleaseInfo,
    MacUpdatePlan,
    download_verified_update,
    is_newer_release,
    launch_macos_update,
    parse_release_payload,
    parse_sha256sums,
    prepare_macos_update,
    release_asset_for_platform,
    running_macos_app,
    semantic_version_key,
    verify_macos_app,
    verify_windows_authenticode,
    write_macos_swap_script,
)
from yt_downloader.version import DEFAULT_VERSION, read_app_version


def _release_download_url(tag_name: str, asset_name: str) -> str:
    return f"https://github.com/SnowfallHD/vodforge/releases/download/{tag_name}/{asset_name}"


def test_semantic_versions_treat_stable_release_as_newer_than_dev_build():
    assert semantic_version_key("v1.2.3") > semantic_version_key("1.2.3-dev")
    assert is_newer_release("0.1.0-dev", "v0.1.0")
    assert not is_newer_release("0.2.0", "v0.1.9")


def test_release_payload_accepts_only_public_stable_github_release():
    release = parse_release_payload(
        {
            "tag_name": "v1.2.3",
            "name": "VODForge 1.2.3",
            "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
            "body": "Release notes",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "VODForge-Windows-Setup-v1.2.3.exe",
                    "browser_download_url": "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/VODForge-Windows-Setup-v1.2.3.exe",
                    "size": 123,
                }
            ],
        }
    )

    assert release.version == "1.2.3"
    assert release.tag_name == "v1.2.3"
    assert release.assets[0].size == 123


def test_release_payload_rejects_asset_outside_the_canonical_release_path():
    with pytest.raises(ValueError, match="invalid release download URL"):
        parse_release_payload(
            {
                "tag_name": "v1.2.3",
                "name": "VODForge 1.2.3",
                "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
                "body": "Release notes",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "VODForge-Windows-Setup-v1.2.3.exe",
                        "browser_download_url": (
                            "https://github.com/other/repository/releases/download/v1.2.3/"
                            "VODForge-Windows-Setup-v1.2.3.exe"
                        ),
                        "size": 123,
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"tag_name": "v1.2.3", "html_url": "https://evil.example/release", "draft": False, "prerelease": False},
        {"tag_name": "latest", "html_url": "https://github.com/SnowfallHD/vodforge/releases/latest", "draft": False, "prerelease": False},
        {"tag_name": "v1.2.3-beta.1", "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3-beta.1", "draft": False, "prerelease": False},
        {"tag_name": "v1.2.3", "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3", "draft": True, "prerelease": False},
    ],
)
def test_release_payload_rejects_untrusted_or_nonstable_data(payload: dict[str, object]):
    with pytest.raises(ValueError):
        parse_release_payload(payload)


def test_packaged_version_file_is_validated(tmp_path: Path):
    version_file = tmp_path / "VODFORGE_VERSION"
    version_file.write_text("1.4.2\n", encoding="utf-8")
    assert read_app_version(version_file) == "1.4.2"

    version_file.write_text("not-a-version", encoding="utf-8")
    assert read_app_version(version_file) == DEFAULT_VERSION


def test_platform_asset_selection_is_exact():
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset("VODForge-Windows-Setup-v1.2.3.exe", "https://github.com/example/windows", 10),
            ReleaseAsset("VODForge-macOS-arm64-v1.2.3.zip", "https://github.com/example/mac-arm", 10),
            ReleaseAsset("VODForge-macOS-x64-v1.2.3.zip", "https://github.com/example/mac-x64", 10),
        ),
    )

    assert release_asset_for_platform(release, platform_name="win32", machine="AMD64").name.endswith(".exe")
    assert release_asset_for_platform(release, platform_name="darwin", machine="arm64").name == "VODForge-macOS-arm64-v1.2.3.zip"
    assert release_asset_for_platform(release, platform_name="darwin", machine="x86_64").name == "VODForge-macOS-x64-v1.2.3.zip"
    assert release_asset_for_platform(release, platform_name="linux", machine="x86_64") is None


def test_verified_update_requires_matching_checksum(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    update_bytes = b"verified installer bytes"
    digest = hashlib.sha256(update_bytes).hexdigest()
    asset_name = "VODForge-Windows-Setup-v1.2.3.exe"
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset(asset_name, _release_download_url("v1.2.3", asset_name), len(update_bytes)),
            ReleaseAsset(
                "SHA256SUMS.txt",
                _release_download_url("v1.2.3", "SHA256SUMS.txt"),
                80,
            ),
        ),
    )

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, timeout=0):
        assert timeout == 60
        if request.full_url.endswith("SHA256SUMS.txt"):
            return FakeResponse(f"{digest}  {asset_name}\n".encode())
        return FakeResponse(update_bytes)

    monkeypatch.setattr("yt_downloader.updates.urllib.request.urlopen", fake_urlopen)
    output = download_verified_update(release, tmp_path, platform_name="win32", machine="AMD64")

    assert output.read_bytes() == update_bytes
    assert parse_sha256sums(f"{digest}  {asset_name}\n") == {asset_name: digest}


def test_verified_update_deletes_tampered_partial_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    asset_name = "VODForge-Windows-Setup-v1.2.3.exe"
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset(asset_name, _release_download_url("v1.2.3", asset_name), 8),
            ReleaseAsset(
                "SHA256SUMS.txt",
                _release_download_url("v1.2.3", "SHA256SUMS.txt"),
                80,
            ),
        ),
    )

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    responses = iter([FakeResponse(f"{'0' * 64}  {asset_name}\n".encode()), FakeResponse(b"tampered")])
    monkeypatch.setattr("yt_downloader.updates.urllib.request.urlopen", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(RuntimeError, match="SHA-256 verification"):
        download_verified_update(release, tmp_path, platform_name="win32", machine="AMD64")

    assert not (tmp_path / asset_name).exists()
    assert not (tmp_path / f"{asset_name}.part").exists()


@pytest.mark.parametrize(
    ("url_role", "untrusted_url"),
    [
        ("checksum", "file:///private/etc/hosts"),
        ("checksum", "https://evil.example/SHA256SUMS.txt"),
        (
            "checksum",
            "https://github.com/other/repository/releases/download/v1.2.3/SHA256SUMS.txt",
        ),
        (
            "checksum",
            "https://github.com.evil.example/SnowfallHD/vodforge/releases/download/"
            "v1.2.3/SHA256SUMS.txt",
        ),
        (
            "payload",
            "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/other.exe",
        ),
        (
            "payload",
            "https://github.com/SnowfallHD/vodforge/releases/download/v9.9.9/"
            "VODForge-Windows-Setup-v1.2.3.exe",
        ),
        (
            "payload",
            "https://token@github.com/SnowfallHD/vodforge/releases/download/v1.2.3/"
            "VODForge-Windows-Setup-v1.2.3.exe",
        ),
        (
            "payload",
            "https://github.com:443/SnowfallHD/vodforge/releases/download/v1.2.3/"
            "VODForge-Windows-Setup-v1.2.3.exe",
        ),
        (
            "payload",
            "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/"
            "VODForge-Windows-Setup-v1.2.3.exe?token=secret",
        ),
        (
            "payload",
            "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/"
            "VODForge-Windows-Setup-v1.2.3.exe#unexpected",
        ),
        (
            "payload",
            "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/"
            "VODForge-Windows-Setup-v1.2.3.exe;token=secret",
        ),
    ],
)
def test_verified_update_revalidates_asset_urls_before_network_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    url_role: str,
    untrusted_url: str,
):
    asset_name = "VODForge-Windows-Setup-v1.2.3.exe"
    payload_url = _release_download_url("v1.2.3", asset_name)
    checksum_url = _release_download_url("v1.2.3", "SHA256SUMS.txt")
    if url_role == "payload":
        payload_url = untrusted_url
    else:
        checksum_url = untrusted_url
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset(asset_name, payload_url, 8),
            ReleaseAsset("SHA256SUMS.txt", checksum_url, 80),
        ),
    )
    network_calls: list[str] = []

    def unexpected_urlopen(request, **_kwargs):
        network_calls.append(request.full_url)
        raise AssertionError("untrusted release data reached the network boundary")

    monkeypatch.setattr("yt_downloader.updates.urllib.request.urlopen", unexpected_urlopen)

    destination = tmp_path / "updates"
    with pytest.raises(RuntimeError, match="invalid download URL"):
        download_verified_update(release, destination, platform_name="win32", machine="AMD64")

    assert network_calls == []
    assert not destination.exists()


def test_verified_update_rejects_incoherent_release_version_before_network_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset_name = "VODForge-Windows-Setup-v1.2.3.exe"
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v9.9.9",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v9.9.9",
        notes="",
        assets=(
            ReleaseAsset(asset_name, _release_download_url("v9.9.9", asset_name), 8),
            ReleaseAsset(
                "SHA256SUMS.txt",
                _release_download_url("v9.9.9", "SHA256SUMS.txt"),
                80,
            ),
        ),
    )
    network_calls: list[str] = []

    def unexpected_urlopen(request, **_kwargs):
        network_calls.append(request.full_url)
        raise AssertionError("incoherent release identity reached the network boundary")

    monkeypatch.setattr("yt_downloader.updates.urllib.request.urlopen", unexpected_urlopen)
    destination = tmp_path / "updates"

    with pytest.raises(RuntimeError, match="invalid version metadata"):
        download_verified_update(release, destination, platform_name="win32", machine="AMD64")

    assert network_calls == []
    assert not destination.exists()


def _write_mac_app(app_path: Path, *, bundle_id: str = "com.snowfallhd.vodforge") -> None:
    contents = app_path / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump({"CFBundleIdentifier": bundle_id}, handle)


def _mac_verification_runner(*, team_id: str = "76G5W4954G"):
    def run(command, **_kwargs):
        stderr = ""
        if command[:3] == ["/usr/bin/codesign", "-d", "--verbose=4"]:
            stderr = f"Identifier=com.snowfallhd.vodforge\nTeamIdentifier={team_id}\n"
        return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)

    return run


def test_running_macos_app_finds_only_enclosing_bundle():
    executable = Path("/Applications/VODForge.app/Contents/MacOS/VODForge")
    assert running_macos_app(executable) == Path("/Applications/VODForge.app")
    assert running_macos_app(Path("/usr/local/bin/vodforge")) is None


def test_macos_update_requires_exact_bundle_and_team_identity(tmp_path: Path):
    app_path = tmp_path / "VODForge.app"
    _write_mac_app(app_path)
    verify_macos_app(app_path, runner=_mac_verification_runner())

    with pytest.raises(RuntimeError, match="Kryden Ventures"):
        verify_macos_app(app_path, runner=_mac_verification_runner(team_id="WRONGTEAM"))

    _write_mac_app(app_path, bundle_id="com.example.impostor")
    with pytest.raises(RuntimeError, match="wrong application identifier"):
        verify_macos_app(app_path, runner=_mac_verification_runner())


def test_prepare_macos_update_extracts_direct_bundle_and_verifies_it(tmp_path: Path):
    archive = tmp_path / "VODForge-macOS-arm64-v1.2.3.zip"
    archive.write_bytes(b"release archive")
    target = tmp_path / "Applications" / "VODForge.app"
    _write_mac_app(target)

    def runner(command, **kwargs):
        if command[:4] == ["/usr/bin/ditto", "-x", "-k", str(archive)]:
            _write_mac_app(Path(command[-1]) / "VODForge.app")
        return _mac_verification_runner()(command, **kwargs)

    plan = prepare_macos_update(archive, target, runner=runner)
    assert plan.source_app == plan.staging_root / "VODForge.app"
    assert plan.target_app == target
    assert plan.staging_root.name.startswith("staged-")


def test_macos_swap_script_reverifies_and_rolls_back(tmp_path: Path):
    staging = tmp_path / "updates" / "v1.2.3" / "staged-test"
    source = staging / "VODForge.app"
    target = tmp_path / "Applications" / "VODForge.app"
    _write_mac_app(source)
    _write_mac_app(target)
    script = write_macos_swap_script(MacUpdatePlan(source, target, staging)).read_text()

    assert "codesign --verify --deep --strict" in script
    assert "TeamIdentifier=76G5W4954G" in script
    assert "stapler validate" in script
    assert "spctl --assess" in script
    assert 'mv "$old_app" "$target_app"' in script


def test_launch_macos_update_uses_detached_argument_safe_handoff(tmp_path: Path):
    staging = tmp_path / "updates" / "v1.2.3" / "staged-test"
    source = staging / "VODForge.app"
    target = tmp_path / "Applications" / "VODForge.app"
    _write_mac_app(source)
    _write_mac_app(target)
    plan = MacUpdatePlan(source, target, staging)
    calls = []

    class Process:
        returncode = None

        def poll(self):
            return None

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    launch_macos_update(plan, parent_pid=123, runner=_mac_verification_runner(), popen=popen)
    command, kwargs = calls[0]
    assert command[0] == "/bin/bash"
    assert command[2:] == ["123", str(source), str(target), str(staging)]
    assert kwargs["start_new_session"] is True
    assert kwargs["close_fds"] is True


def test_windows_update_requires_valid_owned_timestamped_signature(tmp_path: Path):
    installer = tmp_path / "VODForge-Windows-Setup-v1.2.3.exe"
    installer.write_bytes(b"signed installer")

    def valid_runner(command, **_kwargs):
        payload = (
            '{"Status":"Valid","Subject":"CN=\\"Kryden Ventures, LLC\\", '
            'O=\\"Kryden Ventures, LLC\\", C=US","Timestamp":"CN=Microsoft Time Stamp"}'
        )
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    verify_windows_authenticode(installer, runner=valid_runner)

    def unsigned_runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"Status":"NotSigned","Subject":"","Timestamp":""}',
            stderr="",
        )

    with pytest.raises(RuntimeError, match="Authenticode"):
        verify_windows_authenticode(installer, runner=unsigned_runner)

    def wrong_publisher_runner(command, **_kwargs):
        payload = json.dumps(
            {
                "Status": "Valid",
                "Subject": 'CN="Example Corp", O="Example Corp", C=US',
                "Timestamp": "CN=Microsoft Time Stamp",
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    with pytest.raises(RuntimeError, match="Kryden Ventures"):
        verify_windows_authenticode(installer, runner=wrong_publisher_runner)
