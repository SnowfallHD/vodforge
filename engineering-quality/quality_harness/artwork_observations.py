"""Independent pixels for controlled, distinct-owner artwork fixtures."""

from __future__ import annotations

from PIL import ImageStat


def inspect_artwork_centers(image, regions, palette):
    """Sample interior patches; this proves identity, not aspect or full composition."""
    observations = []
    for region in regions:
        owner = region["owner"]
        left, top, right, bottom = region["bbox"]
        if owner not in palette or not (
            0 <= left < right <= image.width and 0 <= top < bottom <= image.height
        ):
            raise ValueError("Missing owner or artwork outside captured window")
        fx, fy = region.get("identity_point", (0.5, 0.5))
        if not (0.05 <= fx <= 0.95 and 0.05 <= fy <= 0.95):
            raise ValueError("Identity patch must remain inside artwork")
        x, y = round(left + (right - left) * fx), round(top + (bottom - top) * fy)
        patch = image.crop((x - 3, y - 3, x + 4, y + 4)).convert("RGB")
        observed = tuple(round(v) for v in ImageStat.Stat(patch).median)
        expected = tuple(palette[owner])
        distance = max(abs(a - b) for a, b in zip(observed, expected, strict=True))
        observations.append(
            {
                "owner": owner,
                "expected": expected,
                "observed": observed,
                "distance": distance,
                "matched": distance <= 30,
            }
        )
    return observations


def inspect_artwork_shapes(image, regions):
    """Evaluate a centered white calibration ring, independently of fit code.

    Fixtures use a circle whose diameter is 3/4 of the shorter source edge.
    Square cover crops must preserve its shape, center and complete circumference.
    This evaluates calibrated avatar composition, not arbitrary artwork aesthetics.
    """
    import math

    observations = []
    for region in regions:
        left, top, right, bottom = region["bbox"]
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError("Artwork outside captured window")
        patch = image.crop(tuple(round(v) for v in (left, top, right, bottom))).convert(
            "RGB"
        )
        width, height = patch.size
        if abs(width - height) > 1 or min(width, height) < 24:
            raise ValueError("Calibration requires a resolved square avatar")
        points = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if min(pixel := patch.getpixel((x, y))) >= 205
            and max(pixel) - min(pixel) <= 18
        ]
        expected = 0.75 * min(width, height)
        extent = None
        centered = aspect = span = ring = complete = False
        sectors = [0] * 8
        if points:
            xs, ys = zip(*points, strict=True)
            extent = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
            dx, dy = extent[2] - extent[0], extent[3] - extent[1]
            centered = (
                abs((extent[0] + extent[2]) / 2 - width / 2) <= 2.5
                and abs((extent[1] + extent[3]) / 2 - height / 2) <= 2.5
            )
            aspect = abs(dx - dy) <= 3
            span = abs(dx - expected) <= 3.5 and abs(dy - expected) <= 3.5
            in_band = 0
            for x, y in points:
                xx, yy = x + 0.5 - width / 2, y + 0.5 - height / 2
                radius = math.hypot(xx, yy) / (expected / 2)
                in_band += 0.80 <= radius <= 1.08
                sector = int((math.atan2(yy, xx) + math.pi) * 4 / math.pi) % 8
                sectors[sector] += 1
            ring = in_band / len(points) >= 0.95
            complete = min(sectors) >= max(2, len(points) * 0.05)
        checks = {
            "centered": centered,
            "circular": aspect,
            "expected_span": span,
            "ring_shape": ring,
            "complete_circumference": complete,
        }
        observations.append(
            {
                "owner": region["owner"],
                "extent": extent,
                "white_pixels": len(points),
                "sectors": sectors,
                "checks": checks,
                "matched": all(checks.values()),
            }
        )
    return observations
