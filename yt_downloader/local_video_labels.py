"""Presentation labels for durable still-image conversion profiles."""

LOCAL_VIDEO_DISPLAY_LABELS = {
    "1080p Standard (Recommended)": "Everyday",
    "2160p 4K": "4K",
    "1080p Strict 2 Mbps CBR": "Broadcast",
    "720p Compact": "Smaller File",
}


def local_video_profile_label(value: str) -> str:
    return LOCAL_VIDEO_DISPLAY_LABELS.get(value, value)


def local_video_profile_value(value: str) -> str:
    """Accept a display choice without changing its persisted identity."""
    return next(
        (key for key, label in LOCAL_VIDEO_DISPLAY_LABELS.items() if label == value),
        value,
    )


def local_video_profile_text(value: str) -> str:
    """Project known generated labels only; never rewrite arbitrary user text."""
    historical = {
        "1080p • Standard": "1080p Standard (Recommended)",
        "2160p • 4K": "2160p 4K",
        "1080p • Strict 2 Mbps CBR": "1080p Strict 2 Mbps CBR",
        "720p • Compact": "720p Compact",
    }
    lines = value.split("\n")
    for index, line in enumerate(lines):
        for old, profile in historical.items():
            if line == f"MP4 • {old} • Static image":
                resolution = old.split(" • ")[0]
                lines[index] = (
                    f"MP4 • {resolution} • {local_video_profile_label(profile)} • Static image"
                )
        for profile, label in LOCAL_VIDEO_DISPLAY_LABELS.items():
            if line == f"Static-image MP4 encoded with {profile} and validated.":
                lines[index] = f"Static-image MP4 encoded with {label} and validated."
    return "\n".join(lines)
