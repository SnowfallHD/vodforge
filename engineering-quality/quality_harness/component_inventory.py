"""Reproducible static action-site inventory; native checks establish live adoption."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any


def scan_button_sites(root: Path) -> dict[str, Any]:
    sites = []
    violations = []
    for path in sorted((root / "yt_downloader").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {
            child: node
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = ast.unparse(node.func)
            if callee not in {"ProductButton", "ttk.Button", "tk.Button", "p.button"}:
                continue
            owner = node
            while owner in parents and not isinstance(
                owner, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                owner = parents[owner]
            keywords = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
            label = keywords.get(
                "text",
                ast.unparse(node.args[3])
                if callee == "p.button" and len(node.args) > 3
                else "",
            )
            overrides = {
                key: value
                for key, value in keywords.items()
                if key in {"height", "size", "font", "padding"}
            }
            site = {
                "file": str(path.relative_to(root)),
                "line": node.lineno,
                "owner": getattr(owner, "name", "module"),
                "adapter": callee,
                "label": label,
                "style": keywords.get(
                    "style",
                    "TButton" if callee in {"ProductButton", "ttk.Button"} else "scene",
                ),
                "overrides": overrides,
            }
            sites.append(site)
            if callee in {"tk.Button", "ttk.Button"} or overrides:
                violations.append(site)
    return {
        "scope": "Static constructor/render-call inventory; runtime branches and multiplicity require native evidence.",
        "counts": dict(Counter(site["adapter"] for site in sites)),
        "style_expressions": dict(
            Counter(
                site["style"]
                for site in sites
                if site["adapter"] in {"ProductButton", "ttk.Button"}
            )
        ),
        "violations": violations,
        "sites": sites,
    }


def refresh_control_families(root: Path, previous: dict[str, Any]) -> dict[str, Any]:
    """Refresh explicitly reviewed family names, preserving incomplete qualification."""
    families = previous["families"]
    names = {name for family in families.values() for name in family["owners"]}
    definitions = {}
    sites: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    for path in sorted((root / "yt_downloader").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name in names:
                definitions[node.name] = {
                    "file": str(path.relative_to(root)),
                    "line": node.lineno,
                    "bases": [ast.unparse(base) for base in node.bases],
                }
            if isinstance(node, ast.Call) and ast.unparse(node.func) in names:
                sites[ast.unparse(node.func)].append(
                    {
                        "file": str(path.relative_to(root)),
                        "line": node.lineno,
                        "keywords": {
                            kw.arg: ast.unparse(kw.value)
                            for kw in node.keywords
                            if kw.arg
                            in {
                                "font",
                                "height",
                                "width",
                                "padding",
                                "style",
                                "takefocus",
                                "orient",
                            }
                        },
                    }
                )
    return {
        "scope": previous["scope"],
        "families": {
            key: {
                "qualification": "incomplete",
                "owners": {
                    name: {
                        "definition": definitions.get(name),
                        "direct_call_count": len(sites[name]),
                        "sites": sites[name],
                    }
                    for name in family["owners"]
                },
            }
            for key, family in families.items()
        },
    }
