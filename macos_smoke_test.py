import sys

from yt_downloader.download_service import runtime_smoke


def main() -> int:
    if sys.platform != "darwin":
        print("macos_smoke_test.py must run on macOS")
        return 1
    return runtime_smoke(require_libvlc=False)


if __name__ == "__main__":
    raise SystemExit(main())
