"""The shared matte owner must leave unchanged native canvas items alone."""

from types import SimpleNamespace

import yt_downloader.ui_materials as materials


def test_backdrop_repositions_only_on_actual_scene_motion(monkeypatch):
    palette = ["violet"]
    photo = object()
    root = SimpleNamespace(_matte_texture=("violet", photo))
    calls = []

    class Canvas:
        _items = (7,)

        def winfo_toplevel(self):
            return root

        def type(self, _item):
            return "image"

        def winfo_width(self):
            return 240

        def winfo_rootx(self):
            return 10

        def winfo_rooty(self):
            return 20

        def configure(self, **kwargs):
            calls.append(("configure", kwargs))

        def create_image(self, *args, **kwargs):
            calls.append(("create", args, kwargs))
            return 7

        def itemconfigure(self, *args, **kwargs):
            calls.append(("itemconfigure", args, kwargs))

        def coords(self, *args):
            calls.append(("coords", args))

        def tag_lower(self, *args):
            calls.append(("lower", args))
            self._items = (7, 8)

        def find_all(self):
            return self._items

    anchor = SimpleNamespace(x=10, width=240, y=20)
    anchor.winfo_rootx = lambda: anchor.x
    anchor.winfo_rooty = lambda: anchor.y
    anchor.winfo_width = lambda: anchor.width
    canvas = Canvas()
    canvas._matte_anchor = anchor
    monkeypatch.setattr(materials, "theme_palette_snapshot", lambda: palette[0])
    owner = object.__new__(materials.MatteBackdrop)
    owner.canvas = canvas
    owner.photo = None
    owner.item = None
    owner.identity = None
    owner.position = None
    owner.builds = 0

    owner.draw()
    first_count = len(calls)
    assert owner.position == (240, 0)
    assert owner.builds == 1
    owner.draw()
    assert len(calls) == first_count

    # The shared field renderer may lower its face after the matte was made.
    canvas._items = (8, 7)
    owner.draw()
    assert calls[-1] == ("lower", (7,))
    first_count = len(calls)

    anchor.x += 20
    owner.draw()
    assert calls[first_count:] == [("coords", (7, 260, 0))]
    owner.draw()
    assert len(calls) == first_count + 1

    palette[0] = "cobalt"
    root._matte_texture = ("cobalt", object())
    owner.draw()
    assert owner.builds == 2
    assert any(call[0] == "itemconfigure" for call in calls[first_count + 1 :])
