from scripts.macos_native_closure import audit_payload


def payload(tmp_path, libraries, dependencies):
    for name in libraries:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(bytes.fromhex("cafebabe"))

    def run(args):
        name = str(__import__("pathlib").Path(args[-1]).relative_to(tmp_path))
        if "lipo" in args[0]:
            return libraries[name]
        arch = args[2]
        return "\n".join(
            "Load command 0\n cmd LC_LOAD_DYLIB\n name " + dep + " (offset 24)"
            for dep in dependencies.get((name, arch), [])
        )

    return audit_payload(tmp_path, run)


def test_distinct_abi_libraries_resolve_per_architecture(tmp_path):
    result = payload(
        tmp_path,
        {"ffmpeg": "arm64 x86_64", "lib217.dylib": "arm64", "lib216.dylib": "x86_64"},
        {
            ("ffmpeg", "arm64"): ["@loader_path/lib217.dylib"],
            ("ffmpeg", "x86_64"): ["@loader_path/lib216.dylib"],
        },
    )
    assert result["qualified"]


def test_wrong_architecture_library_and_unreferenced_thin_are_refused(tmp_path):
    result = payload(
        tmp_path,
        {"ffmpeg": "arm64 x86_64", "lib217.dylib": "arm64"},
        {("ffmpeg", "x86_64"): ["@loader_path/lib217.dylib"]},
    )
    assert not result["qualified"]
    assert {r["error"] for r in result["errors"]} == {
        "unresolved or external architecture provider",
        "unreferenced thin library",
    }


def test_extensions_must_be_universal_even_if_only_one_caller(tmp_path):
    result = payload(tmp_path, {"extension.so": "arm64"}, {})
    assert not result["qualified"]


def test_external_and_missing_dependencies_are_not_system_frameworks(tmp_path):
    result = payload(
        tmp_path,
        {"ffmpeg": "arm64 x86_64"},
        {
            ("ffmpeg", "arm64"): [
                "/usr/lib/libSystem.B.dylib",
                "/tmp/foreign.dylib",
                "@loader_path/missing.dylib",
            ]
        },
    )
    assert len(result["errors"]) == 2


def test_rpath_resolution_uses_declared_loader_path_and_rejects_symlink_escape(
    tmp_path,
):
    from pathlib import Path

    for name in ["entry", "lib/abi.dylib"]:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(bytes.fromhex("cafebabe"))

    def run(args):
        if "lipo" in args[0]:
            return "arm64 x86_64"
        if Path(args[-1]).name == "entry":
            return "Load command 0\n cmd LC_RPATH\n path @loader_path/lib (offset 12)\nLoad command 1\n cmd LC_LOAD_DYLIB\n name @rpath/abi.dylib (offset 24)"
        return ""

    assert audit_payload(tmp_path, run)["qualified"]
    outside = tmp_path.parent / "outside.dylib"
    outside.write_bytes(bytes.fromhex("cafebabe"))
    (tmp_path / "lib/abi.dylib").unlink()
    (tmp_path / "lib/abi.dylib").symlink_to(outside)
    assert not audit_payload(tmp_path, run)["qualified"]


def test_exact_loader_rpath_resolves_sibling_dependency(tmp_path):
    from pathlib import Path

    for name in ["entry", "abi.dylib"]:
        (tmp_path / name).write_bytes(bytes.fromhex("cafebabe"))

    def run(args):
        if "lipo" in args[0]:
            return "arm64 x86_64"
        if Path(args[-1]).name == "entry":
            return "Load command 0\n cmd LC_RPATH\n path @loader_path (offset 12)\nLoad command 1\n cmd LC_LOAD_DYLIB\n name @rpath/abi.dylib (offset 24)"
        return ""

    assert audit_payload(tmp_path, run)["qualified"]
