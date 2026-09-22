"""Regressions for shared precision input and nested viewport ownership."""

from types import SimpleNamespace

import pytest

from yt_downloader.ui_widgets import bind_smooth_vertical_wheel


class View:
    def __init__(self, master=None, first=0.5, last=0.6):
        self.tk = SimpleNamespace(call=lambda *_args: "")
        self.master = master
        self.first, self.last = first, last
        self.bindings = {}
        self.serial = 0

    def bind(self, sequence, callback, add=None):
        self.serial += 1
        token = str(self.serial)
        self.bindings.setdefault(sequence, {})[token] = callback
        return token

    def unbind(self, sequence, token=None):
        if token is None:
            self.bindings.pop(sequence, None)
        else:
            self.bindings.get(sequence, {}).pop(token, None)

    def event(self, sequence, **values):
        event = SimpleNamespace(widget=self, **values)
        for callback in tuple(self.bindings.get(sequence, {}).values()):
            if callback(event) == "break":
                return "break"

    def yview(self):
        return self.first, self.last

    def yview_moveto(self, fraction):
        extent = self.last - self.first
        self.first = max(0.0, min(1.0 - extent, fraction))
        self.last = self.first + extent

    def winfo_height(self):
        return 100

    def winfo_children(self):
        return []

    def winfo_toplevel(self):
        return self.master.winfo_toplevel() if self.master else self


def test_tiny_precision_motion_accumulates_without_minimum_one_pixel_per_event():
    view = View()
    bind_smooth_vertical_wheel(view)
    for _ in range(10):
        view.event("<MouseWheel>", delta=0.1, state=0)
    assert view.first == pytest.approx(0.499)


def test_nested_scroll_at_boundary_moves_parent_once():
    parent = View()
    child = View(parent, 0.0, 0.25)
    bind_smooth_vertical_wheel(parent)
    bind_smooth_vertical_wheel(child)
    child.event("<MouseWheel>", delta=12, state=0)
    assert child.first == 0
    assert parent.first == pytest.approx(0.488)


def test_rebinding_same_surface_replaces_owned_handlers():
    view = View()
    for _ in range(3):
        bind_smooth_vertical_wheel(view)
    assert len(view.bindings["<MouseWheel>"]) == 1
    view.event("<MouseWheel>", delta=120, state=0)
    assert view.first == pytest.approx(0.464)


def test_reader_lock_stays_with_log_until_actual_tail():
    view = View()
    bind_smooth_vertical_wheel(view)
    view.event("<MouseWheel>", delta=12, state=0)
    assert view._vodforge_user_scroll_locked is True
    view.yview_moveto(0.895)
    view.event("<MouseWheel>", delta=-12, state=0)
    assert view._vodforge_user_scroll_locked is False


def test_child_scroll_with_room_does_not_also_move_parent():
    parent = View()
    child = View(parent)
    bind_smooth_vertical_wheel(parent)
    bind_smooth_vertical_wheel(child)
    child.event("<MouseWheel>", delta=12, state=0)
    assert child.first == pytest.approx(0.488)
    assert parent.first == 0.5


def test_destroy_removes_owned_bindings_and_keeps_other_owner():
    view = View()
    unrelated = view.bind("<MouseWheel>", lambda event: None)
    bind_smooth_vertical_wheel(view)
    view.event("<Destroy>")
    assert list(view.bindings["<MouseWheel>"]) == [unrelated]
    assert view._vodforge_scroll_binding is None


def test_horizontal_view_uses_same_delta_and_preserves_vertical_position():
    from yt_downloader.ui_scrolling import bind_smooth_scroll

    view = View()
    view.xfirst, view.xlast = 0.2, 0.4
    view.xview = lambda: (view.xfirst, view.xlast)

    def move(fraction):
        view.xfirst, view.xlast = fraction, fraction + 0.2

    view.xview_moveto = move
    view.winfo_width = lambda: 200
    bind_smooth_scroll(view, axis="both")
    view.event("<MouseWheel>", delta=-120, state=1)
    assert view.xfirst == pytest.approx(0.236)
    assert view.first == 0.5


def test_precise_two_axis_input_routes_each_axis_once():
    from yt_downloader.ui_scrolling import bind_smooth_scroll

    parent = View()
    parent.xfirst, parent.xlast = 0.2, 0.4
    parent.xview = lambda: (parent.xfirst, parent.xlast)

    def move(fraction):
        parent.xfirst, parent.xlast = fraction, fraction + 0.2

    parent.xview_moveto = move
    parent.winfo_width = lambda: 200
    child = View(parent)
    child.tk = SimpleNamespace(
        call=lambda *args: (-10, 12) if args[0] == "tk::PreciseScrollDeltas" else ""
    )
    bind_smooth_scroll(parent, axis="both")
    bind_smooth_vertical_wheel(child)
    child.event("<TouchpadScroll>", delta=123)
    assert child.first == pytest.approx(0.488)
    assert parent.first == 0.5
    assert parent.xfirst == pytest.approx(0.21)


def test_fractional_scroll_intent_locks_live_reader_before_first_pixel():
    view = View()
    bind_smooth_vertical_wheel(view)
    view.event("<MouseWheel>", delta=0.1, state=0)
    assert view.first == 0.5
    assert view._vodforge_user_scroll_locked is True


def test_dynamic_children_release_bindings_without_accumulating_dead_widgets():
    parent = View()
    bind_smooth_vertical_wheel(parent)
    binding = parent._vodforge_scroll_binding
    baseline = len(binding._bindings)
    for _ in range(30):
        child = View(parent)
        binding._mapped(SimpleNamespace(widget=child))
        child.event("<Destroy>")
        assert child not in binding._targets
    assert len(binding._bindings) == baseline


@pytest.mark.parametrize("parent_first", [True, False])
def test_horizontal_header_precision_policy_is_independent_of_binding_order(
    parent_first,
):
    from yt_downloader.ui_scrolling import bind_smooth_scroll

    parent, child = View(), View()
    child.master = parent
    header = View(child)
    child.xfirst, child.xlast = 0.2, 0.4
    child.xview = lambda: (child.xfirst, child.xlast)

    def move(fraction):
        child.xfirst, child.xlast = fraction, fraction + 0.2

    child.xview_moveto = move
    child.winfo_width = lambda: 200
    child.tk = SimpleNamespace(
        call=lambda *args: (-10, -12) if args[0] == "tk::PreciseScrollDeltas" else ""
    )
    if parent_first:
        bind_smooth_scroll(parent)
        parent._vodforge_scroll_binding._mapped(SimpleNamespace(widget=header))
    bind_smooth_scroll(child, child, header, axis="both", horizontal_targets=(header,))
    if not parent_first:
        bind_smooth_scroll(parent)
    header.event("<TouchpadScroll>", delta=123)
    assert child.xfirst == pytest.approx(0.21)
    assert child.first == 0.5
    assert parent.first == 0.5


def test_upward_reader_intent_at_non_scrollable_boundary_survives_live_append():
    view = View(first=0, last=1)
    bind_smooth_vertical_wheel(view)
    view.event("<MouseWheel>", delta=0.1, state=0)
    assert view._vodforge_user_scroll_locked is True
    view.event("<MouseWheel>", delta=-0.1, state=0)
    assert view._vodforge_user_scroll_locked is False


def test_row_remainder_does_not_survive_boundary_forwarding_and_reversal():
    parent = View()
    child = View(parent)
    child.yview_scroll = lambda rows, units: child.yview_moveto(
        child.first + rows * 0.024
    )
    bind_smooth_vertical_wheel(parent)
    bind_smooth_vertical_wheel(child, mode="rows", row_pixels=24)
    binding = child._vodforge_scroll_binding
    binding.scroll(0, 12)
    child.yview_moveto(0.9)
    binding.scroll(0, 12)
    binding.scroll(0, -24)
    assert child.first == pytest.approx(0.876)


@pytest.mark.parametrize("mapped", [False, True])
def test_scroller_and_explicit_sibling_both_receive_same_owner_before_after_map(mapped):
    from yt_downloader.ui_scrolling import ScrollBinding

    parent = View()
    scroller, scrollbar = View(parent), View(parent)
    ScrollBinding(parent)
    binding = ScrollBinding(scroller, scrollbar)
    if mapped:
        binding._mapped(SimpleNamespace(widget=scroller))
        binding._mapped(SimpleNamespace(widget=scroller))
    assert len(scroller.bindings.get("<MouseWheel>", {})) == 1
    assert scroller.event("<MouseWheel>", delta=12, state=0) == "break"
    assert scroller.first == pytest.approx(0.488)
    assert parent.first == 0.5
    assert scrollbar.event("<MouseWheel>", delta=12, state=0) == "break"
    assert scroller.first == pytest.approx(0.476)
    assert parent.first == 0.5


def test_explicit_target_reassignment_and_close_release_only_owned_bindings():
    from yt_downloader.ui_scrolling import ScrollBinding

    parent = View()
    scrollbar = View(parent)
    foreign = scrollbar.bind("<MouseWheel>", lambda event: None)
    first, second = View(parent), View(parent)
    a = ScrollBinding(first, scrollbar)
    b = ScrollBinding(second, scrollbar)
    assert scrollbar not in a._targets
    assert len(scrollbar.bindings["<MouseWheel>"]) == 2
    scrollbar.event("<MouseWheel>", delta=12, state=0)
    assert first.first == 0.5 and second.first == pytest.approx(0.488)
    b.close()
    assert scrollbar._vodforge_scroll_input_binding is None
    assert list(scrollbar.bindings["<MouseWheel>"]) == [foreign]


def test_unsupported_optional_touchpad_preserves_wheel_and_registers_no_command():
    import tkinter as tk

    from yt_downloader.ui_scrolling import ScrollBinding

    view = View()

    def unsupported(*args):
        if len(args) == 4 and args[2] == "<TouchpadScroll>" and args[3]:
            raise tk.TclError('bad event type or keysym "TouchpadScroll"')
        return ""

    view.tk = SimpleNamespace(call=unsupported)
    binding = ScrollBinding(view)
    assert "<TouchpadScroll>" not in view.bindings
    view.event("<MouseWheel>", delta=120, state=0)
    assert view.first == pytest.approx(0.464)
    binding.close()
    assert all(not values for values in view.bindings.values())
