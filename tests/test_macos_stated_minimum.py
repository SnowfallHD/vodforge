import plistlib

import pytest

from scripts.check_macos_minimum import minimum_errors

MAGIC = b"\xca\xfe\xba\xbe"


def app_with(tmp_path, stated, files):
    """files: {relative path: {arch: minos}}"""
    app = tmp_path / "VODForge.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "LSMinimumSystemVersion": "15.0",
                "LSMinimumSystemVersionByArchitecture": stated,
            }
        )
    )
    for name in files:
        path = app / "Contents" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(MAGIC + b"\0" * 8)
    (app / "Contents" / "notes.txt").write_text("not code")

    def run(args):
        path = args[-1].replace("\\", "/")
        slices = next(v for k, v in files.items() if path.endswith(k))
        if "lipo" in args[0]:
            return " ".join(slices)
        arch = args[args.index("-arch") + 1]
        return f"Load command 0\n cmd LC_BUILD_VERSION\n minos {slices[arch]}\n"

    return app, run


BOTH_15 = {"arm64": "15.0", "x86_64": "15.0"}


def test_matching_minimums_pass(tmp_path):
    app, run = app_with(
        tmp_path,
        BOTH_15,
        {
            "MacOS/VODForge": {"arm64": "13.0", "x86_64": "13.0"},
            "Frameworks/h.dylib": BOTH_15,
        },
    )
    assert minimum_errors(app, run) == []


def test_minimum_above_what_the_files_need_is_refused(tmp_path):
    app, run = app_with(
        tmp_path,
        {"arm64": "26.0", "x86_64": "15.0"},
        {"MacOS/VODForge": BOTH_15},
    )
    errors = minimum_errors(app, run)
    assert len(errors) == 1
    assert "states macOS 26.0 for arm64" in errors[0]
    assert "need only 15.0" in errors[0]


def test_minimum_below_what_a_file_needs_is_refused(tmp_path):
    app, run = app_with(
        tmp_path,
        BOTH_15,
        {
            "MacOS/VODForge": BOTH_15,
            "Frameworks/new.dylib": {"arm64": "26.0", "x86_64": "15.0"},
        },
    )
    errors = minimum_errors(app, run)
    assert len(errors) == 1
    assert "Frameworks/new.dylib" in errors[0] and "needs 26.0" in errors[0]


@pytest.mark.parametrize("missing", ["arm64", "x86_64"])
def test_a_missing_architecture_is_reported(tmp_path, missing):
    other = "x86_64" if missing == "arm64" else "arm64"
    app, run = app_with(tmp_path, BOTH_15, {"MacOS/VODForge": {other: "15.0"}})
    assert any(f"no {missing} code" in e for e in minimum_errors(app, run))
