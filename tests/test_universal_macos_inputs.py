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


def _fake_library(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture")
    return path


def test_private_recipe_selects_universal_target_and_retains_per_arch_policy(
    tmp_path, monkeypatch
):
    import json
    import plistlib

    from scripts.macos_package_contents import DATA, ICON, QML_DIR

    source = tmp_path / "source"
    for relative in [item for item, _ in DATA] + [ICON, QML_DIR + "/Main.qml"]:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.suffix and relative.count("/") > 0 and "." not in path.name:
            path.mkdir(exist_ok=True)
        else:
            path.write_bytes(b"fixture")
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ["ffmpeg", "ffprobe", "deno", "libx265.216.dylib"]:
        (tools / name).write_bytes(b"controlled input")
    output = tmp_path / "candidate"
    calls = []

    def git(args, **kwargs):
        if args[0] != "git":
            return json.dumps(
                {
                    "base": str(tmp_path / "python-base"),
                    "stdlib": str(tmp_path / "stdlib"),
                }
            )
        return "" if "status" in args else "a" * 40

    def pyinstaller(args, **kwargs):
        calls.append(args)
        if args[0] == "/usr/bin/codesign":
            return
        path = output / "dist/VODForge.app/Contents/Info.plist"
        path.parent.mkdir(parents=True)
        path.write_bytes(
            plistlib.dumps({"CFBundleIdentifier": "com.snowfallhd.vodforge"})
        )

    monkeypatch.setattr(
        "scripts.build_universal_macos.inspect_inputs", lambda _: {"qualified": True}
    )
    monkeypatch.setattr(
        "scripts.build_universal_macos.build_fullscreen",
        lambda source, output, arches: {
            "library": str(_fake_library(output / "libvodforge_fullscreen.dylib")),
            "source_sha256": "b" * 64,
            "architectures": arches,
            "qualified": True,
        },
    )
    monkeypatch.setattr("scripts.build_universal_macos.subprocess.check_output", git)
    monkeypatch.setattr("scripts.build_universal_macos.subprocess.run", pyinstaller)
    monkeypatch.setattr(
        "scripts.build_universal_macos.audit_payload", lambda _: {"qualified": True}
    )
    monkeypatch.delenv("VODFORGE_BUILD_TELEMETRY", raising=False)
    package(source, tmp_path / "venv/bin/python", tools, output, "0.2.6")
    # Telemetry stays off unless the build explicitly asks for it.
    assert (output / "version/VODFORGE_TELEMETRY_POLICY").read_text() == "disabled"
    assert calls[0][calls[0].index("--target-arch") + 1] == "universal2"
    assert (
        str(output / "native-fullscreen/libvodforge_fullscreen.dylib")
        + ":yt_downloader/platforms/macos"
        in calls[0]
    )
    info = plistlib.loads(
        (output / "dist/VODForge.app/Contents/Info.plist").read_bytes()
    )
    assert info["LSMinimumSystemVersionByArchitecture"] == {
        "arm64": "26.0",
        "x86_64": "15.0",
    }
    assert info["CFBundleVersion"] == "0.2.6"
    # The plist edit is followed by an ad-hoc re-sign and a strict check.
    assert calls[1][:3] == ["/usr/bin/codesign", "--force", "--deep"]
    assert calls[2][:2] == ["/usr/bin/codesign", "--verify"]
    # The universal app carries the same files as the regular build.
    data = [calls[0][i + 1] for i, v in enumerate(calls[0]) if v == "--add-data"]
    assert {item.split(":", 1)[1] for item in data} >= {d for _, d in DATA}
    binaries = [calls[0][i + 1] for i, v in enumerate(calls[0]) if v == "--add-binary"]
    assert str(tools / "libx265.216.dylib") + ":." in binaries
    assert json.loads((output / "build-receipt.json").read_text())["source"] == "a" * 40


def test_input_preflight_excludes_debug_symbols_but_not_runtime_extensions(tmp_path):
    debug = tmp_path / "module.so.dSYM/Contents/Resources/DWARF/module.so"
    debug.parent.mkdir(parents=True)
    debug.write_bytes(bytes.fromhex("cafebabe"))
    result = inspect_inputs(
        [tmp_path],
        lambda *_a, **_k: pytest.fail("Debug symbols are not runtime inputs"),
    )
    assert not result["qualified"]  # A debug-only input is never a runtime pass.
    assert str(debug) in result["excluded_debug_paths"]


def test_native_compile_failure_stops_before_pyinstaller(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(
        "scripts.build_universal_macos.inspect_inputs", lambda _: {"qualified": True}
    )
    monkeypatch.setattr(
        "scripts.build_universal_macos.subprocess.check_output",
        lambda args, **_: (
            ""
            if args[0] == "git"
            else json.dumps({"base": str(tmp_path), "stdlib": str(tmp_path)})
        ),
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ["ffmpeg", "ffprobe", "deno", "libsqlite3.dylib"]:
        (tools / name).touch()

    def fail(*_):
        raise ValueError("controlled native compile refusal")

    monkeypatch.setattr("scripts.build_universal_macos.build_fullscreen", fail)
    monkeypatch.setattr(
        "scripts.build_universal_macos.subprocess.run",
        lambda *_a, **_k: pytest.fail("Must not package without helper"),
    )
    with pytest.raises(ValueError, match="native compile refusal"):
        package(tmp_path, tmp_path / "python", tools, tmp_path / "candidate", "0.2.6")
    assert not (tmp_path / "candidate/dist").exists()
