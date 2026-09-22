"""Running-app acceptance of shared navigation; isolated fixture profile."""

from __future__ import annotations

import os
import tkinter as tk

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native display required",
)


@pytest.mark.parametrize(
    ("label", "kind"), [("Help and feedback", "feedback"), ("Rate VODForge", "review")]
)
def test_gear_menu_directly_opens_requested_panel(
    application, monkeypatch, label, kind
):
    app = application
    observed = []

    def invoke(menu, *_args):
        labels = [
            menu.entrycget(i, "label")
            for i in range(menu.index("end") + 1)
            if menu.type(i) != "separator"
        ]
        observed.append(labels)
        assert labels[labels.index("Help and feedback") + 1] == "Rate VODForge"
        assert "Welcome tour" in labels
        index = next(
            i
            for i in range(menu.index("end") + 1)
            if menu.type(i) != "separator" and menu.entrycget(i, "label") == label
        )
        menu.invoke(index)

    monkeypatch.setattr(tk.Menu, "tk_popup", invoke)
    app._show_application_menu()
    pump(app, 0.3)
    assert len(observed) == 1
    assert app.engagement.panel is not None and app.engagement.panel.kind == kind
    assert app.engagement.panel.frame.winfo_viewable()
    app.engagement.panel.close(force=True)
    pump(app, 0.1)
    assert app.engagement.panel is None


def test_rapid_top_tabs_and_within_watch_navigation_retire_obsolete_reveals(
    application,
):
    app = application
    for route in ("library", "watch", "forge", "watch", "activity", "watch"):
        app._select_focus_view(route)
        pump(app, 0.035)
        transition = app._view_transition
        assert (
            transition._target is None or transition._target is app._focus_views[route]
        )
    watch = app.focus_watch
    watch._scene_open("videos")
    assert transition._overlay is None and transition._timer is None
    watch._scene_open("channels")
    assert transition._overlay is None and transition._timer is None
    watch._scene_back()
    pump(app, 0.2)
    assert watch._scene_route == "videos"
    assert transition._overlay is None and transition._image is None
    assert not app.__dict__.get("_archive_overlay")
