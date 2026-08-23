from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).resolve().parents[1]


def _release_notes_module():
    path = ROOT / ".github" / "scripts" / "render_release_notes.py"
    spec = spec_from_file_location("render_release_notes", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_workflow_signs_before_packaging_windows_portable_archive():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    app_sign = workflow.index("name: Sign packaged Windows application")
    installer_build = workflow.index("name: Build Windows installer")
    installer_sign = workflow.index("name: Sign Windows installer")
    portable_package = workflow.index("Compress-Archive")

    assert app_sign < installer_build < installer_sign < portable_package
    assert "azure/login@v3" in workflow
    assert "azure/artifact-signing-action@v2" in workflow
    assert "verify_windows_signatures.ps1" in workflow


def test_release_workflow_keeps_macos_artifacts_explicitly_review_only():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "vodforge-macos-${{ matrix.architecture }}-unsigned" in workflow
    assert 'VODFORGE_UNSIGNED_REVIEW: "1"' in workflow
    assert "render_release_notes.py" in workflow
    assert "--draft" in workflow


def test_macos_dependency_install_recovers_only_when_every_formula_is_present():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "if ! brew install python@3.13 python-tk@3.13 ffmpeg deno; then" in workflow
    assert 'brew list --versions "$formula"' in workflow
    assert 'brew --prefix python@3.13' in workflow


def test_macos_release_script_requires_accepted_notarization_and_stapling():
    script = (ROOT / "sign_and_notarize_macos.sh").read_text()

    assert 'notary_status" != "Accepted"' in script
    assert "stapler staple" in script
    assert "stapler validate" in script
    assert "spctl --assess" in script


def test_packaged_apps_receive_the_requested_operating_system_version_metadata():
    macos_build = (ROOT / "build_macos.sh").read_text()
    windows_build = (ROOT / "build_windows.ps1").read_text()

    assert "for version_key in CFBundleShortVersionString CFBundleVersion" in macos_build
    assert 'Set :$version_key $bundle_version' in macos_build
    assert 'Add :$version_key string $bundle_version' in macos_build
    assert 'StringStruct(\'FileVersion\', \'$displayVersion\')' in windows_build
    assert 'StringStruct(\'ProductVersion\', \'$displayVersion\')' in windows_build
    assert '"--version-file", $versionResourceFile' in windows_build


def test_packaged_apps_and_windows_installer_use_vodforge_icon_assets():
    macos_build = (ROOT / "build_macos.sh").read_text()
    windows_build = (ROOT / "build_windows.ps1").read_text()
    installer = (ROOT / "installer_windows.iss").read_text()

    assert '--icon "$icon_file"' in macos_build
    assert '"--icon", $iconFile' in windows_build
    assert 'assets/icons/lucide' in macos_build
    assert 'assets/icons/lucide' in windows_build
    assert "SetupIconFile=assets\\VODForge.ico" in installer
    assert (ROOT / "assets" / "VODForge.png").is_file()
    assert (ROOT / "assets" / "VODForge.ico").is_file()
    assert (ROOT / "assets" / "VODForge.icns").is_file()
    assert (ROOT / "assets" / "icons" / "lucide" / "settings.png").is_file()
    assert (ROOT / "assets" / "icons" / "lucide" / "LICENSE").is_file()


def test_release_finalizer_replaces_unsigned_reviews_and_regenerates_checksums():
    script = (ROOT / "finalize_macos_release.sh").read_text()

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
    assert "keeps **Download MP4** visible" in notes
    assert "failing NAS or shell provider cannot close VODForge" in notes
    assert "real release version instead of `0.0.0`" in notes


def test_draft_release_notes_keep_the_release_team_safety_gate():
    notes = _release_notes_module().render_release_notes("1.2.3", draft=True)

    assert "Release-team draft" in notes
    assert "Do not publish" in notes
    assert "notarized" in notes
