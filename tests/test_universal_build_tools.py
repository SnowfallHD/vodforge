"""Tools that prepare the universal Mac build: helper collection and wheel fusing."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.collect_macos_helpers import collect, resolve
from scripts.create_universal_python_env import (
    ARM_MAX,
    INTEL_MAX,
    fuse_wheels,
    pair_wheels,
    platform_tags,
)

ARM_CODE = bytes.fromhex("cffaedfe") + b"arm64 code"
INTEL_CODE = bytes.fromhex("cffaedfe") + b"x86_64 code"


def _wheel(
    folder: Path, platform: str, files: dict[str, bytes], tag_lines=None
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"demo-1.0-cp313-cp313-{platform}.whl"
    tag_lines = tag_lines or [f"Tag: cp313-cp313-{platform}"]
    wheel = (
        "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n" + "\n".join(tag_lines) + "\n\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("demo-1.0.dist-info/WHEEL", wheel)
        archive.writestr(
            "demo-1.0.dist-info/RECORD", f"different record for {platform}"
        )
    return path


def _fake_lipo(arm: bytes, intel: bytes) -> bytes:
    return b"FAT:" + arm + b"|" + intel


def test_fused_wheel_combines_compiled_code_and_rewrites_metadata(tmp_path):
    shared = {
        "demo/__init__.py": b"VALUE = 1\n",
        "demo-1.0.dist-info/METADATA": b"Name: demo\n",
    }
    arm = _wheel(
        tmp_path / "a", "macosx_11_0_arm64", {**shared, "demo/_core.so": ARM_CODE}
    )
    intel = _wheel(
        tmp_path / "x", "macosx_10_13_x86_64", {**shared, "demo/_core.so": INTEL_CODE}
    )

    fused = fuse_wheels(arm, intel, tmp_path / "out", lipo=_fake_lipo)

    assert fused.name == "demo-1.0-cp313-cp313-macosx_11_0_universal2.whl"
    with zipfile.ZipFile(fused) as archive:
        assert archive.read("demo/_core.so") == _fake_lipo(ARM_CODE, INTEL_CODE)
        assert archive.read("demo/__init__.py") == b"VALUE = 1\n"
        wheel = archive.read("demo-1.0.dist-info/WHEEL").decode().splitlines()
        assert wheel == [
            "Wheel-Version: 1.0",
            "Root-Is-Purelib: false",
            "Tag: cp313-cp313-macosx_11_0_universal2",
        ]
        record = archive.read("demo-1.0.dist-info/RECORD").decode().splitlines()
        assert {line.split(",")[0] for line in record} == set(archive.namelist())
        assert "demo-1.0.dist-info/RECORD,," in record


def test_fusing_refuses_files_that_differ_but_are_not_compiled_code(tmp_path):
    arm = _wheel(tmp_path / "a", "macosx_11_0_arm64", {"demo/data.txt": b"arm"})
    intel = _wheel(tmp_path / "x", "macosx_10_13_x86_64", {"demo/data.txt": b"intel"})
    with pytest.raises(ValueError, match="not compiled code"):
        fuse_wheels(arm, intel, tmp_path / "out", lipo=_fake_lipo)


def test_fusing_refuses_wheels_with_different_file_lists(tmp_path):
    # imageio-ffmpeg is the real example: it ships a differently named FFmpeg
    # executable for each architecture.
    arm = _wheel(tmp_path / "a", "macosx_11_0_arm64", {"demo/bin-arm": ARM_CODE})
    intel = _wheel(tmp_path / "x", "macosx_10_13_x86_64", {"demo/bin-x86": INTEL_CODE})
    with pytest.raises(ValueError, match="files differ"):
        fuse_wheels(arm, intel, tmp_path / "out", lipo=_fake_lipo)


def test_identical_wheels_are_used_as_is(tmp_path):
    files = {"demo/__init__.py": b""}
    arm = _wheel(tmp_path / "a", "macosx_10_13_universal2", files)
    intel = _wheel(tmp_path / "x", "macosx_10_13_universal2", files)
    intel.write_bytes(arm.read_bytes())
    wheels, report = pair_wheels([arm], [intel], tmp_path / "fused")
    assert wheels == [arm]
    assert report[0]["source"] == "universal2"
    assert not (tmp_path / "fused").exists()


def test_platform_tags_never_exceed_each_architectures_minimum_macos():
    for arch, newest in (("arm64", ARM_MAX), ("x86_64", INTEL_MAX)):
        tags = platform_tags(arch)
        majors = {int(tag.split("_")[1]) for tag in tags}
        assert max(majors) == newest
        assert tags[0].endswith("_universal2")
        assert all(tag.endswith(("_universal2", f"_{arch}")) for tag in tags)
    assert not any(
        t.startswith("macosx_10_")
        for t in platform_tags("arm64")
        if t.endswith("_arm64")
    )


def _otool_fixture(graph):
    """Fake otool: graph maps a real path to (install id, dependencies, rpaths)."""

    def run(args, path):
        identity, deps, rpaths = graph[Path(path).resolve()]
        if args == ["-D"]:
            return f"{path}:\n{identity}\n" if identity else f"{path}:\n"
        if args == ["-L"]:
            return f"{path}:\n" + "".join(
                f"\t{d} (compatibility version 1.0.0)\n" for d in deps
            )
        lines = []
        for rpath in rpaths:
            lines += [
                "Load command 9",
                "          cmd LC_RPATH",
                "      cmdsize 32",
                f"         path {rpath} (offset 12)",
            ]
        return "\n".join(lines)

    return run


def test_helper_collection_follows_every_kind_of_library_reference(tmp_path):
    cellar = tmp_path / "Cellar"
    bin_dir, lib_dir, extra = cellar / "bin", cellar / "lib", cellar / "extra"
    for folder in (bin_dir, lib_dir, extra):
        folder.mkdir(parents=True)
    tools = {}
    for name in ("ffmpeg", "ffprobe", "deno"):
        (bin_dir / name).write_bytes(b"exe " + name.encode())
        tools[name] = bin_dir / name
    for name in ("libavcodec.63.dylib", "libx265.217.dylib"):
        (lib_dir / name).write_bytes(name.encode())
    (extra / "libsqlite3.3.53.dylib").write_bytes(b"sqlite")
    (lib_dir / "libsqlite3.dylib").symlink_to(extra / "libsqlite3.3.53.dylib")
    graph = {
        tools["ffmpeg"].resolve(): (
            None,
            [f"{lib_dir}/libavcodec.63.dylib", "/usr/lib/libSystem.B.dylib"],
            [],
        ),
        tools["ffprobe"].resolve(): (
            None,
            ["@rpath/libavcodec.63.dylib"],
            ["@loader_path/../lib"],
        ),
        tools["deno"].resolve(): (
            None,
            ["/System/Library/Frameworks/Security.framework/Security"],
            [],
        ),
        (lib_dir / "libavcodec.63.dylib").resolve(): (
            "@rpath/libavcodec.63.dylib",
            [
                "@rpath/libavcodec.63.dylib",
                "@loader_path/libx265.217.dylib",
                f"{lib_dir}/libsqlite3.dylib",
            ],
            [],
        ),
        (lib_dir / "libx265.217.dylib").resolve(): (None, [], []),
        (extra / "libsqlite3.3.53.dylib").resolve(): (None, [], []),
    }

    output = tmp_path / "helpers"
    receipt = collect(output, tools, run=_otool_fixture(graph))

    assert sorted(p.name for p in output.iterdir()) == [
        "deno",
        "ffmpeg",
        "ffprobe",
        "libavcodec.63.dylib",
        "libsqlite3.dylib",
        "libx265.217.dylib",
    ]
    # A symlinked reference is stored under the name the loader asks for.
    assert (output / "libsqlite3.dylib").read_bytes() == b"sqlite"
    assert not (output / "libsqlite3.dylib").is_symlink()
    # The receipt sits beside the folder, which must hold only helpers.
    assert (tmp_path / "helpers-receipt.json").is_file()
    assert set(receipt["files"]) == {p.name for p in output.iterdir()}


def test_helper_collection_refuses_two_libraries_with_the_same_name(tmp_path):
    first, second = tmp_path / "a/libz.1.dylib", tmp_path / "b/libz.1.dylib"
    tools = {}
    for path in (first, second):
        path.parent.mkdir(parents=True)
        path.write_bytes(str(path).encode())
    for name, dep in (("ffmpeg", first), ("ffprobe", second), ("deno", None)):
        tools[name] = tmp_path / name
        tools[name].write_bytes(name.encode())
    graph = {
        tools["ffmpeg"].resolve(): (None, [str(first)], []),
        tools["ffprobe"].resolve(): (None, [str(second)], []),
        tools["deno"].resolve(): (None, [], []),
        first.resolve(): (None, [], []),
        second.resolve(): (None, [], []),
    }
    with pytest.raises(ValueError, match="both named libz.1.dylib"):
        collect(tmp_path / "out", tools, run=_otool_fixture(graph))


def test_unresolvable_rpath_reference_fails_instead_of_being_skipped(tmp_path):
    owner = tmp_path / "ffmpeg"
    owner.write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="cannot resolve"):
        resolve("@rpath/libmissing.dylib", owner, owner, [tmp_path / "lib"])
