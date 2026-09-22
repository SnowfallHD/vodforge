"""AppKit controls above the live video view; no replacement playback session."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

from ...ui_theme import THEME

if sys.platform == "darwin":
    import objc  # type: ignore[import-untyped]
    import Quartz  # noqa: F401 - registers CGColorRef bridge before NSColor.CGColor
    from AppKit import (  # type: ignore[import-untyped]
        NSBezierPath,
        NSButton,
        NSColor,
        NSEvent,
        NSFont,
        NSGradient,
        NSImage,
        NSImageSymbolConfiguration,
        NSImageView,
        NSMenu,
        NSMenuItem,
        NSPopUpButton,
        NSSlider,
        NSSliderCell,
        NSTextField,
        NSView,
        NSWindowAbove,
    )
    from Foundation import NSData, NSObject  # type: ignore[import-untyped]

    def _role_color(role: str, alpha: float = 1.0) -> Any:
        value = THEME[role]
        rgb = tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))
        return NSColor.colorWithSRGBRed_green_blue_alpha_(*rgb, alpha)

    class VODForgePlayerOverlayView(NSView):
        owner: Any = None

        def drawRect_(self, _rect: Any) -> None:
            gradient = NSGradient.alloc().initWithStartingColor_endingColor_(
                NSColor.colorWithCalibratedWhite_alpha_(0, 0.88),
                NSColor.colorWithCalibratedWhite_alpha_(0, 0),
            )
            gradient.drawInRect_angle_(((0, 0), (self.bounds().size.width, 110)), 90)
            owner = self.owner
            if owner is not None:
                for _index, frame, state, focused in owner._control_highlights:
                    color = THEME[
                        "accent_surface" if state == "pressed" else "surface_2"
                    ]
                    rgb = tuple(
                        int(color[position : position + 2], 16) / 255
                        for position in (1, 3, 5)
                    )
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(
                        *rgb, 0.95
                    ).setFill()
                    shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                        frame, 7, 7
                    )
                    shape.fill()
                    if focused:
                        _role_color("focus").setStroke()
                        shape.setLineWidth_(1.5)
                        shape.stroke()

        def hitTest_(self, point: Any) -> Any:
            hit = objc.super(VODForgePlayerOverlayView, self).hitTest_(point)
            # Leave the video and its own events unobstructed outside controls.
            return None if hit is self else hit

    class VODForgePlayerVideoClickView(NSView):
        """Transparent input adapter; control descendants own their own clicks."""

        owner: Any = None
        pressed: Any = None

        def mouseDown_(self, event: Any) -> None:
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            self.pressed = (float(point.x), float(point.y))

        def mouseDragged_(self, event: Any) -> None:
            if self.pressed is None:
                return
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            if abs(point.x - self.pressed[0]) + abs(point.y - self.pressed[1]) > 6:
                self.pressed = None

        def mouseUp_(self, event: Any) -> None:
            pressed, self.pressed = self.pressed, None
            owner = self.owner
            if pressed is None or owner is None or owner._closed:
                return
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            bounds = self.bounds().size
            if (
                0 <= point.x <= bounds.width
                and 0 <= point.y <= bounds.height
                and abs(point.x - pressed[0]) + abs(point.y - pressed[1]) <= 6
            ):
                # This only queues Python data; Tk runs it in its own poll.
                owner.dispatch("toggle", None)

    class VODForgePlayerVolumeCell(NSSliderCell):
        def drawBarInside_flipped_(self, rect: Any, _flipped: bool) -> None:
            x, width = rect.origin.x + 5, max(1.0, rect.size.width - 10)
            y = rect.origin.y + rect.size.height / 2 - 1.5
            _role_color("border").setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((x, y), (width, 3)), 1.5, 1.5
            ).fill()
            fraction = (self.doubleValue() - self.minValue()) / max(
                1, self.maxValue() - self.minValue()
            )
            _role_color("progress").setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((x, y), (max(0.01, width * fraction), 3)), 1.5, 1.5
            ).fill()

        def drawKnob_(self, rect: Any) -> None:
            _role_color("text").setFill()
            NSBezierPath.bezierPathWithOvalInRect_(
                (
                    (
                        rect.origin.x + rect.size.width / 2 - 5,
                        rect.origin.y + rect.size.height / 2 - 5,
                    ),
                    (10, 10),
                )
            ).fill()

    class VODForgePlayerNotice(NSTextField):
        def drawRect_(self, rect: Any) -> None:
            NSColor.colorWithCalibratedWhite_alpha_(0.035, 0.92).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                self.bounds(), 7, 7
            ).fill()
            objc.super(VODForgePlayerNotice, self).drawRect_(rect)

    class VODForgePlayerTimeline(NSView):
        owner: Any = None

        def drawRect_(self, _rect: Any) -> None:
            owner = self.owner
            if owner is None:
                return
            width = max(1.0, self.bounds().size.width - 10)
            _role_color("border").setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((5, 9), (width, 3)), 1.5, 1.5
            ).fill()
            _role_color("progress").setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((5, 9), (max(0.01, width * owner.fraction), 3)), 1.5, 1.5
            ).fill()
            _role_color("text").setFill()
            NSBezierPath.bezierPathWithOvalInRect_(
                ((width * owner.fraction, 5.5), (10, 10))
            ).fill()

        def mouseDown_(self, event: Any) -> None:
            self.mouseDragged_(event)

        def mouseDragged_(self, event: Any) -> None:
            if self.owner is None:
                return
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            fraction = min(
                1.0, max(0.0, (point.x - 5) / max(1.0, self.bounds().size.width - 10))
            )
            self.owner.dispatch("seek_fraction", fraction)

    class VODForgePlayerOverlayActions(NSObject):
        owner: Any = None

        def pressed_(self, sender: Any) -> None:
            owner = self.owner
            if owner is not None:
                action = owner.button_actions[int(sender.tag())]
                if action == "floating" and owner.floating:
                    action = "return"
                owner.dispatch(action, None)

        def volume_(self, sender: Any) -> None:
            if self.owner is not None:
                self.owner.dispatch("volume", float(sender.doubleValue()))

        def menu_(self, sender: Any) -> None:
            owner = self.owner
            if owner is not None:
                owner.dispatch_menu(sender.representedObject())


class MacOSPlayerOverlay:
    """Own controls, targets and menus for exactly one native surface.

    Menus are owned and tracked by NSPopUpButton. Python never starts a modal
    AppKit menu loop from within a Tk callback.
    """

    def __init__(self, surface: Any, *, on_action: Callable[[str, Any], None]) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("AppKit player controls require macOS")
        self.surface = surface
        self._on_action = on_action
        self._closed = False
        self._last_interaction = time.monotonic()
        self._pointer_position: tuple[float, float] | None = None
        self._controls_visible = True
        self._visibility_events = 0
        self._hover_fraction: float | None = None
        self._control_highlights: tuple[Any, ...] = ()
        self._preview_has_image = False
        self.fraction = 0.0
        self.floating = False
        self.button_actions = (
            "toggle",
            "mute",
            "captions",
            "fullscreen",
            "options",
            "backward",
            "forward",
            "floating",
        )
        self._menu_generation = 0
        self._menu_signature: Any = None
        self._menus: list[Any] = []
        self.view = VODForgePlayerOverlayView.alloc().initWithFrame_(((0, 0), (1, 1)))
        self.view.owner = self
        self.video_click = VODForgePlayerVideoClickView.alloc().initWithFrame_(
            ((0, 0), (1, 1))
        )
        self.video_click.owner = self
        self.actions = VODForgePlayerOverlayActions.alloc().init()
        self.actions.owner = self
        self.timeline = VODForgePlayerTimeline.alloc().initWithFrame_(((0, 0), (1, 22)))
        self.timeline.owner = self
        self.timeline.setAccessibilityLabel_("Playback position")
        self.view.addSubview_(self.timeline)
        self.buttons = []
        for tag, symbol, label in (
            (0, "play.fill", "Play"),
            (1, "speaker.wave.2.fill", "Mute"),
            (2, "captions.bubble", "Captions"),
            (3, "arrow.up.left.and.arrow.down.right", "Full screen"),
            (4, "gearshape", "Playback options"),
            (5, "gobackward.10", "Jump back 10 seconds"),
            (6, "goforward.10", "Jump forward 10 seconds"),
            (7, "pip.enter", "Watch in floating window"),
        ):
            frame = ((0, 0), (36, 36))
            if tag in {2, 4}:
                button = NSPopUpButton.alloc().initWithFrame_pullsDown_(frame, True)
                button.setAutoenablesItems_(False)
                button.cell().setArrowPosition_(0)
            else:
                button = NSButton.alloc().initWithFrame_(frame)
                button.setTarget_(self.actions)
                button.setAction_("pressed:")
            button.setBordered_(False)
            button.setTitle_(label)
            button.setTag_(tag)
            button.setToolTip_(label)
            button.setAccessibilityLabel_(label)
            button.setContentTintColor_(_role_color("icon"))
            button.setImage_(self._symbol(symbol, label))
            button.setImagePosition_(1)
            self.view.addSubview_(button)
            self.buttons.append(button)
        self.time = NSTextField.labelWithString_("0:00 / 0:00")
        self.time.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(14, 0))
        self.time.setTextColor_(_role_color("text"))
        self.view.addSubview_(self.time)
        self.notice = VODForgePlayerNotice.labelWithString_("")
        self.notice.setFont_(NSFont.systemFontOfSize_(14))
        self.notice.setTextColor_(_role_color("text"))
        self.notice.setAlignment_(1)
        self.notice.setHidden_(True)
        self.view.addSubview_(self.notice)
        self.volume = NSSlider.alloc().initWithFrame_(((0, 0), (86, 24)))
        self.volume.setCell_(VODForgePlayerVolumeCell.alloc().init())
        self.volume.setMinValue_(0)
        self.volume.setMaxValue_(100)
        self.volume.setTarget_(self.actions)
        self.volume.setAction_("volume:")
        self.volume.setContinuous_(True)
        self.volume.setAccessibilityLabel_("Volume")
        self.view.addSubview_(self.volume)
        self.preview_box = NSView.alloc().initWithFrame_(((0, 0), (160, 24)))
        self.preview_box.setWantsLayer_(True)
        self.preview_box.layer().setCornerRadius_(6)
        self.preview_box.layer().setMasksToBounds_(True)
        self.preview_box.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.035, 0.96).CGColor()
        )
        self.preview_box.setHidden_(True)
        self.preview_image = NSImageView.alloc().initWithFrame_(((0, 24), (160, 90)))
        self.preview_image.setImageScaling_(0)
        self.preview_image.setHidden_(True)
        self.preview_box.addSubview_(self.preview_image)
        self.preview_time = NSTextField.labelWithString_("")
        self.preview_time.setFont_(
            NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0)
        )
        self.preview_time.setTextColor_(_role_color("text"))
        self.preview_time.setAlignment_(1)
        self.preview_time.setFrame_(((0, 2), (160, 20)))
        self.preview_box.addSubview_(self.preview_time)
        self.view.addSubview_(self.preview_box)
        self._palette: tuple[str, ...] | None = None
        self._refresh_palette()
        self.sync()

    def _refresh_palette(self) -> None:
        palette = tuple(
            THEME[key]
            for key in (
                "icon",
                "text",
                "progress",
                "border",
                "focus",
                "accent_surface",
                "surface_2",
            )
        )
        if palette == self._palette:
            return
        self._palette = palette
        for button in self.buttons:
            button.setContentTintColor_(_role_color("icon"))
        for label in (self.time, self.notice, self.preview_time):
            label.setTextColor_(_role_color("text"))
        for view in (self.view, self.timeline, self.volume):
            view.setNeedsDisplay_(True)

    @staticmethod
    def _symbol(symbol: str, label: str) -> Any:
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            symbol, label
        )
        if image is not None:
            image = image.imageWithSymbolConfiguration_(
                NSImageSymbolConfiguration.configurationWithPointSize_weight_(20, 0)
            )
        return image

    def dispatch(self, action: str, value: Any) -> None:
        if not self._closed:
            self._last_interaction = time.monotonic()
            self._on_action(action, value)

    def dispatch_menu(self, token: Any) -> None:
        if self._closed or not isinstance(token, str):
            return
        generation, separator, action = token.partition("|")
        if separator and generation == str(self._menu_generation) and action:
            self.dispatch(action, None)

    def sync(self) -> None:
        if self._closed:
            return
        native = self.surface.macos_view
        if native is None:
            return
        frame = native.frame()
        native.superview().addSubview_positioned_relativeTo_(
            self.video_click, NSWindowAbove, native
        )
        self.video_click.setFrame_(frame)
        native.superview().addSubview_positioned_relativeTo_(
            self.view, NSWindowAbove, self.video_click
        )
        self.view.setFrame_(frame)
        width = float(frame.size.width)
        self.timeline.setFrame_(((18, 57), (max(1, width - 36), 22)))
        for index, x in ((0, 18), (5, 62), (6, 106), (1, 150)):
            self.buttons[index].setFrame_(((x, 15), (36, 36)))
        expanded = width >= 680
        self.volume.setHidden_(not expanded)
        self.volume.setFrame_(((196, 21), (86, 24)))
        time_x = 294 if expanded else 196
        # The leftmost right-hand control is captions. Keep an eight-pixel gap;
        # compact windows show elapsed time and expose the complete time in AX/tooltip.
        self._time_width = min(160.0, max(1.0, width - 182 - time_x - 8))
        self.time.setFrame_(((time_x, 23), (self._time_width, 20)))
        for offset, index in enumerate((3, 7, 4, 2)):
            self.buttons[index].setFrame_(((width - 50 - offset * 44, 15), (36, 36)))
        self._notice_max_width = max(1, width - 40)
        self._notice_center = width / 2
        self.view.setNeedsDisplay_(True)

    def present(
        self,
        snapshot: Any,
        *,
        time_text: str,
        fullscreen: bool,
        floating: bool,
        notice: str,
    ) -> None:
        if self._closed:
            return
        self.floating = floating
        self._refresh_palette()
        radius = 0 if fullscreen else 11
        if radius != self.__dict__.get("_video_corner_radius"):
            native = self.surface.macos_view
            if native is not None:
                for clipped in (native, self.view):
                    clipped.setWantsLayer_(True)
                    clipped.layer().setCornerRadius_(radius)
                    clipped.layer().setMasksToBounds_(True)
                self._video_corner_radius = radius
        self.fraction = (
            min(1.0, max(0.0, snapshot.position / snapshot.duration))
            if snapshot.duration > 0
            else 0.0
        )
        playing = snapshot.status in {"Playing", "Starting"}
        for index, symbol, label in (
            (
                0,
                "pause.fill" if playing else "play.fill",
                "Pause" if playing else "Play",
            ),
            (
                1,
                "speaker.slash.fill" if snapshot.volume == 0 else "speaker.wave.2.fill",
                "Unmute" if snapshot.volume == 0 else "Mute",
            ),
            (
                3,
                "arrow.down.right.and.arrow.up.left"
                if fullscreen
                else "arrow.up.left.and.arrow.down.right",
                "Exit full screen" if fullscreen else "Full screen",
            ),
            (
                7,
                "pip.exit" if floating else "pip.enter",
                "Return to main window" if floating else "Watch in floating window",
            ),
        ):
            button = self.buttons[index]
            button.setImage_(self._symbol(symbol, label))
            button.setToolTip_(label)
            button.setAccessibilityLabel_(label)
        self.time.setStringValue_(time_text)
        if self.time.intrinsicContentSize().width > self._time_width:
            self.time.setStringValue_(time_text.split(" / ", 1)[0])
        self.time.setToolTip_(time_text)
        self.time.setAccessibilityLabel_(f"Playback time: {time_text}")
        self.notice.setStringValue_(notice)
        notice_width = min(
            self._notice_max_width, self.notice.intrinsicContentSize().width + 24
        )
        self.notice.setFrame_(
            ((self._notice_center - notice_width / 2, 87), (max(1, notice_width), 24))
        )
        self.notice.setToolTip_(notice)
        self.notice.setHidden_(not bool(notice))
        self.volume.setDoubleValue_(snapshot.volume)
        self.timeline.setNeedsDisplay_(True)
        self._present_visibility(playing=playing, notice=notice)
        self._paint_control_states()
        self._track_hover(enabled=snapshot.duration > 0 and not notice)

    def _paint_control_states(self) -> None:
        """One palette/state adapter for every native transport button and slider."""
        window = self.view.window()
        if window is None:
            return
        point = self.view.convertPoint_fromView_(
            window.mouseLocationOutsideOfEventStream(), None
        )
        focus = window.firstResponder()
        pressed = bool(NSEvent.pressedMouseButtons() & 1)
        highlights = []
        for index, control in enumerate((*self.buttons, self.volume)):
            enabled = bool(control.isEnabled())
            opacity = 1.0 if enabled else 0.38
            if control.alphaValue() != opacity:
                control.setAlphaValue_(opacity)
            if not enabled or control.isHidden() or self.view.isHidden():
                continue
            frame = control.frame()
            x, y = float(frame.origin.x), float(frame.origin.y)
            width, height = float(frame.size.width), float(frame.size.height)
            hovered = x <= point.x <= x + width and y <= point.y <= y + height
            focused = focus is control or (
                focus is not None
                and hasattr(focus, "isDescendantOf_")
                and focus.isDescendantOf_(control)
            )
            if hovered or focused:
                highlights.append(
                    (
                        index,
                        ((x, y), (width, height)),
                        "pressed" if hovered and pressed else "hover",
                        bool(focused),
                    )
                )
        signature = tuple(highlights)
        if signature != self._control_highlights:
            self._control_highlights = signature
            self.view.setNeedsDisplay_(True)

    def _track_hover(self, *, enabled: bool) -> None:
        window = self.view.window()
        if window is None:
            return
        point = self.view.convertPoint_fromView_(
            window.mouseLocationOutsideOfEventStream(), None
        )
        width = float(self.view.bounds().size.width)
        over_timeline = enabled and 18 <= point.x <= width - 18 and 54 <= point.y <= 82
        if over_timeline:
            fraction = min(1.0, max(0.0, (point.x - 23) / max(1.0, width - 46)))
            if (
                self._hover_fraction is None
                or abs(fraction - self._hover_fraction) > 0.0001
            ):
                self._hover_fraction = fraction
                self.dispatch("hover_fraction", fraction)
            self._place_hover()
        elif self._hover_fraction is not None:
            self._hover_fraction = None
            self.preview_box.setHidden_(True)
            self.dispatch("hover_end", None)

    def _place_hover(self) -> None:
        if self._hover_fraction is None:
            return
        width = float(self.view.bounds().size.width)
        x = min(max(12.0, (width - 46) * self._hover_fraction + 23 - 80), width - 172)
        self.preview_box.setFrame_(
            ((x, 86), (160, 114 if self._preview_has_image else 24))
        )

    def show_hover(self, time_text: str, data: bytes | None = None) -> bool:
        if self._closed or self._hover_fraction is None:
            return False
        self.preview_time.setStringValue_(time_text)
        picture = None
        if data is not None:
            picture = NSImage.alloc().initWithData_(
                NSData.dataWithBytes_length_(data, len(data))
            )
        self._preview_has_image = picture is not None
        self.preview_image.setImage_(picture)
        self.preview_image.setHidden_(picture is None)
        self.preview_box.setHidden_(False)
        self._place_hover()
        return picture is not None

    def _update_visibility(
        self,
        *,
        playing: bool,
        notice: str,
        pointer: tuple[float, float],
        inside: bool,
        over_controls: bool,
        interacting: bool,
        now: float,
    ) -> bool:
        # Called by the existing player poll. No additional timer, native
        # event loop, playback mutation or per-motion telemetry.
        if self._closed:
            return False
        if inside and pointer != self._pointer_position:
            self._last_interaction = now
        self._pointer_position = pointer
        if not playing or notice or over_controls or interacting:
            self._last_interaction = now
        visible = bool(
            not playing
            or notice
            or over_controls
            or interacting
            or now - self._last_interaction < 3.0
        )
        if visible != self._controls_visible:
            self._controls_visible = visible
            if self._visibility_events < 8:
                self._visibility_events += 1
                # Queue directly: visibility observations are not user activity.
                self._on_action(
                    "controls_shown" if visible else "controls_hidden", None
                )
        return visible

    def _present_visibility(self, *, playing: bool, notice: str) -> None:
        window = self.view.window()
        if window is None:
            return
        point = self.view.convertPoint_fromView_(
            window.mouseLocationOutsideOfEventStream(), None
        )
        bounds = self.view.bounds().size
        inside = 0 <= point.x <= bounds.width and 0 <= point.y <= bounds.height
        responder = window.firstResponder()
        focused = bool(
            responder is not None
            and hasattr(responder, "isDescendantOf_")
            and responder.isDescendantOf_(self.view)
        )
        visible = self._update_visibility(
            playing=playing,
            notice=notice,
            pointer=(point.x, point.y),
            inside=inside,
            over_controls=inside and point.y <= 80,
            interacting=focused or (inside and NSEvent.pressedMouseButtons() != 0),
            now=time.monotonic(),
        )
        # Keep the native hit targets active during the short fade; retire them
        # completely when hidden. A subsequent pointer movement wakes the view.
        alpha = float(self.view.alphaValue())
        alpha = min(1.0, alpha + 0.5) if visible else max(0.0, alpha - 0.5)
        if visible:
            self.view.setHidden_(False)
        self.view.setAlphaValue_(alpha)
        if alpha == 0:
            self.view.setHidden_(True)

    def set_menus(
        self,
        options: Sequence[tuple[str, str, bool, bool]],
        captions: Sequence[tuple[str, str, bool, bool]],
    ) -> None:
        signature = (tuple(options), tuple(captions))
        if self._closed or signature == self._menu_signature:
            return
        self._menu_signature = signature
        self._menu_generation += 1
        self._menus = []
        for index, entries, symbol, label in (
            (4, options, "gearshape", "Playback options"),
            (2, captions, "captions.bubble", "Captions"),
        ):
            menu = NSMenu.alloc().initWithTitle_(label)
            menu.setAutoenablesItems_(False)
            title = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
            title.setImage_(self._symbol(symbol, label))
            menu.addItem_(title)
            for offset, (text, action, selected, enabled) in enumerate(entries):
                tag = index * 100 + offset
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    text, "menu:", ""
                )
                item.setTarget_(self.actions)
                item.setTag_(tag)
                item.setRepresentedObject_(f"{self._menu_generation}|{action}")
                item.setEnabled_(enabled)
                item.setState_(1 if selected else 0)
                menu.addItem_(item)
            self.buttons[index].setMenu_(menu)
            self._menus.append(menu)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for menu in self._menus:
            menu.cancelTracking()
        self.actions.owner = None
        self.timeline.owner = None
        self.view.owner = None
        self.video_click.owner = None
        self.video_click.pressed = None
        for button in self.buttons:
            button.setTarget_(None)
        self.volume.setTarget_(None)
        self.view.removeFromSuperview()
        self.video_click.removeFromSuperview()
        self._on_action = lambda _action, _value: None
