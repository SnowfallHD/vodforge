"""The real window-manager adapter preserves native fallback and ownership."""

import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.platforms.macos import windowing as window_chrome
from yt_downloader.platforms.macos.windowing import integrate_main_window


@pytest.fixture(autouse=True)
def native_peer(monkeypatch):
    peer = Mock()
    monkeypatch.setattr(window_chrome, "_native_window", lambda _: peer)
    monkeypatch.setattr(window_chrome, "_install_header_toolbar", Mock())
    return peer


def window(system="aqua"):
    result = Mock()
    result.tk = SimpleNamespace(
        call=Mock(return_value=system),
        splitlist=lambda value: tuple(value),
    )
    result.attributes.return_value = (
        "titled",
        "closable",
        "miniaturizable",
        "resizable",
    )
    return result


def test_supported_mac_preserves_native_controls_and_accessible_title(native_peer):
    target = window()
    assert integrate_main_window(target, "VODForge", Mock())
    assert set(target.attributes.call_args.args[1]) == {
        "titled",
        "closable",
        "miniaturizable",
        "resizable",
        "fullsizecontentview",
    }
    target.title.assert_called_once_with("VODForge")
    native_peer.setTitleVisibility_.assert_called_once_with(1)


def test_older_tk_keeps_visible_title_and_reports_fallback_once():
    target = window()
    target.attributes.side_effect = tk.TclError("unknown attribute")
    diagnostic = Mock()
    assert not integrate_main_window(target, "VODForge", diagnostic)
    target.title.assert_called_once_with("VODForge")
    target.iconname.assert_not_called()
    diagnostic.assert_called_once()


def test_rejected_fullsize_style_does_not_hide_the_native_title():
    target = window()
    target.attributes.side_effect = [("titled", "closable"), tk.TclError("unsupported")]
    assert not integrate_main_window(target, "VODForge", Mock())
    target.title.assert_called_once_with("VODForge")


def test_other_platform_never_calls_mac_style_attributes():
    for system in ("win32", "x11"):
        target = window(system)
        assert not integrate_main_window(target, "VODForge", Mock())
        target.attributes.assert_not_called()
        target.title.assert_called_once_with("VODForge")


def test_existing_fullsize_style_is_not_duplicated():
    target = window()
    target.attributes.return_value = ("titled", "fullsizecontentview", "resizable")
    assert integrate_main_window(target, "VODForge", Mock())
    assert target.attributes.call_args.args[1].count("fullsizecontentview") == 1


def test_stale_setup_geometry_cannot_collapse_mapped_header_or_resize_observation():
    from yt_downloader.app import DownloaderApp

    target = SimpleNamespace(
        winfo_width=lambda: 1414,
        winfo_height=lambda: 1008,
        _apply_focus_layout=Mock(),
    )
    event = SimpleNamespace(widget=target, width=1, height=1)
    DownloaderApp._schedule_focus_layout(target, event)
    target._apply_focus_layout.assert_called_once_with(width=1414, height=1008)
    assert target._resize_observed_geometry == (1414, 1008)


def test_live_resize_event_remains_authoritative_before_tk_size_catches_up():
    from yt_downloader.app import DownloaderApp

    target = SimpleNamespace(
        winfo_width=lambda: 1414,
        winfo_height=lambda: 1008,
        _apply_focus_layout=Mock(),
    )
    event = SimpleNamespace(widget=target, width=980, height=780)
    DownloaderApp._schedule_focus_layout(target, event)
    target._apply_focus_layout.assert_called_once_with(width=980, height=780)
    assert target._resize_observed_geometry == (980, 780)


def test_unavailable_native_peer_keeps_standard_window(monkeypatch):
    def unavailable(_):
        raise RuntimeError("No native view")

    monkeypatch.setattr(window_chrome, "_native_window", unavailable)
    target = window()
    assert not integrate_main_window(target, "VODForge", Mock())
    assert target.attributes.call_count == 1
    target.title.assert_called_once_with("VODForge")


def test_visual_title_failure_restores_original_style_and_keeps_name(native_peer):
    native_peer.setTitleVisibility_.side_effect = RuntimeError("Rejected")
    target = window()
    original = target.attributes.return_value
    assert not integrate_main_window(target, "VODForge", Mock())
    target.attributes.assert_called_with("-stylemask", original)
    target.title.assert_called_once_with("VODForge")


def test_supported_native_header_uses_owned_appkit_toolbar_layout(native_peer):
    target = window()
    assert integrate_main_window(target, "VODForge", Mock())
    window_chrome._install_header_toolbar.assert_called_once_with(native_peer)
    assert target._native_toolbar_header is True


@pytest.mark.parametrize("rollback_rejected", [False, True])
def test_toolbar_failure_keeps_integrated_style_and_native_controls(
    monkeypatch, native_peer, rollback_rejected
):
    if rollback_rejected:
        native_peer.setToolbar_.side_effect = RuntimeError("rollback unavailable")
    monkeypatch.setattr(
        window_chrome,
        "_install_header_toolbar",
        Mock(side_effect=RuntimeError("unavailable")),
    )
    target = window()
    diagnostic = Mock()
    assert integrate_main_window(target, "VODForge", diagnostic)
    assert target._native_toolbar_header is False
    native_peer.setToolbar_.assert_called_once_with(None)
    assert diagnostic.call_count == (2 if rollback_rejected else 1)


def test_other_platform_does_not_install_header_toolbar():
    target = window("win32")
    assert not integrate_main_window(target, "VODForge", Mock())
    window_chrome._install_header_toolbar.assert_not_called()
    assert target._native_toolbar_header is False
