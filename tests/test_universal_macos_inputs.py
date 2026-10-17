import pytest

from scripts.build_universal_macos import inspect_inputs, package


@pytest.mark.parametrize(
    "arch,floor,qualified",
    [
        ("arm64", "15.0", False),
        ("arm64 x86_64", "15.0", True),
        ("arm64 x86_64", "16.0", False),
    ],
)
def test_universal_inputs_require_both_slices_and_each_os_floor(
    tmp_path, arch, floor, qualified
):
    native = tmp_path / "python"
    native.write_bytes(bytes.fromhex("cafebabe"))

    def run(args, **kwargs):
        if "lipo" in args[0]:
            return arch
        minimum = floor if args[2] == "x86_64" else "26.0"
        return f"Load command 0\n cmd LC_BUILD_VERSION\n minos {minimum}\n"

    result = inspect_inputs([tmp_path], run)
    assert result["qualified"] == qualified
    if not qualified:
        assert result["errors"]


def test_universal_empty_or_missing_inputs_are_not_a_pass(tmp_path):
    assert not inspect_inputs([tmp_path])["qualified"]
    assert not inspect_inputs([tmp_path / "missing"])["qualified"]


def test_universal_package_refuses_dirty_source_without_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.build_universal_macos.subprocess.check_output",
        lambda *a, **k: " M owned-fix.py\n",
    )
    output = tmp_path / "candidate"
    with pytest.raises(ValueError, match="clean source"):
        package(tmp_path, tmp_path / "python", tmp_path / "tools", output, "0.2.6")
    assert not output.exists()


def test_private_recipe_selects_universal_target_and_retains_per_arch_policy(
    tmp_path, monkeypatch
):
    import json
    import plistlib

    source = tmp_path / "source"
    source.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ["ffmpeg", "ffprobe", "deno", "libsqlite3.dylib"]:
        (tools / name).write_bytes(b"controlled input")
    output = tmp_path / "candidate"
    calls = []

    def git(args, **kwargs):
        return "" if "status" in args else "a" * 40

    def pyinstaller(args, **kwargs):
        calls.append(args)
        path = output / "dist/VODForge.app/Contents/Info.plist"
        path.parent.mkdir(parents=True)
        path.write_bytes(
            plistlib.dumps({"CFBundleIdentifier": "com.snowfallhd.vodforge"})
        )

    monkeypatch.setattr(
        "scripts.build_universal_macos.inspect_inputs", lambda _: {"qualified": True}
    )
    monkeypatch.setattr("scripts.build_universal_macos.subprocess.check_output", git)
    monkeypatch.setattr("scripts.build_universal_macos.subprocess.run", pyinstaller)
    monkeypatch.setattr(
        "scripts.build_universal_macos.audit_payload", lambda _: {"qualified": True}
    )
    package(source, tmp_path / "venv/bin/python", tools, output, "0.2.6")
    assert calls[0][calls[0].index("--target-arch") + 1] == "universal2"
    info = plistlib.loads(
        (output / "dist/VODForge.app/Contents/Info.plist").read_bytes()
    )
    assert info["LSMinimumSystemVersionByArchitecture"] == {
        "arm64": "26.0",
        "x86_64": "15.0",
    }
    assert info["CFBundleVersion"] == "0.2.6"
    assert json.loads((output / "build-receipt.json").read_text())["source"] == "a" * 40
