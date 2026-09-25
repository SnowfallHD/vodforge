from pathlib import Path

from quality_harness.theme_contract import (
    family_material_bypasses,
    theme_default_bypasses,
)


def test_import_time_theme_capture_is_detected():
    assert theme_default_bypasses('def widget(color=THEME["accent"]): pass') == [1]
    assert (
        theme_default_bypasses('def widget(color=None): color=color or THEME["accent"]')
        == []
    )


def test_local_face_clone_is_detected():
    assert family_material_bypasses(
        "draw.rounded_rectangle((0,0,30,30), fill=color)"
    ) == [1]
    assert (
        family_material_bypasses("ttk_surface_image(30, fill=color, edge=edge)") == []
    )


def test_product_controls_do_not_freeze_theme_defaults():
    root = Path(__file__).resolve().parents[2]
    for path in (root / "yt_downloader").glob("*.py"):
        assert theme_default_bypasses(path.read_text(encoding="utf-8")) == [], path.name


def test_control_adapters_have_no_private_raster_face_clones():
    root = Path(__file__).resolve().parents[2]
    for name in (
        "ui_widgets.py",
        "scene_components.py",
        "ui_button_contract.py",
        "ui_context_menu.py",
        "media_player_ui.py",
    ):
        assert (
            family_material_bypasses(
                (root / "yt_downloader" / name).read_text(encoding="utf-8")
            )
            == []
        ), name
