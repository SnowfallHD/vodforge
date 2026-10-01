"""Discover Qt binding candidates; observed paths never imply visual acceptance."""

from __future__ import annotations

import argparse
import ast
import hashlib
import heapq
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# Mask comments and strings before balancing braces. This is a lexical inventory,
# not a QML compiler: dynamic creation and JavaScript-generated controls are unknown.
_MASK = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_OBJECT = re.compile(r"\b([A-Z]\w*(?:\.\w+)*)\s*\{")
_BINDING = re.compile(r"\b(on[A-Z]\w*)\s*:")
_SIGNAL = re.compile(r"\bsignal\s+(\w+)\s*\(")
_STEPS = frozenset({"navigation", "menu", "selection", "action", "confirmation"})


def _masked(text: str) -> str:
    return _MASK.sub(lambda m: "".join("\n" if c == "\n" else " " for c in m[0]), text)


def scan_qml(path: str, text: str) -> dict[str, Any]:
    """Retain all handler candidates, including unresolved lifecycle handlers."""
    masked = _masked(text)
    stack = []
    ends = {}
    for i, char in enumerate(masked):
        if char == "{":
            stack.append(i)
        elif char == "}" and stack:
            ends[stack.pop()] = i
    objects = []
    for match in _OBJECT.finditer(masked):
        start = masked.find("{", match.start(), match.end())
        end = ends.get(start, len(text))
        objects.append((start, end, match[1]))
    sites = []
    for kind, pattern in [("handler", _BINDING), ("signal", _SIGNAL)]:
        for match in pattern.finditer(masked):
            owners = [o for o in objects if o[0] < match.start() < o[1]]
            owner = max(owners, default=(0, len(text), "unknown"), key=lambda o: o[0])
            # Keep only properties in the same object, excluding nested objects.
            own = list(masked[owner[0] : owner[1]])
            for child in objects:
                if owner[0] < child[0] < child[1] < owner[1]:
                    own[child[0] - owner[0] : child[1] - owner[0] + 1] = " " * (
                        child[1] - child[0] + 1
                    )
            own_mask = "".join(own)
            properties = {}
            for prop in ("id", "objectName", "visible", "enabled", "label", "text"):
                found = re.search(r"\b" + prop + r"\s*:", own_mask)
                if found:
                    begin = owner[0] + found.end()
                    finish = text.find("\n", begin)
                    properties[prop] = text[
                        begin : finish if finish >= 0 else owner[1]
                    ].strip()
            begin = match.end()
            while begin < len(masked) and masked[begin].isspace():
                begin += 1
            block_start = begin
            if kind == "handler" and masked[begin:].startswith("function"):
                block_start = masked.find("{", begin)
            end = (
                ends.get(block_start, masked.find("\n", begin))
                if kind == "handler"
                else masked.find("\n", begin)
            )
            if end < 0:
                end = len(text)
            expression = text[
                begin : end + (masked[block_start : block_start + 1] == "{")
            ].strip()
            line = text.count("\n", 0, match.start()) + 1
            sites.append(
                {
                    "site": f"{path}:{line}:{match[1]}",
                    "file": path,
                    "line": line,
                    "kind": kind,
                    "binding": match[1],
                    "owner_type": owner[2],
                    "ancestors": [
                        {
                            "type": o[2],
                            "line": text.count("\n", 0, o[0]) + 1,
                            "id": (
                                re.search(
                                    r"\bid\s*:\s*(\w+)", masked[o[0] : o[1]]
                                ).group(1)
                                if re.search(r"\bid\s*:\s*(\w+)", masked[o[0] : o[1]])
                                else ""
                            ),
                        }
                        for o in sorted(owners)
                        if any(w in o[2] for w in ("Popup", "Dialog", "Menu"))
                    ],
                    "properties": properties,
                    "expression": expression,
                    "binding_sha256": hashlib.sha256(expression.encode()).hexdigest(),
                    "file_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "calls": sorted(
                        set(
                            re.findall(
                                r"\b([A-Za-z_]\w*(?:\.\w+)*)\s*\(", _masked(expression)
                            )
                        )
                    ),
                }
            )
    return {
        "file": path,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "object_candidates": len(objects),
        "contexts": [
            {"id": f"{path}:{text.count(chr(10), 0, start) + 1}:{kind}", "type": kind}
            for start, _end, kind in objects
            if any(word in kind for word in ("Popup", "Dialog", "Menu"))
        ],
        "unbalanced_braces": len(stack),
        "sites": sites,
    }


def _route_contexts(root: Path) -> list[dict[str, str]]:
    path = root / "yt_downloader/qt_quick/main.py"
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in {
                    "_library_scene_route",
                    "_watch_scene_route",
                }:
                    routes.add(
                        (
                            "Library" if "library" in target.attr else "Watch",
                            node.value.value,
                        )
                    )
        if isinstance(node, ast.FunctionDef) and node.name in {
            "navigateLibrary",
            "navigateWatch",
            "navigateLibraryFolders",
        }:
            for child in ast.walk(node):
                if isinstance(child, ast.Set):
                    for value in child.elts:
                        if isinstance(value, ast.Constant) and isinstance(
                            value.value, str
                        ):
                            routes.add(
                                (
                                    "Watch" if "Watch" in node.name else "Library",
                                    value.value,
                                )
                            )
    return [
        {
            "id": f"{screen}/{route}",
            "kind": "source_route",
            "baseline": "route observed in source; item state unverified",
        }
        for screen, route in sorted(routes)
    ]


def inventory(root: Path) -> dict[str, Any]:
    files = [
        scan_qml(str(p.relative_to(root)), p.read_text(encoding="utf-8"))
        for p in sorted((root / "yt_downloader/qt_quick").glob("*.qml"))
    ]
    sites = [s for f in files for s in f["sites"]]
    return {
        "scope": "lexical Qt binding candidates; runtime multiplicity and visibility unverified",
        "counts": {
            "qml_files": len(files),
            "object_candidates": sum(f["object_candidates"] for f in files),
            **dict(Counter(s["kind"] for s in sites)),
        },
        "limits": [
            "dynamic QML/JavaScript controls unenumerated",
            "no visibility or native acceptance inferred",
        ],
        "files": files,
        "route_contexts": _route_contexts(root),
        "sites": sites,
    }


def path_report(discovered: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate evidence-bound transitions and find least-cost witnessed paths.

    Evidence must be collected by a UI observer; a slot invocation alone does not
    prove a visible control. Costs count individual user gestures, including safety.
    """
    sites = {s["site"]: s for s in discovered["sites"] if s["kind"] == "handler"}
    edges = []
    rejected = []
    for edge in evidence.get("edges", []):
        site = sites.get(edge.get("site"))
        reason = None
        if (
            not site
            or site["binding_sha256"] != edge.get("binding_sha256")
            or site["file_sha256"] != edge.get("file_sha256")
        ):
            reason = "missing_or_changed_binding"
        elif edge.get("tier") not in {"headless_ui", "native_ui"}:
            reason = "unobserved_ui"
        elif (
            not edge.get("receipt")
            or edge.get("visible") is not True
            or edge.get("enabled") is not True
        ):
            reason = "missing_visible_enabled_receipt"
        elif not edge.get("steps") or any(s not in _STEPS for s in edge["steps"]):
            reason = "unclassified_steps"
        elif not edge.get("from") or not edge.get("to"):
            reason = "missing_state_context"
        if reason:
            rejected.append({"edge": edge, "reason": reason})
        else:
            edges.append(edge)
    results = []
    for goal in evidence.get("goals", []):
        queue = [(0, goal["from"], [])]
        visited = set()
        result = None
        while queue:
            cost, node, chain = heapq.heappop(queue)
            if node in visited:
                continue
            visited.add(node)
            if node == goal["to"]:
                result = {
                    "steps": cost,
                    "path": chain,
                    "step_types": dict(
                        Counter(s for i in chain for s in edges[i]["steps"])
                    ),
                }
                break
            for i, edge in enumerate(edges):
                if edge["from"] == node:
                    heapq.heappush(
                        queue, (cost + len(edge["steps"]), edge["to"], chain + [i])
                    )
        results.append(
            {
                **goal,
                "status": "unverified"
                if result is None
                else ("ux_review" if result["steps"] > 3 else "reachable"),
                **(result or {}),
                "limit": "shortest among witnessed edges only",
            }
        )
    observed = {edge["site"] for edge in edges}
    return {
        "counts": {
            "handler_candidates": len(sites),
            "observed_handler_sites": len(observed),
            "unresolved_handler_sites": len(sites.keys() - observed),
            "goals": len(results),
            "accepted_edges": len(edges),
            "rejected_edges": len(rejected),
        },
        "unresolved": sorted(sites.keys() - observed),
        "goals": results,
        "rejected": rejected,
        "accepted": edges,
        "limits": [
            "unverified paths are not proven unreachable",
            "receipt content needs independent review",
            "no visual polish, OS picker policy, or all item-state acceptance",
        ],
    }


def reconcile_views(
    authority: list[dict[str, Any]],
    views: dict[str, list[dict[str, Any]]],
    expected: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """Compare independently read projections with canonical attempt identities.

    Each row carries run_id, origin_run_id, retry_of_run_id, state. Membership is
    supplied by the scenario's applicability contract, not inferred from the view.
    """
    canonical = {row["run_id"]: row for row in authority}
    findings = []
    if len(canonical) != len(authority):
        findings.append({"reason": "duplicate_authority_identity"})
    for view, members in expected.items():
        rows = views.get(view, [])
        ids = [row["run_id"] for row in rows]
        if len(set(ids)) != len(ids):
            findings.append({"view": view, "reason": "duplicate_view_identity"})
        if set(ids) != members:
            findings.append(
                {
                    "view": view,
                    "reason": "membership",
                    "missing": sorted(members - set(ids)),
                    "extra": sorted(set(ids) - members),
                }
            )
        for row in rows:
            owner = canonical.get(row["run_id"])
            if owner is None:
                findings.append(
                    {"view": view, "run_id": row["run_id"], "reason": "unknown_target"}
                )
                continue
            for field in ("state", "origin_run_id", "retry_of_run_id"):
                if field not in row or row[field] != owner.get(field):
                    findings.append(
                        {
                            "view": view,
                            "run_id": row["run_id"],
                            "reason": "stale_or_wrong_attempt",
                            "field": field,
                        }
                    )
    return findings


# The two catalogs are extensible declarations. Source discoveries expand them;
# unknown candidate contexts are retained rather than silently treated as screens.
LOCATION_CATALOG = (
    {"id": "Forge", "kind": "screen", "baseline": "idle, no selection"},
    {"id": "Library", "kind": "screen", "baseline": "home, no selection"},
    {"id": "Watch", "kind": "screen", "baseline": "home, no selection"},
    {"id": "Activity", "kind": "screen", "baseline": "current activity"},
)
FEATURE_CATALOG = (
    {
        "id": "find_missing_media",
        "call": "requestMissingFileRelink",
        "screen": "Library",
        "precondition": "selected missing saved item",
    },
    {
        "id": "review_trash_saved_media",
        "call": "startFileAction",
        "aliases": ["startFileActions"],
        "expression_contains": '"delete"',
        "screen": "Library",
        "precondition": "selected saved media with verified file identity",
    },
    {
        "id": "open_saved_output",
        "call": "openLibraryFolder",
        "aliases": ["openSelectedFolderFileLocation"],
        "screen": "Library",
        "precondition": "selected saved output with verified location",
    },
    {
        "id": "remove_saved_entry_review",
        "call": "requestInspectorLibraryRemoval",
        "screen": "Library",
        "precondition": "selected saved item",
    },
    {
        "id": "retry_run",
        "call": "retryTerminal",
        "aliases": ["downloadSelectedIssue"],
        "precondition": "selected terminal run",
    },
    {
        "id": "dismiss_run",
        "call": "dismissTerminal",
        "precondition": "selected terminal run",
    },
    {
        "id": "remove_queued",
        "call": "removeQueued",
        "precondition": "selected queued run",
    },
    {
        "id": "open_location",
        "call": "openInspectorLocation",
        "precondition": "verified selected location",
    },
)
_ACTION_BINDINGS = frozenset(
    {
        "onClicked",
        "onActivated",
        "onTriggered",
        "onAccepted",
        "onRejected",
        "onToggled",
        "onDoubleClicked",
        "onPressed",
        "onReleased",
        "onActionTriggered",
    }
)


def catalogs(found: dict[str, Any]) -> dict[str, Any]:
    locations = list(LOCATION_CATALOG) + found.get("route_contexts", [])
    # Each component is a source context, not proof of an independently reachable
    # screen. Menus/dialogs with no handlers are included via the object inventory.
    for file in found["files"]:
        locations.append(
            {
                "id": file["file"],
                "kind": "component_context",
                "baseline": "item state, selection and visibility unverified",
            }
        )
        for obj in file.get("contexts", []):
            locations.append(
                {
                    "id": obj["id"],
                    "kind": "menu_dialog_context",
                    "baseline": "closed/open state and selection unverified",
                }
            )
    features = []
    enrolled = set()
    for declaration in FEATURE_CATALOG:
        sites = [
            site
            for site in found["sites"]
            if site["kind"] == "handler"
            and any(
                call.rsplit(".", 1)[-1]
                in [declaration["call"], *declaration.get("aliases", [])]
                for call in site["calls"]
            )
            and declaration.get("expression_contains", "") in site["expression"]
        ]
        features.append(
            {
                **declaration,
                "kind": "named_action",
                "sites": [site["site"] for site in sites],
                "primary_entries": sorted({site["file"] for site in sites}),
            }
        )
        enrolled.update(site["site"] for site in sites)
    for site in found["sites"]:
        if site["kind"] == "handler" and site["site"] not in enrolled:
            features.append(
                {
                    "id": site["site"],
                    "sites": [site["site"]],
                    "primary_entries": [site["file"]],
                    "kind": (
                        "input_control_candidate"
                        if site["binding"] in _ACTION_BINDINGS
                        else (
                            "forwarding_candidate"
                            if site["binding"].endswith("Requested")
                            else "unreviewed_event_candidate"
                        )
                    ),
                    "precondition": "source visibility/enabled expressions; runtime applicability unverified",
                }
            )
            enrolled.add(site["site"])
    return {
        "locations": locations,
        "features": features,
        "unregistered_handlers": [
            site["site"]
            for site in found["sites"]
            if site["kind"] == "handler"
            and site["binding"] not in _ACTION_BINDINGS
            and not site["binding"].endswith("Requested")
        ],
        "limits": [
            "component contexts are candidates, not all runtime screen states",
            "event/lifecycle handlers remain unregistered and require review",
            "dynamic controls and item-state space remain unverified",
        ],
    }


# Reviewed source-entry declarations; candidate component containment is not
# runtime visibility. Paths retain those conditions for UX review.
PRIMARY_SCREEN = {
    "RunDeck.qml": "Forge",
    "RunDeckCard.qml": "Forge",
    "ForgeSourceDetails.qml": "Forge",
    "FeaturePreview.qml": "Forge",
    "ManualMp4Settings.qml": "Forge",
    "LibraryScene.qml": "Library",
    "LibraryDetail.qml": "Library",
    "LibraryFolders.qml": "Library",
    "LibraryFolderInspector.qml": "Library",
    "LibraryEmptyPanel.qml": "Library",
    "WatchScene.qml": "Watch",
    "WatchEmptyScene.qml": "Watch",
    "WatchGroupCard.qml": "Watch",
    "ActivityScene.qml": "Activity",
    "ActivityLines.qml": "Activity",
}


def modeled_path(
    location: dict[str, Any], feature: dict[str, Any], found: dict[str, Any]
) -> dict[str, Any]:
    by_site = {site["site"]: site for site in found["sites"]}
    options = []
    for key in feature["sites"]:
        site = by_site[key]
        if site["binding"] not in _ACTION_BINDINGS:
            continue
        primary = PRIMARY_SCREEN.get(Path(site["file"]).name) or feature.get("screen")
        # A component context supports direct actions declared in that component.
        same_context = location["id"] == site["file"]
        start_screen = location["id"].split("/", 1)[0]
        if not same_context and (
            not primary or start_screen not in {"Forge", "Library", "Watch", "Activity"}
        ):
            continue
        steps = []
        if not same_context and start_screen != primary:
            steps.append(
                {
                    "kind": "navigation",
                    "target": primary,
                    "basis": "main navigation screen declaration",
                }
            )
        # Issues recovery is nested under Folders. Preserve both navigation
        # gestures from a home baseline rather than teleporting to the inspector.
        issue_calls = {"downloadSelectedIssue", "requestMissingFileRelink"}
        if (
            not same_context
            and any(call.rsplit(".", 1)[-1] in issue_calls for call in site["calls"])
            and location["id"] != "Library/issues"
        ):
            if location["id"] != "Library/folders":
                steps.append(
                    {
                        "kind": "navigation",
                        "target": "Library/folders",
                        "basis": "LibraryScene folders handler",
                    }
                )
            steps.append(
                {
                    "kind": "navigation",
                    "target": "Library/issues",
                    "basis": "Folders mode declaration",
                }
            )
        # The selected item is a precondition: count selecting it from a baseline
        # without selection. A supplied selection-state location can avoid that step.
        if (
            "selected" in feature["precondition"]
            and "selected" not in location["baseline"]
        ):
            steps.append(
                {
                    "kind": "selection",
                    "target": feature["precondition"],
                    "basis": "action applicability declaration",
                }
            )
        for ancestor in site.get("ancestors", []):
            context_id = f"{site['file']}:{ancestor['line']}:{ancestor['type']}"
            if location["id"] != context_id:
                steps.append(
                    {
                        "kind": "menu",
                        "target": ancestor["id"] or context_id,
                        "basis": "source enclosing popup/dialog; opener needs validation",
                    }
                )
        confirm = site["binding"] == "onAccepted" or any(
            "confirm" in call.lower() for call in site["calls"]
        )
        steps.append(
            {
                "kind": "confirmation" if confirm else "action",
                "target": key,
                "basis": "source input handler",
            }
        )
        options.append(steps)
    if not options:
        return {
            "click_count": None,
            "path": [],
            "status": "unverified",
            "confidence": "unresolved source entry or user gesture",
        }
    steps = min(options, key=len)
    return {
        "click_count": len(steps),
        "path": steps,
        "step_types": dict(Counter(step["kind"] for step in steps)),
        "status": "ux_review" if len(steps) > 3 else "modeled",
        "confidence": "conditional source model; visibility, selection, opener and availability need UI validation",
    }


def matrix_report(found: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    catalog = catalogs(found)
    goals = []
    for location in catalog["locations"]:
        for feature in catalog["features"]:
            goals.append(
                {
                    "from": location["id"],
                    "to": "action:" + feature["id"],
                    "feature": feature["id"],
                    "baseline": location["baseline"],
                    "precondition": feature["precondition"],
                }
            )
    coverage = path_report(found, {**evidence, "goals": goals})
    for result in coverage["goals"]:
        result["click_count"] = result.get("steps")
        result["path"] = [coverage["accepted"][i] for i in result.get("path", [])]
        result["alternatives"] = "keyboard/right-click alternatives unverified"
        location = next(l for l in catalog["locations"] if l["id"] == result["from"])
        feature = next(f for f in catalog["features"] if f["id"] == result["feature"])
        result["modeled"] = modeled_path(location, feature, found)
        result["validated_click_count"] = result["click_count"]
    return {
        "catalogs": catalog,
        "coverage": coverage,
        "matrix_denominator": len(catalog["locations"]) * len(catalog["features"]),
        "exhaustive_catalog_crossproduct": True,
        "feature_kind_counts": dict(
            Counter(f.get("kind", "named_action") for f in catalog["features"])
        ),
        "exhaustive_app_coverage": False,
        "status_counts": dict(Counter(row["status"] for row in coverage["goals"])),
        "modeled_status_counts": dict(
            Counter(row["modeled"]["status"] for row in coverage["goals"])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    found = inventory(args.root)
    evidence = json.loads(args.evidence.read_text()) if args.evidence else {}
    evidence = evidence.get("evidence", evidence)
    report = matrix_report(found, evidence)
    if args.summary:
        print(
            json.dumps(
                {
                    "inventory": found["counts"],
                    "locations": len(report["catalogs"]["locations"]),
                    "features": len(report["catalogs"]["features"]),
                    "feature_kind_counts": report["feature_kind_counts"],
                    "matrix_denominator": report["matrix_denominator"],
                    "status_counts": report["status_counts"],
                    "modeled_status_counts": report["modeled_status_counts"],
                    "coverage": report["coverage"]["counts"],
                    "unregistered_handlers": len(
                        report["catalogs"]["unregistered_handlers"]
                    ),
                    "exhaustive_app_coverage": False,
                },
                indent=2,
            )
        )
    else:
        print(json.dumps({"inventory": found, "coverage": report}, indent=2))


if __name__ == "__main__":
    main()
