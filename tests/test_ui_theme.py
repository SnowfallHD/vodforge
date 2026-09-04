from __future__ import annotations

import pytest

from yt_downloader.ui_theme import (
    CUSTOM_THEME_NAME,
    DEFAULT_THEME_NAME,
    THEME,
    ThemeRenderOwner,
    apply_theme_selection,
    normalize_hex_color,
)


@pytest.fixture(autouse=True)
def _restore_default_theme():
    yield
    apply_theme_selection(DEFAULT_THEME_NAME)


def test_preset_theme_applies_complete_curated_palette() -> None:
    selection = apply_theme_selection("Jade", "#ffffff")

    assert selection.name == "Jade"
    assert THEME["accent"] == "#42d69b"
    assert THEME["bg"] == "#070b0a"
    assert THEME["accent_surface"] == "#1a3c2f"


def test_custom_accent_is_validated_and_darken_pair_is_derived() -> None:
    selection = apply_theme_selection(CUSTOM_THEME_NAME, "#80a0ff")

    assert selection.custom_accent == "#80a0ff"
    assert THEME["accent"] == "#80a0ff"
    assert THEME["accent_dark"] == "#647dc7"
    assert THEME["accent_surface"] == "#262d42"
    assert normalize_hex_color("not-a-color") == "#7170ff"


def test_unknown_theme_falls_back_without_leaking_partial_state() -> None:
    selection = apply_theme_selection("unknown", "bad")

    assert selection.name == DEFAULT_THEME_NAME
    assert THEME["accent"] == "#7170ff"


def test_live_theme_owner_renders_only_changed_valid_snapshots() -> None:
    renders: list[str] = []
    owner = ThemeRenderOwner(
        lambda _previous, _incoming: renders.append(THEME["accent"])
    )

    assert owner.request(DEFAULT_THEME_NAME, "#7170ff") is False
    assert owner.request("Jade", "#7170ff") is True
    assert owner.request("Jade", "#7170ff") is False
    assert renders == ["#42d69b"]


def test_live_custom_theme_waits_for_complete_hex_color() -> None:
    renders: list[str] = []
    owner = ThemeRenderOwner(
        lambda _previous, _incoming: renders.append(THEME["accent"])
    )

    assert owner.request(CUSTOM_THEME_NAME, "#12") is False
    assert owner.request(CUSTOM_THEME_NAME, "#123456") is True
    assert renders == ["#123456"]
