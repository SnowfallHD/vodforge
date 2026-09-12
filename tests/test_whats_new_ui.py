import os
import tkinter as tk

import pytest

from yt_downloader.whats_new import HIGHLIGHTS
from yt_downloader.whats_new_ui import WhatsNewPanel

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="requires native Tcl/Tk"
)


def test_carousel_native_child_resize_noop_and_dismissal():
    root = tk.Tk()
    root.geometry("1180x780")
    root.update()
    dismissed = []
    panel = WhatsNewPanel(root, HIGHLIGHTS, lambda: dismissed.append(True))
    try:
        for geometry in ("1180x780", "860x600"):
            root.geometry(geometry)
            root.update()
            dimensions = None
            for index in range(len(HIGHLIGHTS)):
                panel.render(index)
                root.update()
                current = (
                    panel.frame.winfo_width(),
                    panel.frame.winfo_height(),
                    panel.preview.winfo_width(),
                    panel.preview.winfo_height(),
                )
                if dimensions is None:
                    dimensions = current
                assert current == dimensions
                assert panel.activity_demo is not None
                assert (
                    not panel.preview.find_all()
                )  # No screenshot layer behind native widgets.
                image = panel.activity_demo
                panel.render(index)
                root.update()
                assert panel.activity_demo is image
                assert panel.frame.winfo_toplevel() is root
                assert root.grab_current() is panel.frame
                for widget in (*panel.controls, panel.description):
                    assert widget.winfo_ismapped()
                    assert (
                        widget.winfo_rooty() + widget.winfo_height()
                        <= panel.frame.winfo_rooty() + panel.frame.winfo_height()
                    )
                assert panel.preview.winfo_height() > 100
                if HIGHLIGHTS[index].key == "output-settings":
                    from yt_downloader.export_planning import (
                        EXPORT_MODES,
                        export_mode_description,
                    )

                    demo = panel.activity_demo
                    for choice in EXPORT_MODES:
                        demo.variables[0].set(choice)
                        root.update()
                        labels = [
                            w
                            for w in demo.winfo_children()
                            if w.winfo_class() == "TLabel"
                        ]
                        assert export_mode_description(choice) in [
                            w.cget("text") for w in labels
                        ]

                if HIGHLIGHTS[index].key == "activity-mode":
                    demo = panel.activity_demo
                    assert demo is not None and demo.timer is not None
                    assert not panel.preview.find_all()
                    assert not hasattr(demo, "control")
        assert panel.next.winfo_width() == panel.next.winfo_height() == 34
        assert panel.next.instate(["disabled"])
        assert panel.back.winfo_width() == panel.back.winfo_height() == 34
        panel.frame.focus_force()
        root.update()
        panel.frame.event_generate("<Escape>")
        root.update()
        panel.close()
        assert dismissed == [True]
        assert root.grab_current() is None
    finally:
        panel.close(acknowledge=False)
        root.destroy()


def test_output_settings_try_it_releases_modal_before_opening_settings():
    from yt_downloader.whats_new import WhatsNewOwner

    root = tk.Tk()
    root.geometry("1180x780")
    seen = tk.StringVar(root)
    opened = []
    owner = WhatsNewOwner(
        root,
        seen,
        lambda: True,
        mode="whats-new",
        open_settings=lambda: opened.append(root.grab_current()),
    )
    try:
        owner.show()
        root.update()
        panel = owner.panel
        for geometry in ("1180x780", "860x600"):
            root.geometry(geometry)
            root.update()
            assert panel.finish_button.cget("text") == "Try it"
            assert panel.finish_button.winfo_ismapped()
            assert not any(
                w.winfo_ismapped() for w in (panel.page, panel.back, panel.next)
            )
            assert (
                abs(
                    panel.finish_button.winfo_rootx()
                    + panel.finish_button.winfo_width() / 2
                    - panel.frame.winfo_rootx()
                    - panel.frame.winfo_width() / 2
                )
                < 3
            )
        panel.finish_button.invoke()
        root.update()
        assert opened == [None]
        assert not owner.pending
        assert owner.panel is None
    finally:
        owner.close()
        root.destroy()
