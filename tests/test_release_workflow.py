import re
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def _release_notes_module():
    path = ROOT / ".github" / "scripts" / "render_release_notes.py"
    spec = spec_from_file_location("render_release_notes", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _macos_package_options(tmp_path):
    """The real PyInstaller options both Mac builds use, with stand-in binaries."""
    from scripts.macos_package_contents import VERSION_FILES, pyinstaller_options

    version_dir = tmp_path / "version"
    version_dir.mkdir()
    for name in VERSION_FILES:
        (version_dir / name).write_text("fixture")
    binaries = []
    for name in ("ffmpeg", "ffprobe", "deno", "libvodforge_fullscreen.dylib"):
        path = tmp_path / name
        path.write_bytes(b"fixture")
        binaries.append(path)
    return pyinstaller_options(
        version_dir=version_dir, native_helper=binaries[-1], helpers=binaries[:3]
    )


def _option_values(options, flag):
    return [options[i + 1] for i, value in enumerate(options) if value == flag]


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

    assert 'VODFORGE_UNSIGNED_REVIEW: "1"' in workflow
    assert "render_release_notes.py" in workflow
    assert "--draft" in workflow


def _uploaded_artifacts(job):
    return [
        step["with"]["name"]
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]


def test_draft_receives_only_the_universal_mac_app():
    import yaml

    jobs = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())["jobs"]
    draft_download = next(
        step
        for step in jobs["draft"]["steps"]
        if "download-artifact" in str(step.get("uses"))
    )
    pattern = draft_download["with"]["pattern"]
    assert pattern == "vodforge-*"
    # Per-architecture apps and helpers stay workflow artifacts for QA.
    thin = _uploaded_artifacts(jobs["macos"])
    assert thin and not any(name.startswith("vodforge-") for name in thin)
    universal = _uploaded_artifacts(jobs["macos-universal"])
    assert [n for n in universal if n.startswith("vodforge-")] == [
        "vodforge-macos-universal2-unsigned"
    ]
    assert jobs["macos-universal"]["needs"] == "macos"
    assert set(jobs["draft"]["needs"]) == {"windows", "macos-universal"}


def test_universal_app_is_smoke_tested_on_both_architectures_before_packaging():
    import yaml

    jobs = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())["jobs"]
    steps = [step.get("name", "") for step in jobs["macos-universal"]["steps"]]
    runs = "\n".join(step.get("run", "") for step in jobs["macos-universal"]["steps"])
    assert '"$app" --runtime-smoke' in runs
    assert 'arch -x86_64 "$app" --runtime-smoke' in runs
    assert steps.index("Smoke-test both architectures") < steps.index(
        "Package the universal review application"
    )
    assert (
        "VODForge-macOS-universal2-v${{ inputs.version }}-unsigned-review.zip" in runs
    )


def test_release_draft_builds_qt_on_both_platforms(tmp_path):
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    macos_excluded = _option_values(
        _macos_package_options(tmp_path), "--exclude-module"
    )
    windows_build = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")

    for start, end in (
        ("name: Build Windows application", "name: Sign in to Azure"),
        (
            "name: Build unsigned macOS review application",
            "uses: actions/upload-artifact",
        ),
    ):
        build_step = workflow.split(start, 1)[1].split(end, 1)[0]
        assert "VODFORGE_UI: qt" in build_step
    assert "install_vlc_macos.sh" not in workflow
    assert "install_vlc_windows.ps1" not in workflow
    assert {"vlc", "tkinter"} <= set(macos_excluded)
    assert '"--exclude-module", "vlc"' in windows_build


def test_macos_dependency_install_recovers_only_when_every_formula_is_present():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "if ! brew install python@3.13 ffmpeg deno; then" in workflow
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


def test_macos_release_preflight_keeps_each_qt_module_out_of_backend_process():
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    tests_workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    qt_modules = sorted((ROOT / "tests").glob("test_qt_*.py")) + sorted(
        (ROOT / "engineering-quality" / "tests").glob("test_qt_*.py")
    )
    # A module that borrows Qt test fixtures loads Qt too, whatever its name;
    # in the backend process it aborts on a display-less runner.
    borrowers = [
        path
        for folder in (ROOT / "tests", ROOT / "engineering-quality" / "tests")
        for path in sorted(folder.glob("test_*.py"))
        if not path.name.startswith("test_qt_")
        and re.search(
            r"^\s*(?:from|import) tests\.test_qt_",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    ]
    assert borrowers, "expected the known Qt-fixture borrowers"
    qt_modules += borrowers
    assert qt_modules
    for module in qt_modules:
        name = module.relative_to(ROOT).as_posix()
        for runner in (macos_build, tests_workflow):
            assert runner.count(f"--ignore={name}") == 1
            assert (
                len(
                    re.findall(
                        r"(?<![\w/.-])" + re.escape(name) + r"(?![\w/.-])", runner
                    )
                )
                == 2
            )


def test_release_builds_pin_yt_dlp_with_matching_ejs_scripts():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    app_source = (ROOT / "yt_downloader" / "download_service.py").read_text(
        encoding="utf-8"
    )

    pins = [
        line.split("==", 1)[1]
        for line in requirements
        if line.startswith("yt-dlp[default,curl-cffi]==")
    ]
    assert len(pins) == 1, "yt-dlp must be pinned exactly once"
    assert not any(line.startswith("yt-dlp>=") for line in requirements)
    # The packaged smoke check refuses any other yt-dlp than the pinned one.
    assert f'PINNED_YTDLP_VERSION = "{pins[0]}"' in app_source
    assert 'PINNED_YTDLP_EJS_VERSION = "0.8.0"' in app_source


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
        '/usr/bin/codesign --force --deep --sign - "$app_bundle"'
    )
    strict_verification = macos_build.index(
        '/usr/bin/codesign --verify --deep --strict "$app_bundle"'
    )
    runtime_smoke = macos_build.index('"$app_binary" --runtime-smoke')
    assert version_mutation < local_signing < strict_verification < runtime_smoke


def test_lazy_ytdlp_runtime_is_explicitly_collected_for_both_packagers(tmp_path):
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    macos_options = _macos_package_options(tmp_path)
    windows_build = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    app_source = (ROOT / "yt_downloader" / "download_service.py").read_text(
        encoding="utf-8"
    )

    assert "yt_dlp" in _option_values(macos_options, "--collect-all")
    assert "--collect-all yt_dlp" in windows_build
    assert '"$app_binary" --runtime-smoke' in macos_build
    assert (
        'Start-Process -FilePath $appBinary -ArgumentList "--runtime-smoke" -Wait -PassThru'
        in windows_build
    )
    assert 'resources_module.files("yt_dlp_ejs.yt.solver")' in app_source
    assert 'YTDLP_EJS_SOLVER_RESOURCES = ("core.min.js", "lib.min.js")' in app_source


def test_qt_player_runtime_is_collected_without_legacy_widget_dependencies(tmp_path):
    macos = " ".join(_macos_package_options(tmp_path))
    windows = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    for source in (macos, windows):
        assert "PySide6.QtMultimedia" in source
        assert "PySide6.QtQuickControls2" in source
        assert "tkinter" in source and "PIL.ImageTk" in source
        assert "libvlc.dll" not in source and "vlc_plugins" not in source
    assert not (ROOT / ".github/workflows/playback-windows-e2e.yml").exists()


def test_live_qt_playback_uses_one_media_player_and_native_video_outputs():
    main = (ROOT / "yt_downloader/qt_quick/Main.qml").read_text(encoding="utf-8")
    player = (ROOT / "yt_downloader/qt_quick/PlayerScene.qml").read_text(
        encoding="utf-8"
    )
    assert main.count("MediaPlayer {") == 1
    assert "audioOutput: AudioOutput" in main
    assert (
        "videoOutput: window.miniPlayerActive ? miniVideoSurface : playerScene.activeVideoSurface"
        in main
    )
    assert "VideoOutput {" in player and "VideoOutput.KeepLastFrame" in player
    assert "ffplay" not in (main + player).casefold()


def test_packaged_apps_and_windows_installer_use_vodforge_icon_assets(tmp_path):
    macos_build = (ROOT / "build_macos.sh").read_text(encoding="utf-8")
    macos_options = _macos_package_options(tmp_path)
    windows_build = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "installer_windows.iss").read_text(encoding="utf-8")

    assert _option_values(macos_options, "--icon") == [
        str(ROOT / "assets/VODForge.icns")
    ]
    assert "Print :CFBundleIconFile" in macos_build
    assert 'cmp -s "$icon_file" "$bundle_icon"' in macos_build
    assert '"--icon", $iconFile' in windows_build
    assert any(
        Path(value.rsplit(":", 1)[0]).as_posix().endswith("assets/icons/lucide")
        and value.rsplit(":", 1)[1] == "assets/icons/lucide"
        for value in _option_values(macos_options, "--add-data")
    )
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
    assert "VODForge-macOS-universal2-v${version}-unsigned-review.zip" in script
    assert "scripts.finalize_universal_macos" in script
    assert "SHA256SUMS.txt" in script
    assert "release delete-asset" in script
    assert 'release edit "$tag"' in script
    # The DMG, the universal update archive and both legacy update names are
    # uploaded and covered by the checksums.
    upload = script.split("gh release upload", 1)[1].split(
        "gh release delete-asset", 1
    )[0]
    sums = script.split("shasum -a 256", 1)[1].split("SHA256SUMS.txt", 1)[0]
    for name in ("$dmg", "$universal_zip", "$legacy_arm_zip", "$legacy_intel_zip"):
        assert name in upload and name in sums
    assert 'legacy_arm_zip="VODForge-macOS-arm64-v${version}.zip"' in script
    assert 'legacy_intel_zip="VODForge-macOS-x64-v${version}.zip"' in script


def test_release_notes_offer_one_mac_download_and_explain_legacy_files():
    notes = _release_notes_module().render_release_notes("0.2.6")

    mac = notes.index("### Mac")
    windows = notes.index("### Windows")
    assert mac < windows
    assert "VODForge-macOS-universal2-v0.2.6.dmg" in notes
    assert "Apple silicon" in notes and "Intel" in notes
    assert "VODForge-Windows-Setup-v0.2.6.exe" in notes
    assert "What’s new in 0.2.6" in notes
    # The ZIPs are named only as in-app update files, never linked as downloads.
    assert "releases/download/v0.2.6/VODForge-macOS-arm64" not in notes
    assert "releases/download/v0.2.6/VODForge-macOS-x64" not in notes
    assert "releases/download/v0.2.6/VODForge-macOS-universal2-v0.2.6.zip" not in notes
    assert "0.2.5 and earlier" in notes


def test_final_notes_require_written_highlights():
    with pytest.raises(ValueError, match="highlights"):
        _release_notes_module().render_release_notes("1.2.3")


def test_review_draft_accepts_qa_prerelease_version_without_unsafe_tag_text():
    notes = _release_notes_module().render_release_notes("0.2.3-qt-port", draft=True)
    assert "VODForge-Windows-Setup-v0.2.3-qt-port.exe" in notes
    for invalid in ("0.2.3/other", "0.2.3-", "0.2.3-qa..port"):
        with pytest.raises(ValueError):
            _release_notes_module().render_release_notes(invalid, draft=True)


def test_draft_release_notes_keep_the_release_team_safety_gate():
    notes = _release_notes_module().render_release_notes("1.2.3", draft=True)

    assert "Release-team draft" in notes
    assert "Do not publish" in notes
    assert "notarized" in notes


def test_artifact_only_dispatch_skips_all_release_mutation():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    inputs = workflow.split("jobs:", 1)[0]
    assert "artifacts_only:" in inputs
    assert "type: boolean" in inputs.split("artifacts_only:", 1)[1]
    draft = workflow.split("  draft:", 1)[1]
    assert "if: ${{ !inputs.artifacts_only }}" in draft.split("steps:", 1)[0]
    assert "gh release create" not in workflow.split("  draft:", 1)[0]
    assert "gh release upload" not in workflow
    assert "gh release edit" not in workflow
    assert "--draft" in draft


def test_builds_collect_impersonation_runtime(tmp_path):
    macos = _option_values(_macos_package_options(tmp_path), "--collect-all")
    assert "curl_cffi" in macos
    assert "--collect-all curl_cffi" in (ROOT / "build_windows.ps1").read_text()


def test_private_windows_qa_skips_mac_without_changing_release_gate():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    mac = workflow.split("  macos:\n", 1)[1].split("    steps:", 1)[0]
    assert "if: ${{ !(inputs.artifacts_only && inputs.qa_windows_only) }}" in mac
    draft = workflow.split("  draft:\n", 1)[1].split("    steps:", 1)[0]
    assert "if: ${{ !inputs.artifacts_only }}" in draft
    assert "needs: [windows, macos-universal]" in draft
    universal = workflow.split("  macos-universal:\n", 1)[1].split("    steps:", 1)[0]
    assert "inputs.qa_windows_only" in universal


def test_windows_source_pin_is_exact_and_ignored_outside_private_windows_mode():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    windows = workflow.split("  windows:\n", 1)[1].split("  macos:\n", 1)[0]
    validation = windows.split("name: Validate private Windows source pin", 1)[1]
    assert (
        "if: ${{ inputs.artifacts_only && inputs.qa_windows_only && inputs.qa_source_commit != '' }}"
        in validation
    )
    assert "QA_SOURCE_COMMIT: ${{ inputs.qa_source_commit }}" in validation
    assert "'^[0-9a-f]{40}$'" in validation
    assert (
        "ref: ${{ inputs.artifacts_only && inputs.qa_windows_only && inputs.qa_source_commit || github.ref }}"
        in windows
    )
    assert windows.index("Validate private Windows source pin") < windows.index(
        "actions/checkout@v4"
    )
    assert "azure/login@v3" in windows
    assert "azure/artifact-signing-action@v2" in windows


def test_private_candidate_is_preserved_before_bounded_upgrade_without_release_bypass():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    windows = workflow.split("  windows:\n", 1)[1].split("  macos:\n", 1)[0]
    preserve = windows.split(
        "name: Preserve signed private Windows candidate before native gates", 1
    )[1].split("- name: Verify running Windows upgrade", 1)[0]
    assert "if: ${{ inputs.artifacts_only && inputs.qa_windows_only }}" in preserve
    assert "windows-private-candidate-pending-acceptance" in preserve
    assert "if-no-files-found: error" in preserve
    assert (
        windows.index("Verify installer and package signed portable")
        < windows.index("Preserve signed private Windows candidate")
        < windows.index("Verify running Windows upgrade")
    )
    upgrade = windows.split("name: Verify running Windows upgrade", 1)[1]
    assert (
        "timeout-minutes: ${{ inputs.artifacts_only && inputs.qa_windows_only && 40 || 360 }}"
        in upgrade
    )
    assert "-LegacyHandoff" in upgrade
    assert upgrade.index("-LegacyHandoff") < upgrade.index("name: vodforge-windows")
