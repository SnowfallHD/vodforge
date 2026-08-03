import shutil
import sys

import yt_dlp

from yt_downloader.app import DownloaderApp, QUALITY_OPTIONS

print("WINDOWS_IMPORT_OK")
print("python", sys.version)
print("yt-dlp", yt_dlp.version.__version__)
print("ffmpeg_on_path", shutil.which("ffmpeg"))
print("app_ffmpeg", DownloaderApp._find_ffmpeg())
print("quality_count", len(QUALITY_OPTIONS))
print("qualities", "|".join(QUALITY_OPTIONS.keys()))
