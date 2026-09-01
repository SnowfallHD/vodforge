from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def _release_notes_module():
    path = ROOT / ".github" / "scripts" / "render_release_notes.py"
    spec = spec_from_file_location("render_release_notes", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_workflow_signs_before_packaging_windows_portable_archive():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    app_sign = workflow.index("name: Sign packaged Windows application")
    installer_build = workflow.index("name: Build Windows installer")
    installer_sign = workflow.index("name: Sign Windows installer")
    portable_package = workflow.index("Compress-Archive")

    assert app_sign < installer_build < installer_sign < portable_package
    assert "azure/login@v3" in workflow
    assert "azure/artifact-signing-action@v2" in workflow
    assert "verify_windows_signatures.ps1" in workflow


def test_release_workflow_keeps_macos_artifacts_explicitly_review_only():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "vodforge-macos-${{ matrix.architecture }}-unsigned" in workflow
    assert 'VODFORGE_UNSIGNED_REVIEW: "1"' in workflow
    assert "render_release_notes.py" in workflow
    assert "--draft" in workflow


def test_macos_dependency_install_recovers_only_when_every_formula_is_present():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "if ! brew install python@3.13 python-tk@3.13 ffmpeg deno; then" in workflow
    assert 'brew list --versions "$formula"' in workflow
    assert "brew --prefix python@3.13" in workflow


def test_every_full_repository_test_runner_installs_harness_dependencies():
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    tests_workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )

    required_install = (
        "pip install -r requirements-dev.txt -r engineering-quality/requirements.txt"
    )
    assert required_install in macos_build
    assert required_install in tests_workflow


def test_release_builds_pin_yt_dlp_with_matching_ejs_scripts():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    app_source = (ROOT / "yt_downloader" / "app.py").read_text(encoding="utf-8")

    assert "yt-dlp[default]==2026.8.19" in requirements
    assert not any(line.startswith("yt-dlp>=") for line in requirements)
    assert 'PINNED_YTDLP_VERSION = "2026.8.19"' in app_source
    assert 'PINNED_YTDLP_EJS_VERSION = "0.8.0"' in app_source


def test_macos_release_script_requires_accepted_notarization_and_stapling():
    script = (ROOT / "sign_and_notarize_macos.sh").read_text(encoding="utf-8")

    assert 'notary_status" != "Accepted"' in script
    assert "stapler staple" in script
    assert "stapler validate" in script
    assert "spctl --assess" in script


def test_packaged_apps_receive_the_requested_operating_system_version_metadata():
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    windows_build = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")

    assert (
        "for version_key in CFBundleShortVersionString CFBundleVersion" in macos_build
    )
    assert "Set :$version_key $bundle_version" in macos_build
    assert "Add :$version_key string $bundle_version" in macos_build
    assert "StringStruct('FileVersion', '$displayVersion')" in windows_build
    assert "StringStruct('ProductVersion', '$displayVersion')" in windows_build
    assert '"--version-file", $versionResourceFile' in windows_build


def test_local_macos_bundle_is_resigned_after_final_metadata_mutation():
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")

    version_mutation = macos_build.index("Set :$version_key $bundle_version")
    local_signing = macos_build.index(
        '/usr/bin/codesign --force --deep --sign - "dist/VODForge.app"'
    )
    strict_verification = macos_build.index(
        '/usr/bin/codesign --verify --deep --strict "dist/VODForge.app"'
    )
    runtime_smoke = macos_build.index('"$app_binary" --runtime-smoke')
    assert version_mutation < local_signing < strict_verification < runtime_smoke


def test_lazy_ytdlp_runtime_is_explicitly_collected_for_both_packagers():
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    windows_build = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    app_source = (ROOT / "yt_downloader" / "app.py").read_text(encoding="utf-8")

    assert "--collect-all yt_dlp" in macos_build
    assert "--collect-all yt_dlp" in windows_build
    assert '"$app_binary" --runtime-smoke' in macos_build
    assert (
        'Start-Process -FilePath $appBinary -ArgumentList "--runtime-smoke" -Wait -PassThru'
        in windows_build
    )
    assert 'resources_module.files("yt_dlp_ejs.yt.solver")' in app_source
    assert 'YTDLP_EJS_SOLVER_RESOURCES = ("core.min.js", "lib.min.js")' in app_source


def test_packaged_apps_and_windows_installer_use_vodforge_icon_assets():
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    windows_build = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "installer_windows.iss").read_text(encoding="utf-8")

    assert '--icon "$icon_file"' in macos_build
    assert "Print :CFBundleIconFile" in macos_build
    assert 'cmp -s "$icon_file" "$bundle_icon"' in macos_build
    assert '"--icon", $iconFile' in windows_build
    assert "assets/icons/lucide" in macos_build
    assert "assets/icons/lucide" in windows_build
    assert "SetupIconFile=assets\\VODForge.ico" in installer
    assert (ROOT / "assets" / "VODForge.png").is_file()
    assert (ROOT / "assets" / "VODForge.ico").is_file()
    assert (ROOT / "assets" / "VODForge.icns").is_file()
    macos_icon_source = ROOT / "assets" / "VODForge-macos.png"
    assert macos_icon_source.is_file()
    with Image.open(macos_icon_source) as icon:
        assert icon.size == (1024, 1024)
        bounds = icon.getchannel("A").getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    assert min(left, top) >= 48
    assert max(right, bottom) <= 976
    assert (ROOT / "assets" / "icons" / "lucide" / "settings.png").is_file()
    assert (ROOT / "assets" / "icons" / "lucide" / "send-filled.png").is_file()
    assert (ROOT / "assets" / "icons" / "lucide" / "MATERIAL_LICENSE").is_file()
    assert (ROOT / "assets" / "icons" / "lucide" / "LICENSE").is_file()
    for icon_name in (
        "activity",
        "folder",
        "library",
        "link-2",
        "settings",
        "sliders-horizontal",
        "send-filled",
    ):
        with Image.open(
            ROOT / "assets" / "icons" / "lucide" / f"{icon_name}.png"
        ) as icon:
            assert icon.size == (512, 512)
            assert "A" in icon.getbands()
        assert (ROOT / "assets" / "icons" / "lucide" / f"{icon_name}-20.svg").is_file()
        with Image.open(
            ROOT / "assets" / "icons" / "lucide" / f"{icon_name}-20.png"
        ) as icon:
            assert icon.size == (20, 20)
            assert "A" in icon.getbands()
    for vector_variant in (
        "activity-20-accent.svg",
        "activity-20-muted.svg",
        "folder-20-muted.svg",
        "library-20-accent.svg",
        "library-20-muted.svg",
        "link-2-20-muted.svg",
        "send-filled-20-white.svg",
        "settings-20-muted.svg",
        "settings-20-text.svg",
        "sliders-horizontal-20-muted.svg",
    ):
        assert (ROOT / "assets" / "icons" / "lucide" / vector_variant).is_file()


def test_release_finalizer_replaces_unsigned_reviews_and_regenerates_checksums():
    script = (ROOT / "finalize_macos_release.sh").read_text(encoding="utf-8")

    assert "Release finalization must run from main" in script
    assert "unsigned-review.zip" in script
    assert "sign_and_notarize_macos.sh" in script
    assert "SHA256SUMS.txt" in script
    assert "release delete-asset" in script
    assert 'release edit "$tag"' in script


def test_release_notes_lead_with_clear_user_facing_platform_choices():
    notes = _release_notes_module().render_release_notes("1.2.3")

    newer = notes.index("### Newer Macs — Apple silicon")
    older = notes.index("### Older Macs — Intel-based")
    windows = notes.index("### Windows")
    assert newer < older < windows
    assert "late 2020 and newer" in notes
    assert "2020 and earlier" in notes
    assert "About This Mac" in notes
    assert "VODForge-macOS-arm64-v1.2.3.zip" in notes
    assert "VODForge-macOS-x64-v1.2.3.zip" in notes
    assert "VODForge-Windows-Setup-v1.2.3.exe" in notes
    assert "**MP4 video** or **MP3 audio**" in notes
    assert "1080p and 4K sources" in notes
    assert "original YouTube source and final VODForge output details" in notes
    assert "partial file" in notes
    assert "seen → clicked → joined" in notes
    assert "stops its exact active run" in notes
    assert "Downloaded media and folders remain untouched" in notes
    assert "configure only the next run" in notes
    assert "AAC or MP3 audio inside the MP4 container" in notes


def test_draft_release_notes_keep_the_release_team_safety_gate():
    notes = _release_notes_module().render_release_notes("1.2.3", draft=True)

    assert "Release-team draft" in notes
    assert "Do not publish" in notes
    assert "notarized" in notes
