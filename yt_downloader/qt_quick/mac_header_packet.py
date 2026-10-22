"""One native-row transaction. No GUI, timing, previous allocation or fallback."""

from __future__ import annotations

import math


class NativeRowRefused(ValueError):
    pass


def rect(value):
    if (
        len(value) != 4
        or any(type(v) not in (float, int) or not math.isfinite(v) for v in value)
        or min(value[2:]) <= 0
    ):
        raise NativeRowRefused("missing current positive rectangle")
    return tuple(float(v) for v in value)


def packet(sample, body_slot, sequence, control_gap=0):
    """The native row owns control lane + custom-item lane; Qt owns only its lane.

    A control outside the accessory is valid. A control outside the shared
    vertical band/content width is not. No full-row drawing ownership is inferred
    from these measurements: actual native pixels remain a separate gate.
    """
    if (
        type(control_gap) not in (int, float)
        or not math.isfinite(control_gap)
        or not 0 <= control_gap <= 256
    ):
        raise NativeRowRefused("invalid independent control gap policy")
    if (
        type(sequence) is not int
        or sequence < 1
        or type(body_slot) not in (int, float)
        or not math.isfinite(body_slot)
        or not 0 < body_slot <= 256
    ):
        raise NativeRowRefused("invalid generation/body reservation")
    if sample.get("owner") != "unified-toolbar" or not all(
        sample.get(k) is True
        for k in (
            "current",
            "toolbar_owned",
            "delegate_unchanged",
            "full_size",
            "transparent",
            "title_hidden",
        )
    ):
        raise NativeRowRefused("native owner is not current and visible")
    if type(sample.get("transition")) is not int or sample["transition"] not in (
        0,
        1,
        2,
    ):
        raise NativeRowRefused("unknown native transition")
    # AppKit may temporarily hide its real overlay during fullscreen reparenting.
    # Its current allocation is still authoritative; do not freeze the old size,
    # nor report that the hidden native window is visible.
    if type(sample.get("host_visible")) is not bool or (
        not sample["host_visible"] and sample["transition"] == 0
    ):
        raise NativeRowRefused("native host visibility is not current")
    host = rect(sample["host"])
    content = rect(sample["content"])
    hx, hy, hw, hh = host
    cx, cy, cw, ch = content
    if hh < body_slot:
        raise NativeRowRefused(
            "native row is too short for the independent header policy"
        )
    if hx < cx or hx + hw > cx + cw:
        raise NativeRowRefused("custom item outside viewport width")
    buttons = sample.get("buttons", [])
    if (
        len(buttons) != 3
        or len({b.get("identity") for b in buttons}) != 3
        or any(
            type(b.get("identity")) is not int or b["identity"] <= 0 for b in buttons
        )
    ):
        raise NativeRowRefused("three current control identities required")
    states = [b.get("visibility") for b in buttons]
    if states == ["visible"] * 3:
        bounds = [rect(b["visible_screen"]) for b in buttons]
        for x, y, w, h in bounds:
            if x < cx or x + w > cx + cw or y < hy or y + h > hy + hh:
                raise NativeRowRefused(
                    "controls are not in the current shared native row band"
                )
        lanes = [rect(b.get("screen_bounds", b["visible_screen"])) for b in buttons]
        for full, visible_bounds in zip(lanes, bounds):
            x, y, w, h = full
            vx, vy, vw, vh = visible_bounds
            if vx < x or vy < y or vx + vw > x + w or vy + vh > y + h:
                raise NativeRowRefused(
                    "visible controls disagree with current full bounds"
                )
        if any(a[0] + a[2] > b[0] for a, b in zip(lanes, lanes[1:])):  # noqa: RUF007 - preserve accepted pure transaction
            raise NativeRowRefused("control lanes overlap or reorder")
        # Windowed AppKit may allocate an adjacent item; fullscreen AppKit
        # may allocate an item spanning the genuine native controls. Both are
        # current same-row ownership, not a stale windowed offset. Only content
        # clearance changes, from current visible intersections + design gap.
        overlaps = [r for r in lanes if r[0] + r[2] > hx and r[0] < hx + hw]
        # While fullscreen's native item slides, retain the same declared
        # control-to-content gap even just after its left edge clears the last
        # button. Dropping that gap at the intersection boundary creates a
        # backward target step (real native replay: 99 -> 92 -> 96). This uses
        # only current controls/item/fullscreen state; no cached origin or new
        # offset/animation. Windowed adjacent allocation remains unchanged.
        if sample["fullscreen"]:
            leading = max(0.0, max(r[0] + r[2] for r in lanes) + control_gap - hx)
        else:
            leading = (
                max(r[0] + r[2] for r in overlaps) - hx + control_gap
                if overlaps
                else 0.0
            )
        if leading < 0 or leading >= hw:
            raise NativeRowRefused("native controls leave no item content lane")
        start = min(hx, min(r[0] for r in bounds))
        row = (start, hy, max(hx + hw, max(r[0] + r[2] for r in bounds)) - start, hh)
        content_target = (
            max(r[0] + r[2] for r in lanes) + control_gap
            if sample["fullscreen"]
            else hx + leading
        )
        visible = True
    elif states == ["hidden"] * 3:
        row = host
        content_target = cx
        visible = False
        leading = 0.0
    else:
        raise NativeRowRefused("mixed/unknown control visibility")
    # Both states use current native allocation. Current native geometry owns horizontal
    # clearance. One packet only; no second animation or retained windowed width.
    return {
        "schema_version": 1,
        "sequence": sequence,
        "owner": "unified-toolbar",
        "host_visible": sample["host_visible"],
        "state": "controls-visible" if visible else "controls-hidden",
        "host_screen": list(host),
        "content_screen": list(content),
        "content_target_screen_x": float(content_target),
        "native_row_screen": list(row),
        "width": hw,
        "height": hh,
        "leading": float(leading),
        "reserve": float(leading),
        "relative_x": hx - cx,
        "relative_y": cy + ch - hy - hh,
        "fullscreen": sample["fullscreen"],
        "transition": sample["transition"],
        "body_slot_height": float(body_slot),
        "pixel_acceptance": False,
    }
