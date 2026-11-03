# The macOS header and menu bar (Sept 23 – Oct 30, 2026)

## Summary

VODForge's macOS header (logo, Forge/Library/Watch/Activity navigation, search, X and
Settings) should sit in the window's title bar and behave like Safari's toolbar:
correct size the moment the window enters full screen, and slide smoothly with the
menu bar when the pointer reveals it at the top of the screen.

For five weeks it didn't. On entering full screen the header was drawn about 35%
too large for roughly half a second and then snapped to size. When the menu bar
slid down, the header lagged behind it, the logo ran under the window buttons, and
the row finished with a visible ~31 pt catch-up jump. It sometimes disappeared
after resizing or after full-screen reveal and focus changes. About 50 commits and
many diagnostic builds went into it.

The fix was to stop drawing the header with Qt. Since October 30 the header is a set
of native AppKit toolbar items (`yt_downloader/platforms/macos/header_items.m`,
bridged by `yt_downloader/qt_quick/mac_toolbar_header.py`). macOS draws and moves
them itself, the same way it handles Safari's toolbar. Recordings confirmed the
size snap and the reveal lag were gone, and the old Qt-drawn header (about 7,100
lines including its tests and diagnostics) was removed.

## What we tried, and why each attempt failed

### 1. Qt header blended into the title bar (Sept 23 – Sept 30)

`6e4b5ac` made the window's content extend under a transparent title bar and drew
the header in QML at the top. That looked right while the window stayed still, but
dragging the window by the header needed hand-offs between Qt and the native title
bar (`c98d849`, `c1115a4`), and in full screen the macOS menu bar slid over the top
of the content instead of pushing the header down.

**Why it fell short:** macOS only moves things that it owns along with the menu
bar. A header painted inside the content area isn't one of them.

### 2. Qt-drawn header placed inside a native toolbar (Oct 18 – Oct 23)

`6e041e4` and `8b7a5f0` created a real `NSToolbar` and placed a Qt-rendered child
surface in it (`header_toolbar.m` + `mac_header.py`). The toolbar now moved with
the menu bar, but the Qt surface inside it had to be re-sized and re-positioned to
follow, using geometry "packets" sent from the native side to QML.

Each new symptom got a targeted fix:

- The header disappeared after full-screen reveal and composer focus. We added
  pending-alignment guards that wait for a matching geometry event.
- The motion looked rough. We added animated hand-offs (70/220 ms smoothed
  animations), and readiness was separated from presentation.
- The logo overlapped the window buttons. We added full button-bounds reads and
  clamped layout.
- Tooltip and popup ownership broke the header after full-screen exit. We repaired
  popup wrapper ownership (`item.window()` changed ownership as a side effect).
- Hidden-host transitions refused valid geometry. We allowed authoritative
  transition geometry.
- On two displays, the visibility reader returned "unknown" and blocked input.
  We changed it to use the envelope of all screen intersections.

Each fix passed its tests, and several fixed real bugs. But the user's next review
kept finding the same visible problems: the snap on entry, the lag and jump on
reveal, and the header vanishing on resize.

**Why it kept failing:** two rendering systems shared one piece of chrome. AppKit
decided when and where the toolbar moved, and Qt drew the pixels afterwards, a
frame or more late. Every guard and animation tried to make Qt keep up with motion
it didn't control. Tests ran offscreen or with synthetic geometry packets, so they
could pass while the real app on screen still looked wrong. Two "endpoint" tests
even encoded settled positions that no native producer ever delivered.

### 3. Measuring instead of patching (Oct 25)

We recorded full-screen cycles on the MacBook Air and tested one hypothesis per
run, each against a baseline recording:

| Hypothesis | Result |
| --- | --- |
| Qt and the native view disagree on size or backing scale | No: 9,340 samples, zero mismatches |
| Resizing too early causes the stretch | Holding the size changed timing, not the stretch. Rejected |
| Publishing geometry before the native resize | All three sizes matched, but the stretch remained. Rejected |
| Forcing a redraw of the content layer | Ran in 0.25 ms, but the stretch remained. Rejected |
| Qt's container layer (`QT_MAC_NO_CONTAINER_LAYER`) | Layer removed, but the stretch remained. Rejected |
| Metal transactions (`QT_MTL_NO_TRANSACTION`) | Changed layer type, but the stretch remained. Rejected |
| Window "expanded content" flag | Flag removed, but the stretch remained. Rejected |

The decisive experiments:

- **Layer probe:** for about 0.65 s after each full-screen entry, the header's
  Metal surface was the new size while its drawable still held the old,
  smaller-scale image, stretched by the layer's resize gravity. That is the
  "enlarged then snaps" frame.
- **Static grid:** with all header content replaced by a fixed grid (no
  animation, no layout), the grid still stretched when Qt drew it. When AppKit
  drew the same grid in the same toolbar, it didn't. The problem was Qt's rendering
  path for an embedded surface, not our layout, animation or timing code.
- **Plain controls:** a stock Qt window and a plain AppKit window both showed the
  doubled image on full-screen exit. That is macOS's own crossfade, and Safari
  shows it too. It isn't a bug.

### 4. Copying what Safari does (Oct 30)

We recorded Safari, the current VODForge and a small standalone AppKit test app
side by side (`a991366`). Safari's toolbar never resizes on full-screen entry and
moves in one smooth slide with the menu bar. The test app, with VODForge-styled
separate toolbar items drawn by AppKit, behaved exactly like Safari.

So the header became native toolbar items: brand, four navigation buttons, search
field, X and Settings. They reuse the existing stone-material images, drawn
nine-part at 2x, and the icons are ports of the QML scene icons. QML hides its own
header on macOS and offsets the body by the toolbar's height. Clicks and search
text travel to Python through a pipe, not native callbacks. The user reviewed a
recording and confirmed the motion: no size snap on entry, and reveal and hide
move as one.

Follow-ups found during that review:

- **Upside-down button materials.** NSImage nine-part drawing ignores
  `respectFlipped`, so the drawing context is unflipped locally. A native pixel
  test now checks drawn materials (`tests/test_macos_header_items_native.py`).
  The earlier tests missed this because they used a stand-in toolbar that never
  drew anything.
- **Folder picker opened mid-reveal and stalled the menu bar.** The deferral
  logic read geometry packets that only the old header produced.
  `vf_toolbar_chrome` now reports full-screen transition and menu-bar reveal, and
  the picker waits until the menu bar is still.
- **Modals didn't dim or block the native header.** The header now mirrors the
  dimming Qt actually shows, ignores hover and keyboard input while dimmed, and
  turns a header click into an "outside press" so popups close the same way as
  for any other background click.

The Qt-drawn header was then deleted (`19c9d54`). If the native toolbar fails to
load, the window falls back to a standard title bar with the in-window Qt header,
the same layout Windows and Linux use.

## Lessons to carry forward

1. **Let the platform draw platform chrome.** Anything that moves with OS-driven
   animation (menu bar, toolbar, full-screen transitions, window controls) should
   be drawn by the OS toolkit. A cross-toolkit surface embedded in native chrome
   will always be at least a frame behind the motion.
2. **Record a reference app and the real app first.** One side-by-side recording
   of Safari would have shown, on day one, what correct looks like and that the
   exit doubling is normal. Reason from frames, not from logs or settled
   screenshots.
3. **Separate "our code" from "the toolkit" with the smallest reproduction.**
   A static grid and a ten-line AppKit app answered in one afternoon what weeks of
   targeted fixes couldn't.
4. **When several reasonable fixes don't change the symptom, question the
   design.** Each guard in phase 2 fixed something real, but none touched the
   cause. Repeated near-misses are a signal to stop patching.
5. **Visual motion needs real-pixel evidence.** Offscreen QML, synthetic geometry
   packets and stand-in views can't certify what users see. Native tests must
   draw real pixels (as the material test now does), and motion needs a
   recording.
6. **One owner per surface, and remove the old path when it's replaced.** The
   environment-variable fallback to the old header kept 7,100 lines and their
   tests alive for no user benefit.
7. **Diagnostics are a means, not a deliverable.** The probes and trace options
   grew larger than the feature. Build the smallest instrument that answers the
   current question, then remove it.

## Still open

- Two acceptance items in `engineering-quality/acceptance/user-reported-defects.json`
  (`mac-header-disappears-on-resize`, `mac-header-motion-regression`) stay open
  until a packaged build is checked. The fix was confirmed in a source run, not
  yet in a signed package.
- Intel Macs, two physical displays, and full keyboard and VoiceOver use of the
  native header haven't been tested.
- Menu-bar-revealed folder-picker timing hasn't been re-recorded since the
  deferral fix.
