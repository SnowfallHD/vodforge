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
                if HIGHLIGHTS[index].key != "activity-mode":
                    assert panel.photo is not None
                image = panel.photo
                panel.render(index)
                root.update()
                assert panel.photo is image
                assert panel.frame.winfo_toplevel() is root
                assert root.grab_current() is panel.frame
                for widget in (*panel.controls, panel.description):
                    assert widget.winfo_ismapped()
                    assert (
                        widget.winfo_rooty() + widget.winfo_height()
                        <= panel.frame.winfo_rooty() + panel.frame.winfo_height()
                    )
                assert panel.preview.winfo_height() > 100
                if HIGHLIGHTS[index].key == "activity-mode":
                    demo = panel.activity_demo
                    assert demo is not None and demo.timer is not None
                    assert panel.preview.itemcget(panel.image_item, "image") == ""
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
