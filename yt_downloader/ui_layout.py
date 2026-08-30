from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .platform_services import is_macos

INITIAL_WINDOW_MAX_WIDTH = 1180
INITIAL_WINDOW_MAX_HEIGHT = 900
FOCUS_COMPACT_WIDTH = 920
FOCUS_COMPACT_HEIGHT = 690
FOCUS_WIDE_WIDTH = 1080
FOCUS_WIDE_HEIGHT = 760
LIBRARY_WIDE_WIDTH = 1000
LIBRARY_COMPACT_HEIGHT = 740
LIBRARY_WIDE_HEIGHT = 920
LIBRARY_MAX_CONTENT_WIDTH = 1600
LIBRARY_MIN_HORIZONTAL_PADDING = 18
LIBRARY_CENTERING_STEP = 32
FOCUS_RUN_CARD_WIDTH = 220
FOCUS_HERO_THUMBNAIL_MIN_WIDTH = 720
LIBRARY_THUMBNAIL_MAX_WIDTH = 240


class _WindowGeometryOwner(Protocol):
    def winfo_rootx(self) -> int: ...

    def winfo_rooty(self) -> int: ...

    def winfo_width(self) -> int: ...

    def winfo_height(self) -> int: ...


def centered_toplevel_geometry(
    owner: _WindowGeometryOwner,
    width: int,
    height: int,
    *,
    minimum_x: int = 20,
    minimum_y: int = 40,
) -> str:
    """Return owner-centered geometry without mapping a Toplevel early."""
    x = max(minimum_x, owner.winfo_rootx() + (owner.winfo_width() - width) // 2)
    y = max(minimum_y, owner.winfo_rooty() + (owner.winfo_height() - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def bounded_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Choose an initial size that stays clear of common taskbar and dock areas."""
    width_margin = 80 if screen_width > 800 else 24
    height_margin = 120 if screen_height > 640 else 48
    return (
        max(1, min(INITIAL_WINDOW_MAX_WIDTH, screen_width - width_margin)),
        max(1, min(INITIAL_WINDOW_MAX_HEIGHT, screen_height - height_margin)),
    )


def initial_window_geometry(
    screen_width: int,
    screen_height: int,
    *,
    platform_name: str | None = None,
) -> str:
    """Place the first window fully on-screen instead of accepting OS cascade state."""
    width, height = bounded_window_size(screen_width, screen_height)
    x = max(0, (int(screen_width) - width) // 2)
    if is_macos(platform_name):
        # Keep a stable menu-bar gap and leave the existing height allowance
        # below the window for the Dock, even when macOS remembers a low
        # cascade position from a prior process.
        y = 28 if int(screen_height) > 640 else 20
    else:
        y = max(0, (int(screen_height) - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def focus_layout_mode(width: int, height: int) -> str:
    """Choose the Focus Deck density without introducing a page scrollbar."""
    if width < FOCUS_COMPACT_WIDTH or height < FOCUS_COMPACT_HEIGHT:
        return "compact"
    if width < FOCUS_WIDE_WIDTH or height < FOCUS_WIDE_HEIGHT:
        return "balanced"
    return "wide"


def focus_library_layout_mode(width: int) -> str:
    """Protect the selected item before the media table consumes medium widths."""
    if width < FOCUS_COMPACT_WIDTH:
        return "compact"
    if width < LIBRARY_WIDE_WIDTH:
        return "balanced"
    return "wide"


def focus_library_vertical_layout_mode(height: int) -> str:
    """Protect the selected-details reader as vertical room is reduced."""
    if int(height) < LIBRARY_COMPACT_HEIGHT:
        return "compact"
    if int(height) < LIBRARY_WIDE_HEIGHT:
        return "balanced"
    return "wide"


def stretched_table_column_widths(
    widths: Iterable[int],
    available_width: int,
    stretch_limits: dict[int, int | None],
) -> list[int]:
    """Distribute spare viewport width across every eligible table column."""
    result = [max(1, int(width)) for width in widths]
    remaining = max(0, int(available_width) - sum(result))
    active = [
        index
        for index in sorted(stretch_limits)
        if 0 <= index < len(result)
        and ((limit := stretch_limits[index]) is None or result[index] < int(limit))
    ]
    while remaining > 0 and active:
        share = max(1, remaining // len(active))
        progressed = False
        for index in tuple(active):
            if remaining <= 0:
                break
            limit = stretch_limits[index]
            headroom = (
                remaining if limit is None else max(0, int(limit) - result[index])
            )
            addition = min(remaining, share, headroom)
            if addition > 0:
                result[index] += addition
                remaining -= addition
                progressed = True
        active = [
            index
            for index in active
            if (limit := stretch_limits[index]) is None or result[index] < int(limit)
        ]
        if not progressed:
            break
    return result


def responsive_table_stretch_indices(
    columns: Iterable[str],
    stretch_columns: Iterable[str],
    manually_resized_columns: Iterable[str],
    *,
    resizing_column: str | None = None,
    last_resized_column: str | None = None,
) -> list[int]:
    """Choose responsive fill columns without moving the active divider."""
    ordered = list(columns)
    eligible = set(stretch_columns)
    manual = set(manually_resized_columns)
    automatic = [
        index
        for index, column in enumerate(ordered)
        if column in eligible and column not in manual and column != resizing_column
    ]
    if automatic:
        return automatic
    # Once every eligible column has been touched, keep the most recently
    # dragged divider exact and let the other columns share the fill. Their
    # stored bases remain unchanged, so shrinking and widening the frame does
    # not manufacture permanent widths or unnecessary horizontal overflow.
    return [
        index
        for index, column in enumerate(ordered)
        if column in eligible
        and column != resizing_column
        and column != last_resized_column
    ]


def resized_table_column_width(
    initial_width: int, delta: int, minimum_width: int
) -> int:
    """Clamp one user-resized table column without affecting its neighbors."""
    return max(int(minimum_width), int(initial_width) + int(delta))


def focus_library_horizontal_padding(
    width: int,
    *,
    maximum_content_width: int = LIBRARY_MAX_CONTENT_WIDTH,
) -> int:
    """Center a bounded Library workspace without per-pixel Grid reflows."""
    overflow = max(0, max(1, int(width)) - int(maximum_content_width))
    # A one-pixel padding update touches three managed Library surfaces. At
    # ultrawide sizes that needlessly reflows the hidden page throughout a
    # native frame drag, even while Forge is visible. Center in visually
    # indistinguishable 32 px window-width steps instead.
    return max(
        LIBRARY_MIN_HORIZONTAL_PADDING,
        (overflow // LIBRARY_CENTERING_STEP) * (LIBRARY_CENTERING_STEP // 2),
    )


def focus_run_deck_capacity(available_width: int, *, maximum: int = 4) -> int:
    """Show every run card that fits instead of collapsing by breakpoint."""
    safe_width = max(1, int(available_width))
    return max(1, min(max(1, int(maximum)), safe_width // FOCUS_RUN_CARD_WIDTH))


def focus_hero_thumbnail_visible(width: int) -> bool:
    """Keep the selected-run artwork until the window is genuinely narrow."""
    return int(width) >= FOCUS_HERO_THUMBNAIL_MIN_WIDTH


def focus_wheel_pixels(delta: float) -> int:
    """Normalize high-resolution trackpad and coarse wheel deltas to pixels."""
    raw_delta = float(delta)
    if raw_delta == 0:
        return 0
    pixels = -raw_delta
    if abs(raw_delta) >= 120:
        pixels = -round(raw_delta / 120) * 36
    magnitude = max(1, round(abs(pixels)))
    return int(max(-72, min(72, magnitude if pixels > 0 else -magnitude)))


def pixel_scroll_target(
    first: float,
    last: float,
    viewport_height: int,
    pixels: float,
) -> float:
    """Move a fraction-addressed viewport by real pixels.

    Text widgets use their native pixel-scroll command because their fractions
    can be temporarily stale while wrapped display-line metrics settle. This
    calculation remains the smooth fallback for Canvas-style surfaces whose
    current visible fraction is their scroll authority.
    """
    safe_first = max(0.0, min(1.0, float(first)))
    safe_last = max(safe_first, min(1.0, float(last)))
    visible_fraction = safe_last - safe_first
    if visible_fraction <= 0.0 or visible_fraction >= 0.999:
        return safe_first
    movement = float(pixels) * visible_fraction / max(1, int(viewport_height))
    return max(0.0, min(1.0 - visible_fraction, safe_first + movement))


def rounded_canvas_rectangle_points(
    width: int, height: int, radius: int
) -> tuple[float, ...]:
    """Return a smooth native-Canvas rounded rectangle without raster work."""
    right = max(1.0, float(width) - 1.0)
    bottom = max(1.0, float(height) - 1.0)
    curve = max(0.0, min(float(radius), right / 2.0, bottom / 2.0))
    return (
        curve,
        0.0,
        curve,
        0.0,
        right - curve,
        0.0,
        right - curve,
        0.0,
        right,
        0.0,
        right,
        curve,
        right,
        curve,
        right,
        bottom - curve,
        right,
        bottom - curve,
        right,
        bottom,
        right - curve,
        bottom,
        right - curve,
        bottom,
        curve,
        bottom,
        curve,
        bottom,
        0.0,
        bottom,
        0.0,
        bottom - curve,
        0.0,
        bottom - curve,
        0.0,
        curve,
        0.0,
        curve,
        0.0,
        0.0,
    )


def accumulated_row_scroll(
    remainder: float, pixels: int, row_pixels: int
) -> tuple[int, float]:
    """Accumulate high-resolution wheel motion before moving row widgets."""
    safe_row_pixels = max(1, int(row_pixels))
    total = float(remainder) + int(pixels)
    rows = int(total / safe_row_pixels)
    return rows, total - (rows * safe_row_pixels)


def pixel_table_visible_row_window(
    total_rows: int,
    row_height: int,
    viewport_height: int,
    y_offset: float,
) -> tuple[float, int, int]:
    """Clamp a virtual table viewport and include a small paint buffer."""
    safe_rows = max(0, int(total_rows))
    safe_row_height = max(1, int(row_height))
    safe_viewport = max(safe_row_height, int(viewport_height))
    content_height = max(safe_row_height, safe_rows * safe_row_height)
    clamped_offset = max(
        0.0, min(float(y_offset), max(0, content_height - safe_viewport))
    )
    first_row = max(0, int(clamped_offset // safe_row_height) - 1)
    last_row = min(
        safe_rows,
        int((clamped_offset + safe_viewport) // safe_row_height) + 2,
    )
    return clamped_offset, first_row, last_row


def youtube_thumbnail_size(width: int) -> tuple[int, int]:
    """Return the standard 16:9 thumbnail slot for a given display width."""
    safe_width = max(1, int(width))
    return safe_width, max(1, round(safe_width * 9 / 16))


def library_thumbnail_size(available_width: int) -> tuple[int, int]:
    """Keep Library artwork useful without crowding tags and description."""
    return youtube_thumbnail_size(
        min(max(1, int(available_width)), LIBRARY_THUMBNAIL_MAX_WIDTH)
    )


def thumbnail_size_within(
    source_size: tuple[int, int],
    maximum_size: tuple[int, int],
) -> tuple[int, int]:
    """Aspect-fit a thumbnail inside a maximum box without cropping or distortion."""
    source_width, source_height = source_size
    maximum_width, maximum_height = maximum_size
    if min(source_width, source_height, maximum_width, maximum_height) <= 0:
        return 1, 1
    scale = min(maximum_width / source_width, maximum_height / source_height)
    return max(1, round(source_width * scale)), max(1, round(source_height * scale))
