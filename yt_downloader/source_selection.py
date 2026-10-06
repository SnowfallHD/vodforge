"""Closed, scalar source-selection observations; never provider payloads."""

SELECTION_CHOICES = {
    "selection_decision": frozenset(
        {
            "split",
            "progressive",
            "progressive_fallback",
            "no_audio",
            "no_video",
            "hdr_rejected",
        }
    ),
    "selection_has_audio": frozenset({"yes", "no", "unselected"}),
    "selection_scope": frozenset({"item", "last_analyzed_item"}),
}
SELECTION_RANGES = {
    **{
        key: (0, 10000)
        for key in (
            "selection_video_only_count",
            "selection_audio_only_count",
            "selection_av_count",
            "selection_same_tier_av_count",
            "selection_usable_av_count",
        )
    },
    "selection_max_height": (0, 100000),
    "selection_video_tier": (0, 100000),
}


def selection_observation(value: dict[str, str], *, scope: str) -> dict[str, str]:
    """Fail closed on partial/untrusted records rather than serializing extras."""
    expected = set(SELECTION_CHOICES) | set(SELECTION_RANGES)
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or scope not in SELECTION_CHOICES["selection_scope"]
    ):
        return {}
    for key, choices in SELECTION_CHOICES.items():
        if not isinstance(value[key], str) or value[key] not in choices:
            return {}
    for key, (low, high) in SELECTION_RANGES.items():
        item = value[key]
        if (
            not isinstance(item, str)
            or len(item) > 6
            or not item.isascii()
            or not item.isdecimal()
            or str(int(item)) != item
            or not low <= int(item) <= high
        ):
            return {}
    return {**value, "selection_scope": scope}
