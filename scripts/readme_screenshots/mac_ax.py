"""Drive the running Mac app through Accessibility for the README screenshots.

    mac_ax.py PID trusted | list [ROLE] | press ROLE NAME [INDEX]
             | size W H [X Y] | shot OUT.png [shadow]

`shot ... shadow` captures the window with macOS's own shadow (transparent
background), ready for frame.py. The terminal needs Accessibility permission.
"""

import subprocess
import sys

import ApplicationServices as ax
import Quartz

PID = int(sys.argv[1])
cmd = sys.argv[2]
args = sys.argv[3:]
app = ax.AXUIElementCreateApplication(PID)


def attr(e, n):
    err, v = ax.AXUIElementCopyAttributeValue(e, n, None)
    return v if err == 0 else None


def label(e):
    for n in ("AXTitle", "AXDescription", "AXValue"):
        v = attr(e, n)
        if isinstance(v, str) and v:
            return v
    return ""


def walk(e, d=0):
    yield e
    if d < 45:
        for c in attr(e, "AXChildren") or []:
            yield from walk(c, d + 1)


def windows():
    ws = list(attr(app, "AXWindows") or [])
    m = attr(app, "AXMainWindow")
    if m is not None and m in ws:
        ws.remove(m)
        ws.insert(0, m)
    return ws


def pos(e):
    p = attr(e, "AXPosition")
    s = attr(e, "AXSize")
    if p is None or s is None:
        return None
    _, pt = ax.AXValueGetValue(p, ax.kAXValueCGPointType, None)
    _, sz = ax.AXValueGetValue(s, ax.kAXValueCGSizeType, None)
    return (round(pt.x), round(pt.y), round(sz.width), round(sz.height))


if cmd == "trusted":
    print(ax.AXIsProcessTrusted())
elif cmd == "list":
    role = args[0] if args else None
    for w in windows():
        for e in walk(w):
            r = attr(e, "AXRole")
            if role and r != role:
                continue
            l = label(e)
            if l:
                print(r, repr(l[:70]), pos(e))
elif cmd == "press":
    role, name = args[0], args[1]
    idx = int(args[2]) if len(args) > 2 else 0
    hits = [
        e
        for w in windows()
        for e in walk(w)
        if attr(e, "AXRole") == role and label(e) == name
    ]
    if len(hits) <= idx:
        sys.exit(f"not found: {role} {name!r} ({len(hits)})")
    print(ax.AXUIElementPerformAction(hits[idx], "AXPress"))
elif cmd == "size":
    w = windows()[0]
    import Foundation

    sz = ax.AXValueCreate(
        ax.kAXValueCGSizeType, Foundation.NSMakeSize(float(args[0]), float(args[1]))
    )
    print(ax.AXUIElementSetAttributeValue(w, "AXSize", sz))
    if len(args) > 3:
        pt = ax.AXValueCreate(
            ax.kAXValueCGPointType,
            Foundation.NSMakePoint(float(args[2]), float(args[3])),
        )
        print(ax.AXUIElementSetAttributeValue(w, "AXPosition", pt))
elif cmd == "shot":
    out = args[0]
    shadow = len(args) > 1 and args[1] == "shadow"
    for info in (
        Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
        )
        or []
    ):
        if (
            info.get("kCGWindowOwnerPID") == PID
            and info.get("kCGWindowLayer") == 0
            and info.get("kCGWindowName") == "VODForge"
        ):
            a = (
                ["/usr/sbin/screencapture", "-x"]
                + ([] if shadow else ["-o"])
                + [f"-l{info['kCGWindowNumber']}", out]
            )
            subprocess.run(a, check=True)
            print(out, dict(info["kCGWindowBounds"]))
            break
