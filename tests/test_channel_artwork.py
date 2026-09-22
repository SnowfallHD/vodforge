from __future__ import annotations

import base64
import io
import json
import threading

import pytest
from PIL import Image

from yt_downloader.channel_artwork import ChannelArtworkOwner, channel_request
from yt_downloader.channel_artwork_worker import acquire_profile, profile_thumbnails
from yt_downloader.thumbnail_network import ThumbnailUrlPolicy, validated_channel_url

CID = "UC" + "A" * 22
URL = "https://www.youtube.com/channel/" + CID
ROW = {"channel_id": CID, "webpage_url": "https://www.youtube.com/watch?v=one"}
AVATAR = "https://yt3.googleusercontent.com/avatar=s0"
BANNER = "https://yt3.googleusercontent.com/banner=s0"


def image_bytes(color="red", size=(80, 80)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format="JPEG")
    return stream.getvalue()


def profile():
    return {
        "schema_version": 1,
        "channel_id": CID,
        "name": "Creator",
        "description": "Source description",
        "images": {
            "avatar": base64.b64encode(image_bytes()).decode(),
            "banner": base64.b64encode(image_bytes("blue", (160, 80))).decode(),
        },
    }


@pytest.mark.parametrize(
    "source",
    [
        "https://vimeo.com/one",
        "https://youtube.com.evil.test/one",
        "http://youtube.com/watch?v=one",
        "file://youtube.com/one",
        "https://user:secret@youtube.com/watch?v=one",
        "https://youtube.com:444/watch?v=one",
    ],
)
def test_foreign_or_invalid_provider_cannot_authorize_channel_lookup(source):
    assert channel_request({**ROW, "webpage_url": source}) is None


def test_stable_provider_channel_id_wins_over_name_and_channel_url():
    assert channel_request(
        {
            **ROW,
            "channel": "PRIVATE name",
            "channel_url": "https://www.youtube.com/@Wrong",
        }
    ) == (URL, CID)
    assert channel_request({"channel_url": "https://www.youtube.com/@YouTube"}) == (
        "https://www.youtube.com/@YouTube",
        "",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/channel/" + CID,
        "http://youtube.com/channel/" + CID,
        "https://www.youtube.com/watch?v=one",
        "https://www.youtube.com/channel/short",
        "https://www.youtube.com/@YouTube?private=1",
        "https://www.youtube.com/@YouTube#fragment",
    ],
)
def test_channel_policy_requires_canonical_channel_provenance(url):
    with pytest.raises(RuntimeError):
        ThumbnailUrlPolicy.for_youtube_channel(url)


def test_avatar_authority_is_opt_in_and_role_source_is_exact():
    with pytest.raises(RuntimeError):
        ThumbnailUrlPolicy.for_source(URL).validate(AVATAR)
    policy = ThumbnailUrlPolicy.for_youtube_channel(URL)
    assert policy.validate(AVATAR) == AVATAR
    assert validated_channel_url(URL + "/") == URL
    for url in [
        "https://yt3.googleusercontent.com.evil.test/avatar",
        "http://yt3.googleusercontent.com/avatar",
        "https://yt3.googleusercontent.com:444/avatar",
        "https://user@yt3.googleusercontent.com/avatar",
    ]:
        with pytest.raises(RuntimeError):
            policy.validate(url)


def test_role_marker_does_not_choose_largest_banner_for_avatar():
    info = {
        "thumbnails": [
            {"id": "huge", "width": 9000, "height": 2000, "url": BANNER},
            {"id": "avatar_uncropped", "url": AVATAR},
            {"id": "banner_uncropped", "url": BANNER},
        ]
    }
    assert profile_thumbnails(info) == {"avatar": AVATAR, "banner": BANNER}
    assert profile_thumbnails({"thumbnails": info["thumbnails"][:1]}) == {}


def test_actual_worker_api_requests_no_upload_entries_or_media(monkeypatch):
    import yt_downloader.channel_artwork_worker as module

    options = []

    class Extractor:
        def __init__(self, opts):
            options.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            assert url == URL and download is False
            return {
                "channel_id": CID,
                "channel": "Creator",
                "description": "Source description",
                "entries": [],
                "thumbnails": [
                    {"id": "avatar_uncropped", "url": AVATAR},
                    {"id": "banner_uncropped", "url": BANNER},
                ],
            }

    monkeypatch.setattr(module, "YoutubeDL", Extractor)
    downloads = []

    def download(url, **kwargs):
        assert kwargs["policy"].validate(url) == url
        downloads.append(url)
        return image_bytes("red" if url == AVATAR else "blue")

    monkeypatch.setattr(module, "download_bounded_url_bytes", download)
    result = acquire_profile(URL, CID)
    assert set(result["images"]) == {"avatar", "banner"}
    assert downloads == [AVATAR, BANNER]
    assert options[0]["playlist_items"] == "0"
    assert options[0]["skip_download"] and options[0]["extract_flat"]
    assert options[0]["cachedir"] is False
    assert "cookiesfrombrowser" not in options[0] and "cookiefile" not in options[0]


def test_both_roles_are_cached_privately_and_reused_after_restart(tmp_path):
    calls = []

    def loader(request, cancelled):
        calls.append(request)
        return profile()

    owner = ChannelArtworkOwner(tmp_path, loader=loader)
    avatar = owner.resolve(ROW, "avatar", threading.Event())
    banner = owner.resolve(ROW, "banner", threading.Event())
    assert avatar and banner and avatar != banner
    assert Image.open(avatar).getpixel((40, 40))[0] > 200
    assert Image.open(banner).getpixel((40, 40))[2] > 200
    assert len(calls) == 1
    restarted = ChannelArtworkOwner(
        tmp_path, loader=lambda *_: pytest.fail("Fresh cache must avoid network")
    )
    assert restarted.resolve(ROW, "avatar", threading.Event()) == avatar
    assert restarted.snapshot(ROW)["description"] == "Source description"
    assert all(CID not in path.name for path in tmp_path.iterdir())


def test_same_named_channels_do_not_share_profile_cache(tmp_path):
    calls = []

    def loader(request, cancelled):
        calls.append(request)
        result = profile()
        result["channel_id"] = request[1]
        return result

    owner = ChannelArtworkOwner(tmp_path, loader=loader)
    first = owner.resolve({**ROW, "channel": "Same name"}, "avatar", threading.Event())
    second = owner.resolve(
        {**ROW, "channel": "Same name", "channel_id": "UC" + "B" * 22},
        "avatar",
        threading.Event(),
    )
    assert first != second and len(calls) == 2


def test_cancelled_channel_lookup_does_not_poison_same_owner_retry(tmp_path):
    cancelled = threading.Event()
    calls = []

    def loader(request, event):
        calls.append(request)
        if len(calls) == 1:
            event.set()
            return None
        return profile()

    owner = ChannelArtworkOwner(tmp_path, loader=loader)
    assert owner.resolve(ROW, "avatar", cancelled) is None
    assert not owner._retry
    cancelled.clear()
    assert owner.resolve(ROW, "avatar", cancelled) is not None
    assert len(calls) == 2


def test_unavailable_channel_uses_bounded_negative_cache(tmp_path):
    calls = []
    clock = [1000]
    owner = ChannelArtworkOwner(
        tmp_path, clock=lambda: clock[0], loader=lambda *args: calls.append(args)
    )
    for _ in range(5):
        assert owner.resolve(ROW, "avatar", threading.Event()) is None
    assert len(calls) == 1
    clock[0] += 301
    assert owner.resolve(ROW, "avatar", threading.Event()) is None
    assert len(calls) == 2


def test_wrong_channel_response_cannot_replace_identity(tmp_path):
    result = profile()
    result["channel_id"] = "UC" + "B" * 22
    owner = ChannelArtworkOwner(tmp_path, loader=lambda *_: result)
    assert owner.resolve(ROW, "avatar", threading.Event()) is None
    assert not list(tmp_path.glob("*.jpg"))


def test_stale_profile_remains_available_if_refresh_fails(tmp_path):
    clock = [1000]
    owner = ChannelArtworkOwner(
        tmp_path, clock=lambda: clock[0], loader=lambda *_: profile()
    )
    avatar = owner.resolve(ROW, "avatar", threading.Event())
    clock[0] += 8 * 24 * 60 * 60
    restarted = ChannelArtworkOwner(
        tmp_path, clock=lambda: clock[0], loader=lambda *_: None
    )
    assert restarted.resolve(ROW, "avatar", threading.Event()) == avatar
    assert restarted.snapshot(ROW)["name"] == "Creator"


def test_corrupt_or_wrong_identity_manifest_is_not_used(tmp_path):
    owner = ChannelArtworkOwner(tmp_path, loader=lambda *_: profile())
    avatar = owner.resolve(ROW, "avatar", threading.Event())
    manifest = next(tmp_path.glob("*.json"))
    data = json.loads(manifest.read_text())
    data["channel_id"] = "UC" + "B" * 22
    manifest.write_text(json.dumps(data))
    restarted = ChannelArtworkOwner(tmp_path, loader=lambda *_: None)
    assert restarted.resolve(ROW, "avatar", threading.Event()) is None
    assert avatar.exists()


@pytest.mark.parametrize("outcome", ["cancelled", "timeout", "valid"])
def test_owned_profile_process_has_deadline_cancellation_and_json_boundary(
    tmp_path, monkeypatch, outcome
):
    import subprocess

    from yt_downloader import channel_artwork as module

    cancelled = threading.Event()
    clock = [1.0]
    processes = []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    class Process:
        def __init__(self, command, **kwargs):
            self.command = command
            self.returncode = None
            self.killed = False
            self.inputs = []
            processes.append(self)

        def communicate(self, *, input=None, timeout=None):
            self.inputs.append(input)
            if self.killed:
                return b"", b""
            if outcome == "valid":
                self.returncode = 0
                return json.dumps(profile()).encode(), b""
            if outcome == "cancelled":
                cancelled.set()
            else:
                clock[0] += 10
            raise subprocess.TimeoutExpired(self.command, timeout)

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    owner = ChannelArtworkOwner(tmp_path)
    result = owner._load_worker((URL, CID), cancelled)
    assert (result is not None) == (outcome == "valid")
    assert processes[0].killed == (outcome != "valid")
    assert json.loads(processes[0].inputs[0]) == {"url": URL, "channel_id": CID}


def test_channel_owner_close_prevents_late_profile_files(tmp_path):
    owner = None

    def loader(_request, _cancelled):
        owner.close()
        return profile()

    owner = ChannelArtworkOwner(tmp_path, loader=loader)
    assert owner.resolve(ROW, "avatar", threading.Event()) is None
    assert not list(tmp_path.glob("*"))


def test_large_original_banner_uses_explicit_sized_provider_banner_variant():
    bounded = "https://yt3.googleusercontent.com/banner=w2560"
    selected = profile_thumbnails(
        {
            "thumbnails": [
                {"id": "avatar_uncropped", "url": AVATAR},
                {"id": "banner_uncropped", "url": BANNER},
                {
                    "id": "5",
                    "url": bounded,
                    "width": 2560,
                    "height": 424,
                    "preference": -10,
                },
                {
                    "id": "arbitrary-large-square",
                    "url": "https://invalid.test/wrong",
                    "width": 4096,
                    "height": 4096,
                },
            ]
        }
    )
    assert selected == {"avatar": AVATAR, "banner": bounded}


def test_saved_history_keeps_channel_identity_for_actual_artwork_consumer(tmp_path):
    from yt_downloader.history import (
        load_history,
        sanitize_history_record,
        save_history,
    )

    row = sanitize_history_record(
        {
            **ROW,
            "channel": "Shared name",
            "channel_url": URL + "?private=secret#private",
            "uploader_url": "https://user:secret@www.youtube.com/@Creator?private=secret",
        },
        tmp_path,
    )
    path = tmp_path / "history.json"
    save_history(path, [row])
    loaded = load_history(path)[0]
    assert loaded["channel_id"] == CID
    assert loaded["channel_url"] == URL
    assert loaded["uploader_url"] == "https://www.youtube.com/@Creator"
    assert "secret" not in path.read_text()
    requests = []
    owner = ChannelArtworkOwner(
        tmp_path / "artwork",
        loader=lambda *args: requests.append(args) or profile(),
    )
    assert owner.resolve(loaded, "avatar", threading.Event()).is_file()
    assert requests[0][0] == (URL, CID)


@pytest.mark.parametrize("identity", ["", "bad\x00identity", "bad\nidentity"])
def test_invalid_durable_channel_identity_is_not_retained(tmp_path, identity):
    from yt_downloader.history import sanitize_history_record

    row = sanitize_history_record({"channel_id": identity}, tmp_path)
    assert "channel_id" not in row
