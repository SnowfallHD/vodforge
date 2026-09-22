"""Static bypass inventory complements rendered checks; it is not visual approval."""

from __future__ import annotations

import ast
from pathlib import Path


def theme_default_bypasses(source: str) -> list[int]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if default is not None and any(
                    isinstance(n, ast.Name) and n.id == "THEME"
                    for n in ast.walk(default)
                ):
                    found.append(node.lineno)
    return found


def family_material_bypasses(source: str) -> list[int]:
    """UI adapters may place icons/targets, but not clone raster face shading."""
    names = {"rounded_rectangle"}
    return sorted(
        {
            node.lineno
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in names
        }
    )


def inventory(root: Path) -> dict:
    names = (
        "ui_widgets.py",
        "scene_components.py",
        "ui_button_contract.py",
        "ui_context_menu.py",
        "media_player_ui.py",
        "library_scene_layout.py",
    )
    return {
        name: {
            "theme_defaults": theme_default_bypasses(
                (root / "yt_downloader" / name).read_text()
            ),
            "local_raster_faces": family_material_bypasses(
                (root / "yt_downloader" / name).read_text()
            ),
        }
        for name in names
    }
