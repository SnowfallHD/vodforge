"""Bounded owned-window raster and transition evidence for shared navigation."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from PIL import ImageChops

from tests.test_archive_native import pump, seed
from tests.test_native_thumbnail_rendering import application as _application
from yt_downloader.platform_services import capture_own_widget
from yt_downloader.ui_theme import THEME

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Native display required",
)


def _digest(image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def test_owned_navigation_hover_and_tab_transition(application, tmp_path):
    """Record real owned pixels; never infer a transition from test callbacks."""
    app = application
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    app.geometry("1200x760+80+80")
    seed(app, tmp_path, count=1)
    app._select_focus_view("forge")
    pump(app, 0.25)

    nav = app._focus_nav_buttons["library"]
    nav_idle = capture_own_widget(nav).convert("RGB")
    nav.state(["active"])
    pump(app, 0.08)
    nav_hover = capture_own_widget(nav).convert("RGB")
    # A raised resting face changes its edge shadow on hover. The rounded
    # outside corner, not a point inside that shadow, must retain the backdrop.
    quiet = (0, 0)
    assert (
        max(
            abs(after - before)
            for before, after in zip(
                nav_idle.getpixel(quiet), nav_hover.getpixel(quiet), strict=True
            )
        )
        <= 1
    )
    assert ImageChops.difference(nav_idle, nav_hover).getbbox() is not None
    nav.state(["!active"])

    app._select_focus_view("library")
    pump(app, 0.3)
    sidebar = app.library_scene.sidebar
    bounds, _action = app.library_scene._sidebar_targets[1]
    sidebar_idle = capture_own_widget(sidebar).convert("RGB")
    x, y = bounds[0] + 42, (bounds[1] + bounds[3]) // 2
    sidebar.event_generate("<Motion>", x=x, y=y)
    pump(app, 0.08)
    sidebar_hover = capture_own_widget(sidebar).convert("RGB")
    assert sidebar_idle.getpixel((x, y)) == sidebar_hover.getpixel((x, y))
    assert ImageChops.difference(sidebar_idle, sidebar_hover).getbbox() is not None
    assert not sidebar.find_withtag("pointer-state")
    sidebar.event_generate("<Leave>")

    transitions = []
    for target in ("library", "watch", "activity", "forge"):
        before = capture_own_widget(app).convert("RGB")
        started = time.monotonic()
        app._select_focus_view(target)
        pump(app, 0.22)
        after = capture_own_widget(app).convert("RGB")
        assert app._view_transition._overlay is None
        assert app._focus_views[target].winfo_ismapped()
        transitions.append(
            {
                "target": target,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "before_sha256": _digest(before),
                "after_sha256": _digest(after),
                "paint_status": getattr(app, "_vodforge_transition_paint_status", None),
            }
        )
        before.save(out / f"transition-{target}-before.png")
        after.save(out / f"transition-{target}-after.png")

    nav_idle.save(out / "navigation-idle.png")
    nav_hover.save(out / "navigation-hover.png")
    sidebar_idle.save(out / "sidebar-idle.png")
    sidebar_hover.save(out / "sidebar-hover.png")
    (out / "hover-transition-receipt.json").write_text(
        json.dumps(
            {
                "owned_window": str(app),
                "selected_material_owner": type(
                    app._focus_nav_buttons["forge"]
                ).__name__,
                "selected": app._focus_nav_buttons["forge"].cget("selected"),
                "expected_selection": THEME["selection"],
                "transitions": transitions,
                "scope": "owned native fixture; captures are settled before/after, not display-refresh sampling",
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("surface", ["library", "watch", "rail"])
def test_actual_scene_keyboard_focus_uses_recessed_material(
    application, tmp_path, surface
):
    from tests.test_matte_native import save_native_capture

    app = application
    seed(app, tmp_path, count=9)
    app.geometry("1180x760+40+40")
    app._select_focus_view("library" if surface == "library" else "watch")
    pump(app, 0.3)
    if surface == "library":
        canvas = app.library_scene.canvas
    elif surface == "watch":
        canvas = app.focus_watch.canvas
    else:
        rails = list(app.focus_watch._scene_rails.values())
        assert rails
        canvas = rails[0].canvas
    app.focus_force()
    pump(app, 0.1)
    canvas.focus_force()
    pump(app, 0.1)
    canvas.event_generate("<Right>")
    pump(app, 0.1)
    assert app.focus_get() is canvas
    focus = canvas.find_withtag("keyboard-focus")
    material_owner = getattr(canvas, "_action_material", None)
    assert (focus and all(canvas.type(item) == "image" for item in focus)) or (
        material_owner and material_owner.focused
    )
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    bitmap = save_native_capture(canvas, out / f"{surface}-focused.png")
    if material_owner is not None and material_owner.focused is not None:
        box = material_owner.focused
        sx, sy = (
            bitmap.width / canvas.winfo_width(),
            bitmap.height / canvas.winfo_height(),
        )
        x, y = canvas.canvasx(0), canvas.canvasy(0)
        bitmap.crop(
            (
                round((box[0] - x) * sx),
                round((box[1] - y) * sy),
                round((box[2] - x) * sx),
                round((box[3] - y) * sy),
            )
        ).save(out / f"{surface}-action-focus-crop.png")
        (out / f"{surface}-action-focus.json").write_text(
            json.dumps(
                {
                    "bounds": box,
                    "owner_focus": material_owner.focused,
                    "active_state": str(material_owner.active),
                    "backing_ratio": [sx, sy],
                    "extra_focus_overlay_items": len(focus),
                },
                indent=2,
            )
        )
    app.focus_force()
    pump(app, 0.1)
    assert not canvas.find_withtag("keyboard-focus")
    assert material_owner is None or material_owner.focused is None
