"""Validated explicit feedback and public-review payloads shared by both UIs."""

from __future__ import annotations

import platform
from typing import Any

from .support_diagnostics import (
    FailureContext,
    diagnostics_attachment,
    public_video_url,
)
from .version import __version__

REASONS = (
    "Download problem",
    "Playback problem",
    "Interface problem",
    "Suggestion",
    "Other",
)


def feedback_payload(
    *,
    reason: str,
    message: str,
    reply: bool = False,
    email: str = "",
    include_diagnostics: bool = False,
    include_video_url: bool = False,
    include_output_folder: bool = False,
    context: FailureContext | None = None,
) -> dict[str, Any]:
    if reason not in REASONS:
        raise ValueError("Please select a reason.")
    message = message.strip()
    if not message:
        raise ValueError("Please enter a message.")
    if len(message) > 2000:
        raise ValueError("Please keep your message to 2,000 characters.")
    email = email.strip() if reply else ""
    if len(email) > 254 or (
        email and ("@" not in email or any(c.isspace() for c in email))
    ):
        raise ValueError("Please check your reply email.")
    return {
        "app_version": __version__,
        "platform": platform.system(),
        "reason": reason,
        "message": message,
        "reply_email": email,
        "include_diagnostics": bool(include_diagnostics),
        "diagnostics": diagnostics_attachment(
            context,
            include_diagnostics=include_diagnostics,
            include_output_folder=include_output_folder,
        ),
        "include_video_url": bool(include_video_url),
        "video_url": (public_video_url(context.video_url or "") or "")
        if context and include_video_url
        else "",
    }


def review_payload(
    *, stars: int, comment: str, display_name: str = ""
) -> dict[str, Any]:
    if not 1 <= stars <= 5:
        raise ValueError("Choose a rating from 1 to 5 stars.")
    if len(display_name) > 80:
        raise ValueError("Please keep your display name to 80 characters.")
    comment = comment.strip()
    if len(comment) > 1000:
        raise ValueError("Please keep your comment to 1,000 characters.")
    return {
        "app_version": __version__,
        "platform": platform.system(),
        "stars": stars,
        "comment": comment,
        "display_name": display_name.strip() or "Anonymous",
        "publication_consent": True,
    }
