from __future__ import annotations

from typing import Any

from .windowing import _native_window


def _bitmap_rep_image(rep: Any) -> Any:
    """Detach supported opaque native pixels; preserve PNG for other formats."""
    import io

    from PIL import Image

    width, height, stride = (
        int(rep.pixelsWide()),
        int(rep.pixelsHigh()),
        int(rep.bytesPerRow()),
    )
    if (
        0 < width * height <= 16_000_000
        and width > 0
        and height > 0
        and rep.bitsPerSample() == 8
        and rep.samplesPerPixel() == 4
        and rep.bitsPerPixel() == 32
        and rep.bitmapFormat() == 0
        and not rep.isPlanar()
        and stride >= width * 4
    ):
        try:
            storage = memoryview(rep.bitmapData())
        except TypeError:
            storage = None
        # PyObjC may expose an unsized varlist instead of a buffer. Let the
        # native encoder handle storage that cannot safely be borrowed.
        if (
            storage is not None
            and storage.c_contiguous
            and storage.nbytes >= stride * height
        ):
            pixels = storage.cast("B")
            bitmap = Image.frombuffer(
                "RGBA", (width, height), pixels, "raw", "RGBA", stride, 1
            )
            # Format zero can contain premultiplied alpha. Only opaque pixels
            # bypass the native encoder's alpha/color-format handling.
            if bitmap.getchannel("A").getextrema() == (255, 255):
                return bitmap.copy()  # Never return a borrowed native buffer.

    from AppKit import NSBitmapImageFileTypePNG

    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    with Image.open(io.BytesIO(bytes(data))) as bitmap:
        return bitmap.convert("RGBA")


def capture_own_widget(widget: Any, width: int, height: int) -> Any:
    from PIL import Image

    root = widget.winfo_toplevel()
    view = _native_window(root).contentView()
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    bitmap = _bitmap_rep_image(rep)
    sx = bitmap.width / bounds.size.width
    sy = bitmap.height / bounds.size.height
    x = widget.winfo_rootx() - root.winfo_rootx()
    y = widget.winfo_rooty() - root.winfo_rooty()
    return (
        bitmap.crop(
            (
                round(x * sx),
                round(y * sy),
                round((x + width) * sx),
                round((y + height) * sy),
            )
        )
        .resize((width, height), Image.Resampling.BILINEAR)
        .convert("RGB")
    )


def surface_backing_scale(widget: Any) -> int:
    try:
        return max(
            1,
            min(3, round(_native_window(widget.winfo_toplevel()).backingScaleFactor())),
        )
    except (ImportError, AttributeError, RuntimeError, ValueError):
        pass
    # Styles are installed before Tk maps its first NSWindow. Use the native
    # display scale then, rather than permanently installing 1x ttk images.
    try:
        from AppKit import NSScreen

        screen = NSScreen.mainScreen()
        if screen is not None:
            return max(1, min(3, round(screen.backingScaleFactor())))
    except (ImportError, AttributeError, RuntimeError, ValueError):
        pass
    return 1


def create_surface_image(
    widget: Any,
    bitmap: Any,
    scale: int,
    *,
    logical_size: tuple[int, int],
    existing: Any = None,
) -> tuple[Any, int] | None:
    import io
    import tkinter as tk
    from uuid import uuid4

    from PIL import Image

    width, height = logical_size
    try:
        supported = "nsimage" in widget.tk.call("image", "types")
        if supported:
            from AppKit import NSImage
            from Foundation import NSData

            physical_size = (width * scale, height * scale)
            pixels = (
                bitmap
                if bitmap.size == physical_size
                else bitmap.resize(physical_size, Image.Resampling.BILINEAR)
            )
            stream = io.BytesIO()
            # This is an in-memory transport, not an archival file. The
            # low compression setting preserves pixels while reducing
            # encoding work on the UI thread.
            pixels.save(stream, format="PNG", compress_level=1)
            encoded = stream.getvalue()
            data = NSData.dataWithBytes_length_(encoded, len(encoded))
            native = NSImage.alloc().initWithData_(data)
            if native is not None:
                name = "VODForgeSurface-" + uuid4().hex
                if native.setName_(name):
                    try:
                        if (
                            existing is not None
                            and existing.tk is widget.tk
                            and widget.tk.call("image", "type", str(existing))
                            == "nsimage"
                        ):
                            # Update the representation in place: ttk elements
                            # and canvas items retain this exact Tcl image name.
                            existing.configure(source=name, width=width, height=height)
                            photo = existing
                        else:
                            photo = tk.Image(
                                "nsimage",
                                master=widget,
                                source=name,
                                width=width,
                                height=height,
                            )
                        # Tk maintains normal/dark representations. Count both
                        # at physical area plus encoded data, conservatively.
                        return photo, width * height * scale * scale * 8 + len(encoded)
                    finally:
                        native.setName_(None)
    except (ImportError, AttributeError, RuntimeError, ValueError, tk.TclError):
        pass
    return None


def present_pending_drawing(widget: Any, *, child_canvas_only: bool = False) -> bool:
    import _tkinter
    import time
    import tkinter as tk

    if not isinstance(widget, tk.Misc) or not widget.tk.call(
        "info", "commands", str(widget)
    ):
        return True
    if child_canvas_only and (
        not isinstance(widget, tk.Canvas) or not widget.winfo_children()
    ):
        return True
    root = widget.winfo_toplevel()
    if getattr(root, "_vodforge_scroll_drawing", False):
        return False
    root.__dict__["_vodforge_scroll_drawing"] = True
    try:
        deadline = time.monotonic() + 0.040
        for _ in range(6):
            if not widget.tk.call("info", "commands", str(widget)):
                return True
            if not widget.tk.dooneevent(_tkinter.IDLE_EVENTS | _tkinter.DONT_WAIT):
                return True
            if time.monotonic() >= deadline:
                return False
        return False
    finally:
        root.__dict__["_vodforge_scroll_drawing"] = False
