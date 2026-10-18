"""Build-owner boundaries; command doubles compile no product/native GUI code."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.build_macos_fullscreen import LIBRARY, build


def compiler(tmp_path, *, wrong_arch=False, floor=None, foreign=False):
    calls = []
    slices = {}

    def run(args):
        calls.append(args)
        if args[0] == "/usr/bin/xcrun":
            target = Path(args[args.index("-o") + 1])
            arch = args[args.index("-arch") + 1]
            target.write_bytes(bytes.fromhex("cafebabe") + arch.encode())
            slices[str(target)] = [arch]
            return ""
        if "-create" in args:
            target = Path(args[-1])
            target.write_bytes(bytes.fromhex("cafebabe") + b"both")
            slices[str(target)] = ["arm64", "x86_64"]
            return ""
        if args[0] == "/usr/bin/lipo":
            if wrong_arch:
                return "arm64"
            return " ".join(slices.get(args[-1], ["x86_64"]))
        arch = args[args.index("-arch") + 1]
        version = floor or ("26.0" if arch == "arm64" else "15.0")
        dependency = (
            "/tmp/foreign.dylib"
            if foreign
            else "/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit"
        )
        return f"Load command 0\n cmd LC_BUILD_VERSION\n minos {version}\nLoad command 1\n cmd LC_LOAD_DYLIB\n name {dependency} (offset 24)\n"

    return run, calls


@pytest.mark.parametrize("arches", [["arm64"], ["x86_64"], ["arm64", "x86_64"]])
def test_explicit_helper_targets_and_source_output_provenance(tmp_path, arches):
    source = tmp_path / "owner.m"
    (tmp_path / "header_toolbar.m").write_text("// header fixture")
    source.write_text("// controlled source, not compiled by this unit fixture\n")
    output = tmp_path / "native"
    run, _calls = compiler(tmp_path)
    # A single-slice final file is a copy of the checked slice.
    if len(arches) == 1:
        original = run

        def run(args):
            if args[0] == "/usr/bin/lipo" and args[-1].endswith(LIBRARY):
                return arches[0]
            return original(args)

    receipt = build(source, output, arches, run)
    assert receipt["qualified"]
    assert receipt["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (
        receipt["output_sha256"]
        == hashlib.sha256((output / LIBRARY).read_bytes()).hexdigest()
    )
    assert receipt["source_inputs"] == [
        {
            "path": str(source.resolve()),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        {
            "path": str((tmp_path / "header_toolbar.m").resolve()),
            "sha256": hashlib.sha256(
                (tmp_path / "header_toolbar.m").read_bytes()
            ).hexdigest(),
        },
    ]
    commands = receipt["commands"]
    for arch in arches:
        command = next(
            c for c in commands if "-arch" in c and c[c.index("-arch") + 1] == arch
        )
        assert (
            "-mmacosx-version-min=" + {"arm64": "26.0", "x86_64": "15.0"}[arch]
            in command
        )
        assert str(source) in command and str(tmp_path / "header_toolbar.m") in command
        assert "-fno-objc-arc" in command and "-Werror" in command
        assert command[command.index("-install_name") + 1] == "@rpath/" + LIBRARY
    assert any("-create" in c for c in commands) == (len(arches) == 2)
    assert json.loads((output / "build-receipt.json").read_text()) == receipt


@pytest.mark.parametrize(
    "options", [{"wrong_arch": True}, {"floor": "16.0"}, {"foreign": True}]
)
def test_helper_rejects_wrong_abi_floor_and_host_dependency(tmp_path, options):
    source = tmp_path / "owner.m"
    (tmp_path / "header_toolbar.m").write_text("// header fixture")
    source.write_text("// fixture")
    run, _ = compiler(tmp_path, **options)
    with pytest.raises(ValueError):
        build(source, tmp_path / "output", ["x86_64"], run)
    assert not json.loads((tmp_path / "output/build-receipt.json").read_text())[
        "qualified"
    ]


def test_compile_failure_preserved_and_never_published_as_helper(tmp_path):
    source = tmp_path / "owner.m"
    (tmp_path / "header_toolbar.m").write_text("// header fixture")
    source.write_text("// fixture")

    def fail(args):
        raise subprocess.CalledProcessError(1, args, "controlled compiler failure")

    with pytest.raises(subprocess.CalledProcessError):
        build(source, tmp_path / "output", ["arm64"], fail)
    receipt = json.loads((tmp_path / "output/build-receipt.json").read_text())
    assert not receipt["qualified"] and receipt["commands"]
    assert not (tmp_path / "output" / LIBRARY).exists()


def test_missing_source_existing_output_and_invalid_targets_stop_before_command(
    tmp_path,
):
    source = tmp_path / "owner.m"
    run = lambda *_: pytest.fail("No compiler expected")
    with pytest.raises(ValueError, match="source is missing"):
        build(source, tmp_path / "out", ["arm64"], run)
    assert not (tmp_path / "out").exists()
    (tmp_path / "header_toolbar.m").write_text("// header fixture")
    source.write_text("// fixture")
    (tmp_path / "out").mkdir()
    with pytest.raises(ValueError, match="existing"):
        build(source, tmp_path / "out", ["arm64"], run)
    for arches in [[], ["arm64", "arm64"], ["unsupported"]]:
        with pytest.raises(ValueError, match="architectures"):
            build(source, tmp_path / "other", arches, run)


@pytest.mark.parametrize(
    "arch,configured", [("arm64", "15.0"), ("x86_64", "14.9"), ("arm64", "nonsense")]
)
def test_lower_or_malformed_package_minimum_refused(arch, configured):
    from scripts.build_macos_fullscreen import deployment_minimum

    with pytest.raises(ValueError):
        deployment_minimum(arch, configured)


def test_header_missing_refuses_before_output_or_compiler(tmp_path):
    source = tmp_path / "owner.m"
    source.write_text("// owner")
    with pytest.raises(ValueError, match="header toolbar source is missing"):
        build(
            source,
            tmp_path / "output",
            ["arm64"],
            lambda *_: pytest.fail("No compiler"),
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("changed", ["owner.m", "header_toolbar.m"])
def test_each_bound_source_mutation_refuses_qualification(tmp_path, changed):
    source = tmp_path / "owner.m"
    source.write_text("// owner")
    header = tmp_path / "header_toolbar.m"
    header.write_text("// header")
    run, _ = compiler(tmp_path)

    def mutating_run(args):
        result = run(args)
        if args[0] == "/usr/bin/xcrun":
            (tmp_path / changed).write_text("// changed during compile")
        if args[0] == "/usr/bin/lipo" and args[-1].endswith(LIBRARY):
            return "arm64"
        return result

    with pytest.raises(ValueError, match="source changed during compilation"):
        build(source, tmp_path / "output", ["arm64"], mutating_run)
    receipt = json.loads((tmp_path / "output/build-receipt.json").read_text())
    assert not receipt["qualified"]
    assert len(receipt["source_inputs"]) == 2
