from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    assert "Do not publish the draft until both macOS architectures" in workflow


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


def test_release_finalizer_replaces_unsigned_reviews_and_regenerates_checksums():
    script = (ROOT / "finalize_macos_release.sh").read_text()

    assert "Release finalization must run from main" in script
    assert "unsigned-review.zip" in script
    assert "sign_and_notarize_macos.sh" in script
    assert "SHA256SUMS.txt" in script
    assert "release delete-asset" in script
