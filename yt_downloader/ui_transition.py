"""Brief top-level view reveal, scoped to the current navigation generation."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Any

from .platform_services import (
    capture_own_widget,
    present_pending_drawing,
    supports_tk_event,
)


class ViewTransition:
    def __init__(
        self, root: Any, *, observed: Any = None, diagnostic: Any = None
    ) -> None:
        self.root = root
        self._observed = observed
        self._diagnostic = diagnostic
        self._observed_actions: set[str] = set()
        self._generation = 0
        self._timer: Any = None
        self._overlay: Any = None
        self._image: Any = None
        self._frame: Any = None
        self._size = (0, 0)
        self._started = 0.0
        self._target: Any = None
        self._prepared = False
        self._drawing_attempts = 0
        root.bind("<Destroy>", self._destroyed, add="+")
        root.bind("<Configure>", self._configured, add="+")

    def cancel(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None
        self._image = self._frame = self._target = None
        self._prepared = False
        self._drawing_attempts = 0

    def prepare(self, frame: Any) -> None:
        """Cover the outgoing view before navigation exposes the destination."""
        self.cancel()
        if frame is None or not frame.winfo_exists() or not frame.winfo_ismapped():
            return
        from PIL import ImageFilter, ImageTk

        started = time.monotonic()
        bitmap = capture_own_widget(frame)
        if bitmap is None or time.monotonic() - started > 0.12:
            self._observe("transition_skipped")
            return
        self._target = frame
        self._prepared = True
        self._size = (frame.winfo_width(), frame.winfo_height())
        self._root_size = (self.root.winfo_width(), self.root.winfo_height())
        self._frame = bitmap.filter(ImageFilter.GaussianBlur(1.4))
        self._image = ImageTk.PhotoImage(self._frame, master=self.root)
        # Sibling ownership keeps the cover mapped when the old view unmaps.
        # Install pixels before mapping, so no empty Label frame can be exposed.
        self._overlay = tk.Label(
            frame.master, image=self._image, bd=0, highlightthickness=0, takefocus=False
        )
        self._overlay.place(
            x=frame.winfo_x(),
            y=frame.winfo_y(),
            width=self._size[0],
            height=self._size[1],
        )
        self._overlay.lift()
        self._overlay.bind("<ButtonPress-1>", self._pointer)
        self._overlay.bind("<MouseWheel>", self._wheel)
        if supports_tk_event(self._overlay, "<TouchpadScroll>"):
            self._overlay.bind(
                "<TouchpadScroll>", lambda event: self._wheel(event, precise=True)
            )

    def reveal(self, frame: Any) -> None:
        # Unprepared callers navigate immediately. Never blur a destination that
        # has already become visible, or take another snapshot through the cover.
        if self._overlay is None or not self._prepared:
            self.cancel()
            return
        self._prepared = False
        self._drawing_attempts = 0
        self._target = frame
        self._overlay.lift()
        generation = self._generation
        self._started = time.monotonic()
        self._observe("transition_shown")
        self._timer = self.root.after(72, lambda: self._finish(generation))

    def _finish(self, generation: int) -> None:
        if generation != self._generation:
            return
        # Complete pending destination drawing while the outgoing cover remains.
        # Leaf widgets such as Activity's text area need the same ordering as
        # Watch's child canvases. Service the shared interpreter only once.
        complete = (
            present_pending_drawing(self._target) if self._target is not None else True
        )
        # Idle work may navigate or destroy the owner. That newer intent wins.
        if generation != self._generation:
            return
        self._drawing_attempts += 1
        if complete is False and self._drawing_attempts < 3:
            # Yield to ordinary event processing between bounded drawing passes.
            # User input or newer navigation can still cancel the cover.
            self._timer = self.root.after(8, lambda: self._finish(generation))
            return
        self._timer = None
        self.cancel()

    def _pointer(self, _event: Any) -> str:
        # The visible pixels still belong to the outgoing page. Reveal the new
        # page without transferring that press to an unseen, unrelated action.
        self.cancel()
        return "break"

    def _wheel(self, event: Any, *, precise: bool = False) -> str:
        x, y, delta, state = event.x_root, event.y_root, event.delta, event.state
        self.cancel()
        target = self.root.winfo_containing(x, y)
        if target is not None:
            from .ui_scrolling import (
                event_scroll_binding,
                touchpad_scroll_deltas,
                wheel_motion,
            )

            binding = event_scroll_binding(target)
            if binding:
                if precise:
                    dx, dy = touchpad_scroll_deltas(target, delta)
                    binding.scroll(
                        wheel_motion(dx, precise=True), wheel_motion(dy, precise=True)
                    )
                else:
                    motion = wheel_motion(delta)
                    binding.scroll(
                        motion if state & 1 else 0, 0 if state & 1 else motion
                    )
        return "break"

    def _observe(self, action: str) -> None:
        if self._observed is None or action in self._observed_actions:
            return
        self._observed_actions.add(action)
        try:
            self._observed("appearance", action)
        except Exception:  # noqa: BLE001, S110  # nosec B110 - optional observation cannot interrupt navigation
            pass

    def _diagnose(self, message: str) -> None:
        if self._diagnostic is None:
            return
        try:
            self._diagnostic(message)
        except Exception:  # noqa: BLE001, S110  # nosec B110 - diagnostics cannot block navigation
            pass

    def _configured(self, event: Any) -> None:
        if (
            self._overlay is not None
            and event.widget is self.root
            and (event.width, event.height) != self._root_size
        ):
            self.cancel()

    def _destroyed(self, event: Any) -> None:
        if event.widget is self.root or event.widget is self._target:
            self.cancel()


def cancel_view_transition(widget: Any) -> None:
    root = getattr(widget, "winfo_toplevel", lambda: None)()
    transition = getattr(root, "_view_transition", None)
    if transition is not None:
        transition.cancel()


class WidgetReveal:
    """Prepare a sibling view behind its predecessor, without animation or pumping.

    The view owner supplies its final-layout predicate. This instance owns only
    its timer and temporary input tags. The optional finished callback lets the
    view owner retire an outgoing view after either completion or cancellation.
    """

    _events = (
        "<ButtonPress>",
        "<ButtonRelease>",
        "<KeyPress>",
        "<KeyRelease>",
        "<Motion>",
        "<MouseWheel>",
        "<TouchpadScroll>",
    )

    def __init__(
        self,
        frame: Any,
        outgoing: Any,
        *,
        current: Any,
        escape: Any,
        incoming: Any = None,
        finished: Any = None,
    ) -> None:
        self.frame = frame
        self.outgoing = tuple(outgoing)
        self.incoming = tuple(incoming) if incoming is not None else (frame,)
        self.finished = finished
        self.current = current
        self.escape = escape
        self.ready: Any = None
        self.timer: Any = None
        self.active = True
        self._tag = f"view-reveal-{id(self)}"
        self._guarded: list[Any] = []
        self._commands: list[str] = []
        self._destroy_binding = frame.bind("<Destroy>", self._destroyed, add="+")
        for sequence in self._events:
            if sequence == "<TouchpadScroll>" and not supports_tk_event(
                frame, sequence
            ):
                continue
            self._commands.append(frame.bind_class(self._tag, sequence, self._input))
        for root in self.outgoing:
            for widget in self._walk(root):
                widget.event_generate("<<ViewInputRetired>>", when="now")
                widget.bindtags((self._tag, *widget.bindtags()))
                self._guarded.append(widget)
        for widget in self.incoming:
            widget.lower()

    @staticmethod
    def _walk(root: Any) -> Any:
        yield root
        for child in root.winfo_children():
            yield from WidgetReveal._walk(child)

    @staticmethod
    def _excluded_canvas_content(widget: Any) -> bool:
        manager = widget.winfo_manager()
        if manager == "place":
            anchor = widget.place_info().get("in")
            if anchor and str(anchor) != str(widget.master):
                target = widget.nametowidget(str(anchor))
                return WidgetReveal._excluded_canvas_content(target)
        if manager != "canvas" or not isinstance(widget.master, tk.Canvas):
            return False
        canvas = widget.master
        for item in canvas.find_all():
            if canvas.type(item) != "window" or canvas.itemcget(item, "window") != str(
                widget
            ):
                continue
            if canvas.itemcget(item, "state") == "hidden":
                return True
            bounds = canvas.bbox(item)
            if bounds is None:
                return False
            left, top = canvas.canvasx(0), canvas.canvasy(0)
            right, bottom = left + canvas.winfo_width(), top + canvas.winfo_height()
            return (
                bounds[2] <= left
                or bounds[0] >= right
                or bounds[3] <= top
                or bounds[1] >= bottom
            )
        return False

    @staticmethod
    def _managed(root: Any) -> Any:
        # Unmanaged branches are intentionally hidden; their managed descendants
        # cannot become viewable until their owner chooses to show that branch.
        # Tk also unmaps canvas windows outside the viewport (and their placed
        # hints). They cannot become ready without a later scroll, so they must
        # not hold the current visible presentation behind its outgoing cover.
        if root.winfo_manager() and not WidgetReveal._excluded_canvas_content(root):
            yield root
            for child in root.winfo_children():
                yield from WidgetReveal._managed(child)

    def _input(self, event: Any) -> str:
        if (
            getattr(event, "keysym", "") == "Escape"
            and event.type == tk.EventType.KeyPress
        ):
            self.escape()
        return "break"

    def start(self, ready: Any = None) -> None:
        if not self.active or self.timer is not None:
            return
        self.ready = ready
        self.timer = self.frame.after_idle(self._attempt)

    def _attempt(self) -> None:
        self.timer = None
        if not self.active:
            return
        try:
            if not self.current() or not self.frame.winfo_exists():
                self.cancel()
                return
            managed = [w for root in self.incoming for w in self._managed(root)]
            complete = bool(managed) and all(
                w.winfo_ismapped() and w.winfo_width() > 1 and w.winfo_height() > 1
                for w in managed
            )
            if not complete or (self.ready is not None and not self.ready()):
                self.timer = self.frame.after(8, self._attempt)
                return
            focus = self.frame.focus_get()
            if focus in self._guarded:
                self.frame.focus_set()
            for widget in self.outgoing:
                widget.grid_remove()
            for widget in self.incoming:
                widget.lift()
            self.cancel()
        except tk.TclError:
            self.cancel()

    def cancel(self) -> None:
        if not self.active:
            return
        self.active = False
        if self.timer is not None:
            try:
                self.frame.after_cancel(self.timer)
            except tk.TclError:
                pass
            self.timer = None
        for widget in self._guarded:
            try:
                widget.bindtags(
                    tuple(tag for tag in widget.bindtags() if tag != self._tag)
                )
            except tk.TclError:
                pass
        self._guarded.clear()
        for sequence in self._events:
            try:
                self.frame.unbind_class(self._tag, sequence)
            except tk.TclError:
                pass
        for command in self._commands:
            try:
                # bind_class registers callbacks on the Tk root, which also
                # owns their teardown list. Remove from that same owner.
                self.frame._root().deletecommand(command)
            except tk.TclError:
                pass
        self._commands.clear()
        try:
            self.frame.unbind("<Destroy>", self._destroy_binding)
        except tk.TclError:
            pass
        self.outgoing = self.incoming = ()
        finished, self.finished = self.finished, None
        self.ready = self.current = self.escape = None
        if finished is not None:
            finished()

    def _destroyed(self, event: Any) -> None:
        if event.widget is self.frame:
            self.cancel()
