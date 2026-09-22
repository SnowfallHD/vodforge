import threading
import time
from types import SimpleNamespace

import pytest

import yt_downloader.volume_storage as storage
from yt_downloader.volume_storage import (
    StorageCapacityOwner,
    StorageVolume,
    VolumeCapacity,
)


def wait(owner, predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = owner.poll()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.005)
    raise AssertionError("Capacity did not reach the expected state")


def test_platform_defaults_and_shared_apfs_capacity_are_truthful():
    assert storage.default_volume("win32") == "C:\\"
    assert storage.default_volume("darwin") == "/"
    volumes = (
        StorageVolume("/System/Volumes/Data", "Data", "disk3"),
        StorageVolume("/", "Macintosh HD", "disk3"),
        StorageVolume("/Volumes/Media", "Media", "disk4"),
    )
    distinct = storage.distinct_capacity_volumes(volumes)
    assert [v.path for v in distinct] == ["/", "/Volumes/Media"]


def test_volume_usage_does_not_depend_on_empty_library_and_unmounted_path_never_falls_back(
    monkeypatch,
):
    volume = StorageVolume("/", "Macintosh HD")
    monkeypatch.setattr(storage, "available_volumes", lambda _: (volume,))
    calls = []

    def usage(path):
        calls.append(path)
        return SimpleNamespace(total=1000, free=350)

    monkeypatch.setattr(storage.shutil, "disk_usage", usage)
    _, facts = storage.read_volume_capacity("/", threading.Event())
    assert (facts.total, facts.used, facts.free, facts.fraction_used) == (
        1000,
        650,
        350,
        0.65,
    )
    _, missing = storage.read_volume_capacity(
        "/Volumes/Disconnected", threading.Event()
    )
    assert missing is None and calls == ["/"]


@pytest.mark.parametrize("failure", ["exception", "missing", "cancelled"])
def test_unavailable_capacity_never_fabricates_zero_usage(monkeypatch, failure):
    event = threading.Event()
    monkeypatch.setattr(
        storage, "available_volumes", lambda _: (StorageVolume("/", "Mac"),)
    )

    def usage(_):
        if failure == "exception":
            raise OSError("disconnected")
        return SimpleNamespace(total=0, free=0)

    monkeypatch.setattr(storage.shutil, "disk_usage", usage)
    if failure == "cancelled":
        event.set()
    assert storage.read_volume_capacity("/", event)[1] is None


def test_blocked_drive_selection_keeps_one_worker_and_retires_old_result():
    entered, release = threading.Event(), threading.Event()
    threads, reads = [], []

    def reader(path, cancelled):
        threads.append(threading.get_ident())
        reads.append(path)
        if path == "old":
            entered.set()
            assert release.wait(3)
        volume = StorageVolume(path, path)
        return (volume,), VolumeCapacity(volume, 100, 40, 60, 1)

    owner = StorageCapacityOwner("old", reader=reader)
    try:
        owner.poll()
        assert entered.wait(2)
        for index in range(30):
            owner.select(f"new-{index}")
            assert owner.poll().capacity is None
        assert reads == ["old"]
        release.set()
        snapshot = wait(owner, lambda value: value.status == "ready")
        assert snapshot.capacity.volume.path == "new-29"
        assert reads == ["old", "new-29"]
        assert len(set(threads)) == 1 and threads[0] != threading.get_ident()
        owner.close()
        owner.select("retired")
        assert owner.poll().selected == "new-29"
    finally:
        release.set()
        owner.close()
        owner._worker._thread.join(2)


def test_refresh_is_rate_limited_and_errors_are_unavailable():
    reads, clock = [], [1.0]

    def reader(path, _):
        reads.append(path)
        raise OSError("offline")

    owner = StorageCapacityOwner("/", reader=reader, clock=lambda: clock[0])
    try:
        assert wait(owner, lambda state: state.status == "unavailable").capacity is None
        for _ in range(30):
            owner.poll()
        assert len(reads) == 1
        clock[0] += 31
        owner.poll()
        wait(owner, lambda _: len(reads) == 2 and not owner._worker.busy)
        assert len(reads) == 2
    finally:
        owner.close()
        owner._worker._thread.join(2)


def test_location_labels_preserve_identity_and_distinguish_unknown_and_duplicates():
    from yt_downloader.archive_paths import ArchivePath
    from yt_downloader.storage_labels import location_labels

    paths = tuple(
        map(
            ArchivePath.parse,
            (
                "/Users/me/Media",
                "/Volumes/Studio/Media",
                "/Volumes/NAS/Media",
                "/Volumes/Offline/Media",
                "Z:\\Media",
                "\\\\server\\share\\Media",
                "/Users/me/Other",
            ),
        )
    )
    volumes = (
        StorageVolume("/", "Macintosh HD", kind="local"),
        StorageVolume("/Volumes/Studio", "Studio", kind="external"),
        StorageVolume("/Volumes/NAS", "Studio", kind="network"),
    )
    labels = location_labels(paths, volumes)
    assert [item.path for item in labels] == list(paths)
    assert labels[0].title == labels[6].title == "Macintosh HD"
    assert labels[0].subtitle != labels[6].subtitle
    assert labels[1].title == labels[2].title == "Studio"
    assert labels[1].subtitle.startswith("External")
    assert labels[2].subtitle.startswith("Network")
    assert labels[3].title == "Offline" and labels[3].subtitle == "Type unknown"
    assert labels[4].subtitle == "Type unknown"
    assert labels[5].title == "share" and labels[5].subtitle == "Network"
    for label in labels:
        assert str(label.path) in label.tooltip and "\n" in label.tooltip


def test_mac_discovery_uses_real_volume_names_and_network_filesystem(monkeypatch):
    import psutil

    monkeypatch.setattr(storage.os, "name", "posix")
    monkeypatch.setattr(storage.sys, "platform", "darwin")
    monkeypatch.setattr(
        psutil,
        "disk_partitions",
        lambda **_: [
            SimpleNamespace(mountpoint="/Volumes/Studio", fstype="apfs"),
            SimpleNamespace(mountpoint="/Volumes/NAS", fstype="smbfs"),
            SimpleNamespace(mountpoint="/Volumes/Unknown", fstype="apfs"),
        ],
    )
    monkeypatch.setattr(
        storage,
        "_disk_info",
        lambda path: {
            "/": {"VolumeName": "Macintosh HD", "Internal": True},
            "/Volumes/Studio": {"VolumeName": "Client footage", "Internal": False},
        }.get(path, {}),
    )
    choices = storage.available_volumes(threading.Event())
    assert [(v.label, v.kind) for v in choices] == [
        ("Macintosh HD", "local"),
        ("NAS", "network"),
        ("Client footage", "external"),
        ("Unknown", "unknown"),
    ]


@pytest.mark.parametrize(
    "bus, expected",
    [
        ("USB", "external"),
        ("NVMe", "local"),
        ("iSCSI", "unknown"),
    ],
)
def test_windows_bus_classification_is_evidence_based(monkeypatch, bus, expected):
    from types import SimpleNamespace

    from yt_downloader import volume_storage

    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0, stdout=__import__("json").dumps({"Drive": "E", "Bus": bus})
        )

    monkeypatch.setattr(volume_storage.subprocess, "run", run)
    assert volume_storage._windows_fixed_drive_kinds() == {"E": expected}
    assert calls[0][1]["timeout"] == 3


def test_windows_bus_query_failure_keeps_kind_unknown(monkeypatch):
    from yt_downloader import volume_storage

    def fail(*_, **__):
        raise OSError("unavailable")

    monkeypatch.setattr(volume_storage.subprocess, "run", fail)
    assert volume_storage._windows_fixed_drive_kinds() == {}
