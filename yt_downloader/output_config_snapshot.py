"""Allowlisted display provenance; never restores download authentication."""

from collections.abc import Mapping
from typing import Any

from .models import DownloadJob, OutputType
from .youtube_access import COOKIE_BROWSER_VALUES

OUTPUT_CONFIG_DISPLAY_KEY = "vodforge_output_config_display"


def sanitize_output_config_display(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or value.get("access") not in {
        "Public",
        "Browser",
        "cookies.txt",
    }:
        return None
    access = value["access"]
    raw_browser = str(value.get("browser") or "")
    browser = (
        next(
            (
                name
                for name, raw in COOKIE_BROWSER_VALUES.items()
                if raw_browser.casefold() in {name.casefold(), raw}
            ),
            "",
        )
        if access == "Browser"
        else ""
    )
    applicable = value.get("nvenc_applicable")
    return {
        "access": access,
        "browser": browser,
        "nvenc_applicable": applicable if type(applicable) is bool else None,
    }


def output_config_display(job: DownloadJob) -> dict[str, Any]:
    access = (
        "Public"
        if not job.use_cookies
        else "Browser"
        if job.cookie_browser
        else "cookies.txt"
    )
    display = sanitize_output_config_display(
        {
            "access": access,
            "browser": job.cookie_browser,
            "nvenc_applicable": job.nvenc_applicable
            if job.output_type == OutputType.MP4
            else False,
        }
    )

    assert display is not None
    return display
