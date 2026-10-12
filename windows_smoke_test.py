import shutil
import sys

import yt_dlp

from yt_downloader.download_service import QUALITY_OPTIONS, DownloadWorkerCore


def main() -> int:
    print("WINDOWS_IMPORT_OK")
    print("python", sys.version)
    print("yt-dlp", yt_dlp.version.__version__)
    print("ffmpeg_on_path", shutil.which("ffmpeg"))
    print("app_ffmpeg", DownloadWorkerCore._find_ffmpeg())
    print("quality_count", len(QUALITY_OPTIONS))
    print("qualities", "|".join(QUALITY_OPTIONS.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
