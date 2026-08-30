from yt_downloader.app import DownloaderApp
from yt_downloader.ui_events import _UiEventHost


def _assert_downloader_app_contract(app: DownloaderApp) -> None:
    host: _UiEventHost = app
    assert host is app
