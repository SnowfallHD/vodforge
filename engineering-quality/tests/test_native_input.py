import json
import sys
from types import SimpleNamespace

import pytest
from quality_harness import native_input


@pytest.mark.parametrize("size", [(1180, 808), (2360, 1616), (1122, 768.0)])
def test_image_coordinates_preserve_desktop_target_across_retina_and_resizing(size):
    bounds = {"X": -1440, "Y": 30, "Width": 1180, "Height": 808}
    assert native_input.image_point(bounds, size[0] / 2, size[1] / 2, *size) == (
        -850,
        434,
    )


@pytest.mark.parametrize("point", [(-1, 0), (100, 0), (0, 100), (float("nan"), 0)])
def test_click_outside_observed_image_is_rejected(point):
    with pytest.raises(ValueError):
        native_input.image_point(
            {"X": 0, "Y": 0, "Width": 100, "Height": 100}, *point, 100, 100
        )


class Quartz:
    kCGEventMouseMoved = 1
    kCGEventLeftMouseDown = 2
    kCGEventLeftMouseUp = 3
    kCGMouseButtonLeft = 0
    kCGMouseEventClickState = 0
    kCGHIDEventTap = 0

    def __init__(self):
        self.events = []

    def CGEventCreateMouseEvent(self, source, kind, point, button):
        return {"kind": kind, "flags": 1 << 20}

    def CGEventCreateKeyboardEvent(self, source, code, down):
        return {"kind": "key", "down": down, "flags": 1 << 20}

    def CGEventSetFlags(self, event, flags):
        event["flags"] = flags

    def CGEventKeyboardSetUnicodeString(self, event, length, text):
        event["unicode"] = (length, text)

    def CGEventSetIntegerValueField(self, *args):
        pass

    def CGEventPost(self, tap, event):
        self.events.append(event)


def test_shortcut_releases_modifier_and_next_click_never_inherits_command(monkeypatch):
    monkeypatch.setattr(native_input.time, "sleep", lambda _: None)
    quartz = Quartz()
    native_input.post_key(quartz, 9, 1 << 20, lambda: None)
    native_input.post_click(quartz, (10, 10), lambda: None)
    assert quartz.events[0]["flags"] == 1 << 20
    assert all(event["flags"] == 0 for event in quartz.events[1:])


def test_click_releases_button_even_when_mouse_down_opens_another_window(monkeypatch):
    monkeypatch.setattr(native_input.time, "sleep", lambda _: None)
    quartz = Quartz()

    def guard():
        if any(e["kind"] == quartz.kCGEventLeftMouseDown for e in quartz.events):
            raise RuntimeError("New dialog has focus")

    native_input.post_click(quartz, (10, 10), guard)
    assert quartz.events[-1]["kind"] == quartz.kCGEventLeftMouseUp


def test_unicode_typing_preserves_non_bmp_characters_and_clears_modifiers(monkeypatch):
    monkeypatch.setattr(native_input.time, "sleep", lambda _: None)
    quartz = Quartz()
    native_input.post_text(quartz, "A🚀", lambda: None)
    assert [e["unicode"] for e in quartz.events] == [
        (1, "A"),
        (1, "A"),
        (2, "🚀"),
        (2, "🚀"),
    ]
    assert all(e["flags"] == 0 for e in quartz.events)


def test_partial_typing_retains_dispatch_fact_when_focus_changes(monkeypatch):
    monkeypatch.setattr(native_input.time, "sleep", lambda _: None)
    quartz = Quartz()
    dispatched = []

    def guard():
        if quartz.events:
            raise RuntimeError("Focus changed")

    with pytest.raises(RuntimeError, match="Focus changed"):
        native_input.post_text(quartz, "ab", guard, lambda: dispatched.append(True))
    assert dispatched
    assert len(quartz.events) == 2


def test_foreground_change_before_mouse_down_sends_no_press(monkeypatch):
    monkeypatch.setattr(native_input.time, "sleep", lambda _: None)
    quartz = Quartz()

    def guard():
        if quartz.events:
            raise RuntimeError("Foreground changed")

    with pytest.raises(RuntimeError, match="Foreground changed"):
        native_input.post_click(quartz, (10, 10), guard)
    assert [e["kind"] for e in quartz.events] == [quartz.kCGEventMouseMoved]


def test_window_transition_waits_for_observation_and_times_out_without_retry(
    monkeypatch,
):
    clock = SimpleNamespace(now=0)
    monkeypatch.setattr(native_input.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(
        native_input.time,
        "sleep",
        lambda delay: setattr(clock, "now", clock.now + delay),
    )
    assert native_input.wait_for(lambda: clock.now >= 0.2, "window") is True
    with pytest.raises(RuntimeError, match="no retry sent"):
        native_input.wait_for(lambda: False, "missing window", timeout=0.1)


@pytest.mark.parametrize("wrong_focus", [False, True])
def test_real_dispatch_path_refuses_occlusion_or_wrong_window_without_sending_input(
    monkeypatch, tmp_path, wrong_focus
):
    quartz = Quartz()
    quartz.kCGWindowListOptionOnScreenOnly = 1
    quartz.CGWindowListCopyWindowInfo = lambda *args: [
        {
            "kCGWindowOwnerPID": 10,
            "kCGWindowLayer": 0,
            "kCGWindowName": "QA main",
            "kCGWindowNumber": 20,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 100, "Height": 100},
        }
    ]
    app = SimpleNamespace(
        activateWithOptions_=lambda _: True, processIdentifier=lambda: 10
    )
    appkit = SimpleNamespace(
        NSRunningApplication=SimpleNamespace(
            runningApplicationWithProcessIdentifier_=lambda _: app
        ),
        NSApplicationActivateIgnoringOtherApps=1,
        NSWorkspace=SimpleNamespace(
            sharedWorkspace=lambda: SimpleNamespace(frontmostApplication=lambda: app)
        ),
    )
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setattr(
        native_input, "verify_live_launch", lambda _: {"verified": True}
    )
    monkeypatch.setattr(
        native_input, "verify_native_window_identity", lambda **_: {"verified": True}
    )
    monkeypatch.setattr(
        native_input,
        "focused_window_title",
        lambda _: "Alert" if wrong_focus else "QA main",
    )
    monkeypatch.setattr(native_input, "hit_test_pid", lambda _: 99)
    monkeypatch.setattr(native_input.subprocess, "run", lambda *args, **kwargs: None)
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps({"driver_ready": True, "current_launch": {"pid": 10}})
    )
    output = tmp_path / "input.json"
    with pytest.raises(
        RuntimeError, match="keyboard focus" if wrong_focus else "blocked by desktop"
    ):
        native_input.main(
            [
                "--session",
                str(session),
                "--window-title",
                "QA main",
                "--output",
                str(output),
                "click",
                "--x",
                "10",
                "--y",
                "10",
                "--image-width",
                "100",
                "--image-height",
                "100",
            ]
        )
    assert quartz.events == []
    receipt = json.loads(output.read_text())
    assert receipt["input_sent"] is False
    assert receipt["status"] == "failed"


@pytest.mark.parametrize("mismatch", [None, "pid", "bounds", "duplicate", "no_sheet"])
def test_modal_sheet_requires_unique_same_process_exact_rectangle(
    monkeypatch, mismatch
):
    import ctypes

    class Function:
        def __init__(self, call):
            self.call = call

        def __call__(self, *args):
            return self.call(*args)

    values = {
        1: b"AXMainWindow",
        2: b"AXChildren",
        3: b"AXRole",
        4: b"AXPosition",
        5: b"AXSize",
    }
    attrs = {
        b"AXMainWindow": 10,
        b"AXChildren": 11,
        b"AXRole": 12,
        b"AXPosition": 13,
        b"AXSize": 14,
    }

    def attribute(element, key, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = attrs[values[key]]
        return 0

    def string(value, buffer, size, encoding):
        buffer.value = b"AXButton" if mismatch == "no_sheet" else b"AXSheet"
        return True

    def coordinates(value, kind, output):
        pair = ctypes.cast(output, ctypes.POINTER(ctypes.c_double))
        pair[0], pair[1] = (150, 238) if kind == 1 else (880, 448)
        return True

    cf = SimpleNamespace(
        CFStringCreateWithCString=Function(
            lambda _, name, enc: next(k for k, v in values.items() if v == name)
        ),
        CFArrayGetCount=Function(lambda _: 1),
        CFArrayGetValueAtIndex=Function(lambda *_: 20),
        CFStringGetCString=Function(string),
        CFRelease=Function(lambda _: None),
    )
    ax = SimpleNamespace(
        AXUIElementCopyAttributeValue=Function(attribute),
        AXValueGetValue=Function(coordinates),
    )
    window = {
        "kCGWindowOwnerPID": 99 if mismatch == "pid" else 42,
        "kCGWindowLayer": 0,
        "kCGWindowName": "Choose MP3 audio",
        "kCGWindowBounds": {
            "X": 151 if mismatch == "bounds" else 150,
            "Y": 238,
            "Width": 880,
            "Height": 448,
        },
    }
    windows = [window, window] if mismatch == "duplicate" else [window]
    monkeypatch.setitem(
        sys.modules,
        "Quartz",
        SimpleNamespace(
            kCGWindowListOptionOnScreenOnly=1,
            CGWindowListCopyWindowInfo=lambda *_: windows,
        ),
    )
    assert native_input._modal_sheet_title(42, cf, ax, 1) == (
        "Choose MP3 audio" if mismatch is None else None
    )


def test_right_click_releases_matching_button_and_clears_modifiers(monkeypatch):
    monkeypatch.setattr(native_input.time, "sleep", lambda _: None)
    quartz = Quartz()
    quartz.kCGMouseButtonRight = 1
    quartz.kCGEventRightMouseDown = 4
    quartz.kCGEventRightMouseUp = 5
    native_input.post_click(quartz, (10, 10), lambda: None, right=True)
    assert [e["kind"] for e in quartz.events] == [1, 4, 5]
    assert all(e["flags"] == 0 for e in quartz.events)
