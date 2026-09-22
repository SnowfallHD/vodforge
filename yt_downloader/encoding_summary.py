"""Canonical source/output comparison fields shared by all information views."""

SUMMARY_COMPARISON_ROWS = [
    ("Format selector", "Source format selector used", None),
    ("Video format ID", "Video format ID", None),
    ("Audio format ID", "Audio format ID", None),
    ("Container/ext", "Source container/ext", "Output container"),
    ("Resolution", "Source resolution", "Output resolution"),
    ("Frame rate", "Source frame rate", "Output frame rate"),
    ("Video codec", "Source video codec", "Output video codec"),
    ("Video bitrate", "Source video bitrate", "Measured video bitrate"),
    ("Audio codec", "Source audio codec", "Output audio codec"),
    ("Audio bitrate", "Source audio bitrate", "Measured audio bitrate"),
    ("Audio sample rate", "Source audio sample rate", "Audio sample rate"),
    ("Audio channels", "Source audio channels", "Audio channels"),
    ("HDR/SDR or pixel format", "HDR/SDR status", "Pixel format"),
    ("File size", "File size estimate", "Output file size"),
    (
        "Effective/target video bitrate",
        "Effective H.264-equivalent video bitrate",
        "Target video bitrate",
    ),
    (
        "Effective/target audio bitrate",
        "Effective AAC-equivalent audio bitrate",
        "Target audio bitrate",
    ),
    ("Selection/status", "Reason selected", "Validation status"),
]


AUDIO_SUMMARY_COMPARISON_ROWS = [
    ("Format selector", "Source format selector used", None),
    ("Audio format ID", "Audio format ID", None),
    ("Container/ext", "Source container/ext", "Output container"),
    ("Audio codec", "Source audio codec", "Output audio codec"),
    ("Audio bitrate", "Source audio bitrate", "Measured audio bitrate"),
    ("Audio sample rate", "Source audio sample rate", "Audio sample rate"),
    ("Audio channels", "Source audio channels", "Audio channels"),
    ("File size", "File size estimate", "Output file size"),
    (
        "Effective/target audio bitrate",
        "Effective MP3-equivalent audio bitrate",
        "Target audio bitrate",
    ),
    ("Selection/status", "Reason selected", "Validation status"),
]
