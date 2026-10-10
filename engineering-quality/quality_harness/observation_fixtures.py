"""Relocate retained observations as values, before serializing their JSON."""

from __future__ import annotations

from pathlib import PurePath
from typing import Any


def relocate_observation(value: Any, old_root: str, destination: PurePath) -> Any:
    """Clone an observation while keeping native path separators and JSON escaping.

    Relative manifest keys and provider URLs stay unchanged. Embedded diagnostic
    text retains its original formatting; whole paths and path-valued CLI options
    use the destination's path flavour.
    """
    if isinstance(value, dict):
        return {
            key: relocate_observation(item, old_root, destination)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [relocate_observation(item, old_root, destination) for item in value]
    if not isinstance(value, str) or old_root not in value:
        return value
    prefix = ""
    path = value
    if value.startswith("--") and "=" in value:
        option, path = value.split("=", 1)
        prefix = option + "="
    if path == old_root or path.startswith(old_root + "/"):
        suffix = path[len(old_root) :].lstrip("/")
        return prefix + str(destination.joinpath(*suffix.split("/")))
    return value.replace(old_root, str(destination))
