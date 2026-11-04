"""Create the universal2 Python environment the universal Mac app is built from.

PyInstaller can only build a universal app if Python and every compiled
dependency contain both arm64 and x86_64 code. This script:

1. `install-python`: downloads the pinned python.org installer (universal2),
   checks its SHA-256 and Apple signature, and installs it. Use it on a
   disposable build machine such as a GitHub runner; it changes the system.
2. `create-env`: makes a virtual environment from that Python, downloads the
   app's dependencies for both architectures at the same versions, fuses
   packages that publish separate arm64 and x86_64 wheels into universal2 wheels,
   installs them, and checks that both architectures import.

    sudo python3 -m scripts.create_universal_python_env install-python
    python3 -m scripts.create_universal_python_env create-env --output ENV_DIR

To move to a newer Python, update the version and its SHA-256 from
https://www.python.org/api/v2/downloads/release_file/?release=<id>.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PYTHON_VERSION = "3.13.17"
PYTHON_PKG_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-macos11.pkg"
)
PYTHON_PKG_SHA256 = "3053592af66128269efab37fe7851a4894920b27c442aeec99ce4d34d17c07e3"
PYTHON_PKG_SIGNER = "Python Software Foundation (BMM5U3QVKW)"
FRAMEWORK_PYTHON = Path(
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
)

# Highest macOS each architecture may require (the app's per-architecture minimums).
ARM_MAX = 26
INTEL_MAX = 15
MACHO_MAGIC = {
    bytes.fromhex(value)
    for value in (
        "feedfacf",
        "cffaedfe",
        "feedface",
        "cefaedfe",
        "cafebabe",
        "bebafeca",
    )
}
WHEEL_NAME = re.compile(
    r"^(?P<dist>[^-]+)-(?P<version>[^-]+)(?:-(?P<build>\d[^-]*))?-"
    r"(?P<python>[^-]+)-(?P<abi>[^-]+)-(?P<platform>[^-]+)\.whl$"
)


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


# --- Python installer -------------------------------------------------------


def install_python(download_dir: Path) -> Path:
    download_dir.mkdir(parents=True, exist_ok=True)
    pkg = download_dir / Path(PYTHON_PKG_URL).name
    with urllib.request.urlopen(PYTHON_PKG_URL, timeout=300) as response:
        pkg.write_bytes(response.read())
    digest = hashlib.sha256(pkg.read_bytes()).hexdigest()
    if digest != PYTHON_PKG_SHA256:
        raise ValueError(f"Python installer checksum mismatch: {digest}")
    signature = run(
        ["/usr/sbin/pkgutil", "--check-signature", str(pkg)], capture_output=True
    ).stdout
    if (
        PYTHON_PKG_SIGNER not in signature
        or "signed by a developer certificate issued by Apple" not in signature
    ):
        raise ValueError(
            "Python installer is not signed by the Python Software Foundation"
        )
    run(["/usr/sbin/installer", "-pkg", str(pkg), "-target", "/"])
    version = run([str(FRAMEWORK_PYTHON), "--version"], capture_output=True).stdout
    if version.split() != ["Python", PYTHON_VERSION]:
        raise ValueError(f"Unexpected installed Python: {version}")
    return FRAMEWORK_PYTHON


# --- Wheel resolution -------------------------------------------------------


def platform_tags(arch: str) -> list[str]:
    """pip --platform values, universal2 first so a fat wheel is preferred.

    Capped at the app's minimum macOS for that architecture, so a wheel that
    needs a newer system is never chosen.
    """
    newest = ARM_MAX if arch == "arm64" else INTEL_MAX
    versions = [(major, 0) for major in range(newest, 10, -1)]
    versions += [(10, minor) for minor in range(16, 8, -1)]
    tags = [f"macosx_{a}_{b}_universal2" for a, b in versions]
    # Apple silicon wheels start at macOS 11.
    tags += [
        f"macosx_{a}_{b}_{arch}" for a, b in versions if arch == "x86_64" or a >= 11
    ]
    return tags


def download(
    pip: list[str], requirements: list[str], arch: str, target: Path, *, no_deps=False
):
    command = [*pip, "download", "--only-binary=:all:", "--dest", str(target)]
    for tag in platform_tags(arch):
        command += ["--platform", tag]
    if no_deps:
        command.append("--no-deps")
    run([*command, *requirements])
    return sorted(target.glob("*.whl"))


def parse_wheel(path: Path) -> dict:
    match = WHEEL_NAME.match(path.name)
    if not match:
        raise ValueError(f"Unexpected wheel name: {path.name}")
    return match.groupdict()


def _platform_version(platform: str) -> tuple[int, int]:
    match = re.match(r"macosx_(\d+)_(\d+)_", platform)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


# --- Fusing -----------------------------------------------------------------


def _record_line(name: str, data: bytes) -> str:
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    )
    return f"{name},sha256={digest},{len(data)}"


def fuse_wheels(arm: Path, intel: Path, output_dir: Path, lipo=None) -> Path:
    """Combine an arm64 wheel and an x86_64 wheel of one release into universal2.

    Every file must be identical in both, except compiled Mach-O files (combined
    with lipo) and the wheel's own WHEEL/RECORD metadata (rewritten).
    """
    arm_info, intel_info = parse_wheel(arm), parse_wheel(intel)
    if (arm_info["dist"], arm_info["version"]) != (
        intel_info["dist"],
        intel_info["version"],
    ):
        raise ValueError(f"Wheels are different releases: {arm.name} / {intel.name}")
    lipo = lipo or _lipo
    platform_version = max(
        _platform_version(arm_info["platform"]),
        _platform_version(intel_info["platform"]),
    )
    platform = f"macosx_{platform_version[0]}_{platform_version[1]}_universal2"
    build = f"-{arm_info['build']}" if arm_info["build"] else ""
    name = (
        f"{arm_info['dist']}-{arm_info['version']}{build}-"
        f"{arm_info['python']}-{arm_info['abi']}-{platform}.whl"
    )
    with zipfile.ZipFile(arm) as za, zipfile.ZipFile(intel) as zx:
        dist_info = next(
            n.split("/", 1)[0]
            for n in za.namelist()
            if n.split("/", 1)[0].endswith(".dist-info")
        )
        metadata = {f"{dist_info}/WHEEL", f"{dist_info}/RECORD"}
        arm_names = set(za.namelist()) - metadata
        intel_names = set(zx.namelist()) - metadata
        if arm_names != intel_names:
            raise ValueError(
                f"{arm.name}: files differ between architectures: "
                f"{sorted(arm_names ^ intel_names)[:5]}"
            )
        files: dict[str, bytes] = {}
        for member in sorted(arm_names):
            if member.endswith("/"):
                continue
            a, x = za.read(member), zx.read(member)
            if a == x:
                files[member] = a
            elif a[:4] in MACHO_MAGIC and x[:4] in MACHO_MAGIC:
                files[member] = lipo(a, x)
            else:
                raise ValueError(
                    f"{arm.name}: {member} differs and is not compiled code"
                )
        wheel = za.read(f"{dist_info}/WHEEL").decode()
    tags = [f"{arm_info['python']}-{arm_info['abi']}-{platform}"]
    lines = [
        line
        for line in wheel.splitlines()
        if line.strip() and not line.startswith("Tag:")
    ]
    lines += [f"Tag: {tag}" for tag in tags]
    files[f"{dist_info}/WHEEL"] = ("\n".join(lines).strip() + "\n").encode()
    record = [_record_line(n, d) for n, d in files.items()]
    record.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = ("\n".join(record) + "\n").encode()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / name
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as out:
        for member, data in files.items():
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o755 << 16 if data[:4] in MACHO_MAGIC else 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, data)
    return destination


def _lipo(arm: bytes, intel: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        a, x, out = (Path(folder) / n for n in ("arm64", "x86_64", "fat"))
        a.write_bytes(arm)
        x.write_bytes(intel)
        run(["/usr/bin/lipo", "-create", str(a), str(x), "-output", str(out)])
        archs = set(
            run(
                ["/usr/bin/lipo", "-archs", str(out)], capture_output=True
            ).stdout.split()
        )
        if archs != {"arm64", "x86_64"}:
            raise ValueError(f"lipo produced {archs}")
        return out.read_bytes()


def pair_wheels(
    arm_wheels: list[Path], intel_wheels: list[Path], fused_dir: Path
) -> tuple[list[Path], list[dict]]:
    """One installable universal wheel per distribution, plus a description of each."""
    by_dist = lambda wheels: {parse_wheel(w)["dist"].lower(): w for w in wheels}
    arm, intel = by_dist(arm_wheels), by_dist(intel_wheels)
    if arm.keys() != intel.keys():
        raise ValueError(f"Dependency sets differ: {sorted(arm.keys() ^ intel.keys())}")
    chosen, report = [], []
    for dist in sorted(arm):
        a, x = arm[dist], intel[dist]
        if a.name == x.name and a.read_bytes() == x.read_bytes():
            wheel, how = (
                a,
                "pure" if parse_wheel(a)["platform"] == "any" else "universal2",
            )
        else:
            wheel, how = fuse_wheels(a, x, fused_dir), "fused"
        chosen.append(wheel)
        report.append(
            {
                "distribution": parse_wheel(wheel)["dist"],
                "version": parse_wheel(wheel)["version"],
                "wheel": wheel.name,
                "source": how,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "inputs": sorted({a.name, x.name}),
            }
        )
    return chosen, report


IMPORT_CHECK = (
    "import PIL.Image, psutil, curl_cffi, objc, AppKit, Quartz, PySide6.QtCore, "
    "PySide6.QtQuick, yt_dlp, certifi, PyInstaller; print('ok')"
)


def create_env(python: Path, output: Path, requirements: list[str]) -> dict:
    if output.exists():
        raise ValueError(f"Refusing existing environment: {output}")
    run([str(python), "-m", "venv", str(output)])
    env_python = output / "bin/python"
    pip = [str(env_python), "-m", "pip", "--disable-pip-version-check"]
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        arm_wheels = download(pip, requirements, "arm64", work / "arm64")
        pins = [
            f"{parse_wheel(w)['dist']}=={parse_wheel(w)['version']}" for w in arm_wheels
        ]
        intel_wheels = download(pip, pins, "x86_64", work / "x86_64", no_deps=True)
        wheels, report = pair_wheels(arm_wheels, intel_wheels, work / "fused")
        run([*pip, "install", "--no-deps", "--no-index", *map(str, wheels)])
    for arch in ("arm64", "x86_64"):
        result = run(
            ["/usr/bin/arch", f"-{arch}", str(env_python), "-c", IMPORT_CHECK],
            capture_output=True,
        )
        if result.stdout.strip() != "ok":
            raise ValueError(
                f"{arch} import check failed: {result.stdout}{result.stderr}"
            )
    receipt = {
        "python": run(
            [str(env_python), "--version"], capture_output=True
        ).stdout.strip(),
        "requirements": requirements,
        "wheels": report,
        "import_check": {"arm64": "ok", "x86_64": "ok"},
    }
    (output / "universal-env.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install-python")
    install.add_argument(
        "--download-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "vodforge-python",
    )
    env = commands.add_parser("create-env")
    env.add_argument("--output", type=Path, required=True)
    env.add_argument("--python", type=Path, default=FRAMEWORK_PYTHON)
    env.add_argument("--requirements", type=Path, default=ROOT / "requirements.txt")
    env.add_argument("--extra", action="append", default=["pyinstaller"])
    args = parser.parse_args(argv)
    if args.command == "install-python":
        print(install_python(args.download_dir))
        return 0
    requirements = ["-r", str(args.requirements), *args.extra]
    receipt = create_env(args.python, args.output, requirements)
    fused = sum(1 for w in receipt["wheels"] if w["source"] == "fused")
    print(
        f"Universal environment ready: {len(receipt['wheels'])} packages, {fused} fused"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
