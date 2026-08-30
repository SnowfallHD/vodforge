from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


def _definitions(source_path: Path) -> list[dict[str, Any]]:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions: list[dict[str, Any]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _visit_definition(self, node: ast.AST, name: str, kind: str) -> None:
            qualified = ".".join([*self.stack, name])
            end = int(getattr(node, "end_lineno", getattr(node, "lineno", 0)))
            start = int(getattr(node, "lineno", 0))
            definitions.append(
                {
                    "name": qualified,
                    "kind": kind,
                    "line": start,
                    "end_line": end,
                    "lines": end - start + 1,
                }
            )
            self.stack.append(name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._visit_definition(node, node.name, "class")

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_definition(node, node.name, "function")

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_definition(node, node.name, "async_function")

    Visitor().visit(tree)
    return definitions


def change_surface_probe(
    repo_root: Path, harness_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    probes = json.loads(
        (harness_root / "maintainability" / "change-probes.json").read_text(
            encoding="utf-8"
        )
    )["probes"]
    searchable = [
        *sorted((repo_root / "yt_downloader").glob("*.py")),
        *sorted((repo_root / "tests").glob("test_*.py")),
    ]
    results: list[dict[str, Any]] = []
    for probe in probes:
        file_hits: dict[str, dict[str, int]] = {}
        for path in searchable:
            text = path.read_text(encoding="utf-8")
            anchor_hits = {
                anchor: text.count(anchor)
                for anchor in probe["anchors"]
                if anchor in text
            }
            if anchor_hits:
                file_hits[str(path.relative_to(repo_root))] = anchor_hits
        production_files = [
            path for path in file_hits if path.startswith("yt_downloader/")
        ]
        test_files = [path for path in file_hits if path.startswith("tests/")]
        results.append(
            {
                **probe,
                "files_touched_by_anchors": len(file_hits),
                "production_files": production_files,
                "test_files": test_files,
                "references": file_hits,
            }
        )

    app_path = repo_root / "yt_downloader" / "app.py"
    line_count = len(app_path.read_text(encoding="utf-8").splitlines())
    definitions = _definitions(app_path)
    oversized = sorted(
        (item for item in definitions if item["lines"] >= 100),
        key=lambda item: item["lines"],
        reverse=True,
    )
    largest = oversized[:20]
    app_class = next(
        (item for item in definitions if item["name"] == "DownloaderApp"), None
    )
    worker = next(
        (
            item
            for item in definitions
            if item["name"].endswith("DownloaderApp._download_worker_single")
        ),
        None,
    )
    findings: list[dict[str, Any]] = []
    if line_count >= 5000 or (worker and worker["lines"] >= 300):
        findings.append(
            {
                "id": "MAINT-MONOLITH-001",
                "title": "The real pipeline is headless-testable but structurally coupled to a very large Tk module",
                "classification": "maintainability risk",
                "severity": "medium",
                "area": "yt_downloader/app.py DownloaderApp and _download_worker_single",
                "reproduction": [
                    "Parse production Python definitions with the standard AST.",
                    "Measure module, class, and worker spans.",
                    "Map realistic change anchors across production and tests.",
                ],
                "evidence": [
                    f"app.py lines: {line_count}",
                    f"DownloaderApp span: {(app_class or {}).get('lines')} lines",
                    f"_download_worker_single span: {(worker or {}).get('lines')} lines",
                    f"Definitions >=100 lines: {len(oversized)}",
                ],
                "suggested_fix": "After behavior is protected by this harness, extract a UI-independent orchestration service and typed event protocol without changing the existing export/path/history sources of truth.",
                "scenario_id": "maintainability.change_surface",
            }
        )
    scenario = {
        "id": "maintainability.change_surface",
        "evidence_tier": "unit_static",
        "category": "maintainability",
        "status": "failed" if findings else "passed",
        "duration_seconds": 0.0,
        "metrics": {
            "app_module_lines": line_count,
            "downloader_app_lines": (app_class or {}).get("lines"),
            "download_worker_lines": (worker or {}).get("lines"),
            "definitions_at_least_100_lines": len(oversized),
            "change_probes": results,
            "largest_definitions": largest,
        },
        "evidence": [
            f"Measured {line_count} lines in app.py.",
            f"Measured {(worker or {}).get('lines')} lines in the real headless worker seam.",
            f"Mapped {len(results)} realistic change surfaces with production/test reference counts.",
        ],
        "artifacts": [str(harness_root / "maintainability" / "change-probes.json")],
        "error": None,
    }
    return scenario, findings
