from scripts.assemble_universal_helpers import HELPERS, check_edges, private_name


def test_arch_specific_abi_libraries_are_valid_only_on_their_own_edges(tmp_path):
    slices = {
        "ffmpeg": ["arm64", "x86_64"],
        "libx265.217.dylib": ["arm64"],
        "libx265.216.dylib": ["x86_64"],
    }

    def deps(name, arch):
        if name != "ffmpeg":
            return ["/usr/lib/libSystem.B.dylib"]
        return [
            "@loader_path/libx265." + ("217" if arch == "arm64" else "216") + ".dylib"
        ]

    assert not check_edges(slices, deps)
    wrong = check_edges(
        slices,
        lambda name, arch: (
            ["@loader_path/libx265.217.dylib"] if name == "ffmpeg" else []
        ),
    )
    assert wrong == [
        (
            "ffmpeg",
            "x86_64",
            "@loader_path/libx265.217.dylib",
            "missing architecture provider",
        )
    ]


def test_helper_closure_rejects_host_paths_escape_and_missing_provider(tmp_path):
    for dep in [
        "/opt/homebrew/lib/libsecret.dylib",
        "@loader_path/../foreign.dylib",
        "@loader_path/absent.dylib",
    ]:
        assert check_edges({"ffmpeg": ["arm64", "x86_64"]}, lambda *_, dep=dep: [dep])


def test_helper_libraries_get_private_names_so_they_cannot_replace_pythons():
    # Recorded failure: Intel FFmpeg's thin libcrypto.3.dylib took the name of
    # Python's universal copy in Contents/Frameworks, so _ssl lost arm64.
    for helper in HELPERS:
        assert private_name(helper) == helper
    for library in ("libcrypto.3.dylib", "libssl.3.dylib", "libavcodec.63.dylib"):
        bundled = private_name(library)
        assert bundled != library and bundled.endswith(library)
    assert len({private_name(n) for n in ("libssl.3.dylib", "libssl.4.dylib")}) == 2
