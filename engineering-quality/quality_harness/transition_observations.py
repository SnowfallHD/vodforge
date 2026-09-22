"""Detect mixed old/new regions in controlled abrupt view reveals."""

from PIL import ImageChops, ImageFilter, ImageStat


def classify_view_regions(observed, previous, destination, boxes):
    """Unrecognized pixels are unproven; this is not a universal animation oracle."""
    if observed.size != previous.size or observed.size != destination.size or not boxes:
        return {"status": "unproven", "regions": []}
    blurred = previous.filter(ImageFilter.GaussianBlur(1.4))

    def distance(a, b):
        return (
            sum(
                ImageStat.Stat(
                    ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
                ).mean
            )
            / 3
        )

    regions = []
    distinct_references = 0
    for box in boxes:
        x, y, right, bottom = box
        if not (
            0 <= x < right <= observed.width and 0 <= y < bottom <= observed.height
        ):
            return {"status": "unproven", "regions": regions}
        distinct_references += distance(previous.crop(box), destination.crop(box)) > 12
        current = observed.crop(box)
        old_distance = min(
            distance(current, previous.crop(box)), distance(current, blurred.crop(box))
        )
        new_distance = distance(current, destination.crop(box))
        state = (
            "unknown"
            if min(old_distance, new_distance) > 6
            else "old"
            if old_distance < 6 and new_distance > old_distance + 6
            else "new"
            if new_distance < 6 and old_distance > new_distance + 6
            else "shared"
        )
        regions.append(
            {
                "state": state,
                "old_distance": old_distance,
                "new_distance": new_distance,
                "box": box,
            }
        )
    states = [row["state"] for row in regions]
    mixed = states.count("old") >= 2 and states.count("new") >= 2
    status = (
        "failed"
        if mixed
        else "unproven"
        if "unknown" in states or distinct_references < 4
        else "passed"
    )
    return {
        "status": status,
        "regions": regions,
        "mixed_generations": mixed,
        "distinct_reference_regions": distinct_references,
    }


def content_regions(size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Keep spatial sensitivity fixed as the content viewport grows."""
    width, height = size
    if width <= 60 or height <= 80:
        raise ValueError("Content viewport is too small for reference regions")
    return [
        (x, y, min(x + 230, width - 40), min(y + 130, height - 20))
        for y in range(60, height - 20, 130)
        for x in range(20, width - 40, 230)
    ]


def compare_unchanged_regions(observed, reference, regions, reference_regions):
    """Compare fixed-size controls whose state is unchanged but position can move.

    More than 0.5 percent of pixels changing by over 8 channel levels is a failure.
    This is a calibrated consistency check, not a general visual-design score.
    """
    references = {row["owner"]: row["bbox"] for row in reference_regions}
    if not regions or len(references) != len(reference_regions):
        raise ValueError("Missing or duplicate reference regions")
    if len({row["owner"] for row in regions}) != len(regions):
        raise ValueError("Duplicate observed regions")
    if set(references) - {row["owner"] for row in regions}:
        raise ValueError("Reference control is missing from observed regions")
    results = []
    for row in regions:
        owner, box = row["owner"], tuple(round(v) for v in row["bbox"])
        if owner not in references:
            raise ValueError("Observed control has no reference")
        expected_box = tuple(round(v) for v in references[owner])
        for image, bounds in [(observed, box), (reference, expected_box)]:
            x, y, right, bottom = bounds
            if not (0 <= x < right <= image.width and 0 <= y < bottom <= image.height):
                raise ValueError("Control region is outside captured pixels")
        actual = observed.crop(box).convert("RGB")
        expected = reference.crop(expected_box).convert("RGB")
        if actual.size != expected.size:
            results.append(
                {
                    "owner": owner,
                    "status": "unproven",
                    "matched": False,
                    "reason": "Control dimensions changed",
                }
            )
            continue
        channels = ImageChops.difference(actual, expected).split()
        maximum = ImageChops.lighter(
            ImageChops.lighter(channels[0], channels[1]), channels[2]
        )
        changed = sum(maximum.histogram()[9:])
        allowance = int(actual.width * actual.height * 0.005)
        results.append(
            {
                "owner": owner,
                "status": "passed" if changed <= allowance else "failed",
                "matched": changed <= allowance,
                "changed_pixels": changed,
                "allowed_changed_pixels": allowance,
                "size": list(actual.size),
            }
        )
    return results
