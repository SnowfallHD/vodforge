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
    parentheses = []
    paren_ends = {}
    ends = {}
    for i, char in enumerate(masked):
        if char == "(":
            parentheses.append(i)
        elif char == ")" and parentheses:
            paren_ends[parentheses.pop()] = i
        if char == "{":
            stack.append(i)
        elif char == "}" and stack:
            ends[stack.pop()] = i
    objects = []
    for match in _OBJECT.finditer(masked):
        start = masked.find("{", match.start(), match.end())
        end = ends.get(start, len(text))
        objects.append((start, end, match[1]))

    def direct_properties(owner):
        own = list(masked[owner[0] : owner[1]])
        for child in objects:
            if owner[0] < child[0] < child[1] < owner[1]:
                own[child[0] - owner[0] : child[1] - owner[0] + 1] = " " * (
                    child[1] - child[0] + 1
                )
        own_mask = "".join(own)
        result = {}
        for prop in (
            "id",
            "objectName",
            "label",
            "text",
            "placeholderText",
            "readOnly",
            "visible",
            "enabled",
        ):
            match = re.search(r"\b" + prop + r"\s*:", own_mask)
            if match:
                begin = owner[0] + match.end()
                boundaries = [masked.find(token, begin) for token in ("\n", ";", "}")]
                finish = min([i for i in boundaries if i >= begin], default=owner[1])
                result[prop] = text[begin:finish].strip()
        return result

    input_controls = []
    for declaration in objects:
        if declaration[2] not in {
            "TextField",
            "TextArea",
            "TextInput",
            "TextEdit",
            "Slider",
            "SpinBox",
            "ComboBox",
            "CheckBox",
            "RadioButton",
            "Switch",
        }:
            continue
        properties = direct_properties(declaration)
        ancestors = [obj for obj in objects if obj[0] < declaration[0] < obj[1]]
        scopes = [
            direct_properties(ancestor).get("visible", "") for ancestor in ancestors
        ]
        screens = sorted(
            {
                screen
                for scope in scopes
                for screen in re.findall(r'bridge\.selection\s*===\s*"(\w+)"', scope)
            }
        )
        line = text.count("\n", 0, declaration[0]) + 1
        input_controls.append(
            {
                "site": f"{path}:{line}:control",
                "kind": "input_control",
                "binding": "focus",
                "file": path,
                "line": line,
                "owner_line": line,
                "owner_type": declaration[2],
                "properties": properties,
                "expression": text[declaration[0] : declaration[1] + 1],
                "calls": [],
                "screens": screens,
                "scope_predicates": scopes,
                "binding_sha256": hashlib.sha256(
                    text[declaration[0] : declaration[1] + 1].encode()
                ).hexdigest(),
                "file_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "ancestors": [
                    {
                        "type": ancestor[2],
                        "line": text.count("\n", 0, ancestor[0]) + 1,
                        "id": direct_properties(ancestor).get("id", ""),
                    }
                    for ancestor in ancestors
                    if any(
                        word in ancestor[2]
                        for word in ("Popup", "Dialog", "Menu", "Window")
                    )
                ],
            }
        )
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
            for prop in (
                "id",
                "objectName",
                "visible",
                "enabled",
                "label",
                "text",
                "accessibilityLabel",
                "acceptedButtons",
                "interactive",
                "action",
            ):
                found = re.search(r"\b" + prop + r"\s*:", own_mask)
                if found:
                    begin = owner[0] + found.end()
                    boundaries = [
                        masked.find(token, begin) for token in ("\n", ";", "}")
                    ]
                    finish = min(
                        [i for i in boundaries if i >= begin], default=owner[1]
                    )
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
            if (
                kind == "handler"
                and block_start == begin
                and masked[begin : begin + 1] != "{"
            ):
                end = max(
                    [
                        end,
                        *[
                            finish + 1
                            for start, finish in paren_ends.items()
                            if begin <= start <= end
                        ],
                    ]
                )
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
                    "owner_line": text.count("\n", 0, owner[0]) + 1,
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
        "root_type": objects[0][2] if objects else "unknown",
        "object_declarations": [
            {
                "id": f"{path}:{text.count(chr(10), 0, start) + 1}:{kind}",
                "type": kind,
                "qml_id": (
                    re.search(r"\bid\s*:\s*(\w+)", masked[start:end]).group(1)
                    if re.search(r"\bid\s*:\s*(\w+)", masked[start:end])
                    else ""
                ),
                "root_definition": start == min(o[0] for o in objects),
            }
            for start, end, kind in objects
        ],
        "contexts": [
            {
                "id": f"{path}:{text.count(chr(10), 0, start) + 1}:{kind}",
                "type": kind,
                "qml_id": (
                    re.search(r"\bid\s*:\s*(\w+)", masked[start:end]).group(1)
                    if re.search(r"\bid\s*:\s*(\w+)", masked[start:end])
                    else ""
                ),
                "root_definition": start == min(o[0] for o in objects),
            }
            for start, end, kind in objects
            if any(word in kind for word in ("Popup", "Dialog", "Menu", "Window"))
        ],
        "unbalanced_braces": len(stack),
        "sites": sites,
        "input_controls": input_controls,
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


def _state_contracts(root: Path) -> list[dict[str, Any]]:
    path = root / "yt_downloader/qt_quick/main.py"
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    result = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "terminal_status"
            ):
                for comparison in node.comparators:
                    if isinstance(comparison, ast.Set) and all(
                        isinstance(v, ast.Constant) and isinstance(v.value, str)
                        for v in comparison.elts
                    ):
                        result.append(
                            {
                                "function": function.name,
                                "field": ast.unparse(node.left),
                                "states": sorted(v.value for v in comparison.elts),
                                "predicate": ast.unparse(node),
                                "source": f"yt_downloader/qt_quick/main.py:{node.lineno}",
                                "source_sha256": hashlib.sha256(
                                    source.encode()
                                ).hexdigest(),
                            }
                        )
    return result


def inventory(root: Path) -> dict[str, Any]:
    files = [
        scan_qml(p.relative_to(root).as_posix(), p.read_text(encoding="utf-8"))
        for p in sorted((root / "yt_downloader/qt_quick").glob("*.qml"))
    ]
    inherited = {Path(file["file"]).stem: file["root_type"] for file in files}
    context_types = {"Popup", "Dialog", "Menu", "Window", "ApplicationWindow"}
    changed = True
    while changed:
        expanded = context_types | {
            name for name, base in inherited.items() if base in context_types
        }
        changed = expanded != context_types
        context_types = expanded
    for file in files:
        known = {context["id"] for context in file["contexts"]}
        for declaration in file["object_declarations"]:
            if declaration["type"] in context_types and declaration["id"] not in known:
                file["contexts"].append(
                    {
                        **declaration,
                        "inheritance_basis": inherited.get(
                            declaration["type"], declaration["type"]
                        ),
                    }
                )
    sites = [s for f in files for s in f["sites"]] + [
        control for file in files for control in file.get("input_controls", [])
    ]
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
        "state_contracts": _state_contracts(root),
        "sites": sites,
    }


def runtime_controls(root_object: Any, discovered: dict[str, Any]) -> dict[str, Any]:
    """Read and classify supplied Qt instances; retain auditable exclusion rows."""
    from PySide6.QtCore import QMetaMethod, QObject

    input_signals = {
        "activated",
        "clicked",
        "triggered",
        "accepted",
        "pressed",
        "toggled",
    }
    patterns = []
    for site in discovered["sites"]:
        expression = site["properties"].get("objectName", "")
        literals = re.findall(r'"([^"\\]*)"', expression)
        for literal in literals:
            pattern = re.escape(literal)
            if literal.endswith("_") and any(
                word in expression for word in ("index", "slotIndex")
            ):
                pattern += r"[0-9]+"
            patterns.append((pattern, site["site"]))
    nodes = [root_object, *root_object.findChildren(QObject)]
    index = {id(node): i for i, node in enumerate(nodes)}
    widgets = (
        "StoneButton",
        "StoneField",
        "StoneCheckBox",
        "CopyButton",
        "TextField",
        "TextArea",
        "Slider",
        "ComboBox",
        "SpinBox",
        "InlineSelector",
    )
    controls = []
    for node in nodes:
        meta = node.metaObject()
        signals = {
            bytes(meta.method(i).name()).decode()
            for i in range(meta.methodCount())
            if meta.method(i).methodType() == QMetaMethod.Signal
        } & input_signals
        if not signals:
            continue
        qt_type = meta.className()
        name = node.objectName()
        source_sites = sorted(
            {site for pattern, site in patterns if name and re.fullmatch(pattern, name)}
        )
        parent = node.parent()
        owner = None
        context = None
        while parent is not None:
            parent_type = parent.metaObject().className()
            if owner is None and any(parent_type.startswith(kind) for kind in widgets):
                owner = parent
            if context is None and any(
                word in parent_type for word in ("Popup", "Dialog")
            ):
                context = index.get(id(parent))
            parent = parent.parent()
        reason = None
        classification = "user_control_candidate"
        if qt_type == "QQmlTimer":
            reason = "timer trigger is a lifecycle event, not user input"
        elif qt_type.startswith("QQuickKeysAttached"):
            reason = "keyboard attachment is an alternative input adapter, not another click control"
        elif qt_type.endswith("DialogOptions"):
            reason = "nonvisual native-dialog configuration object, not a rendered input control"
        elif qt_type.startswith(("QQuickOverlayAttached", "QQuickOverlay")):
            reason = "Qt popup-overlay infrastructure; outside-click dismissal remains an alternative"
        elif (
            qt_type.startswith("QQuickMouseArea")
            and owner is not None
            and not name
            and not source_sites
            and not (
                getattr(
                    node.property("acceptedButtons"),
                    "value",
                    node.property("acceptedButtons"),
                )
                or 0
            )
            & 2
        ):
            reason = "unnamed left-button pointer adapter inside a shared input widget; retain its owning widget once"
        elif (
            qt_type.startswith(("StoneField", "StoneButton"))
            and node.property("interactive") is False
        ):
            reason = "this instance explicitly declares interactive=false; retain source for other states"
        if reason:
            classification = "implementation_or_nonuser_instance"
        label = (
            node.property("accessibilityLabel")
            or node.property("label")
            or node.property("placeholderText")
            or ""
        )
        controls.append(
            {
                "instance_id": index[id(node)],
                "object_name": name,
                "qt_type": qt_type,
                "label": str(label),
                "signals": sorted(signals),
                "visible": node.property("visible"),
                "enabled": node.property("enabled"),
                "source_sites": source_sites,
                "classification": classification,
                "exclusion_reason": reason,
                "owning_widget_instance": index.get(id(owner))
                if owner is not None
                else None,
                "context_instance": context,
                "accepted_buttons": getattr(
                    node.property("acceptedButtons"),
                    "value",
                    node.property("acceptedButtons"),
                ),
                "status": "source_name_match"
                if source_sites
                else "unmapped_runtime_candidate",
            }
        )
    # Repeated widgets are grouped only as action families. Each instance and its
    # context stay in the report; no delegate entity is silently excluded.
    families = {}
    for control in controls:
        if control["exclusion_reason"]:
            continue
        base_type = re.sub(r"_QML(?:TYPE)?_[0-9]+.*", "", control["qt_type"])
        key = (
            base_type,
            control["label"],
            tuple(control["source_sites"]),
            control["context_instance"],
        )
        families.setdefault(key, []).append(control["instance_id"])
    user = [c for c in controls if not c["exclusion_reason"]]
    return {
        "controls": controls,
        "action_families": [
            {
                "qt_type": key[0],
                "label": key[1],
                "source_sites": list(key[2]),
                "context_instance": key[3],
                "instances": values,
                "limit": "same action family does not prove equal delegate targets",
            }
            for key, values in families.items()
        ],
        "counts": {
            "interactive_candidates": len(controls),
            "user_control_instances": len(user),
            "action_families": len(families),
            "audited_nonuser_or_adapter_instances": len(controls) - len(user),
            "named_source_matches": sum(bool(c["source_sites"]) for c in controls),
            "unmapped_runtime_candidates": sum(not c["source_sites"] for c in controls),
            "unmapped_user_control_instances": sum(not c["source_sites"] for c in user),
        },
        "exclusion_counts": dict(
            Counter(c["exclusion_reason"] for c in controls if c["exclusion_reason"])
        ),
        "limits": [
            "classification applies to this supplied scene and actual instance properties",
            "all exclusion reasons and delegate instances remain readable",
            "name matching is not binding or effective availability proof",
            "other states and native dialogs remain unobserved",
        ],
    }


def path_report(discovered: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate evidence-bound transitions and find least-cost witnessed paths.

    Evidence must be collected by a UI observer; a slot invocation alone does not
    prove a visible control. Costs count individual user gestures, including safety.
    """
    sites = {
        s["site"]: s
        for s in discovered["sites"]
        if s["kind"] in {"handler", "input_control"}
    }
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
        "id": "choose_output_folder",
        "call": "outputFolderDialog.open",
        "aliases": ["openOutputFolderDialog"],
        "screen": "Forge",
        "precondition": "configured output folder; path supplied by context",
    },
    {
        "id": "submit_source",
        "call": "submit",
        "screen": "Forge",
        "precondition": "URL field value and idle/active state supplied by context",
    },
    {
        "id": "show_settings",
        "call": "settingsPopup.toggleFrom",
        "screen": "global",
        "precondition": "main navigation available",
    },
    {
        "id": "find_missing_media",
        "call": "requestMissingFileRelink",
        "aliases": ["relinkFileDialog.open"],
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
                (
                    call in [declaration["call"], *declaration.get("aliases", [])]
                    or call.rsplit(".", 1)[-1]
                    in [declaration["call"], *declaration.get("aliases", [])]
                )
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
        if site["binding"] not in _ACTION_BINDINGS and site["kind"] != "input_control":
            continue
        primary = PRIMARY_SCREEN.get(Path(site["file"]).name) or feature.get("screen")
        # A component context supports direct actions declared in that component.
        inside_context = next(
            (
                i
                for i, a in enumerate(site.get("ancestors", []))
                if location["id"] == f"{site['file']}:{a['line']}:{a['type']}"
            ),
            None,
        )
        same_context = location["id"] == site["file"] or inside_context is not None
        if (
            feature["id"] == "find_missing_media"
            and Path(site["file"]).name == "Main.qml"
            and inside_context is None
            and not any(
                a["id"] == "libraryItemPopup" for a in site.get("ancestors", [])
            )
        ):
            # Direct recovery controls exist in both popups, but the asynchronous
            # review/playback opener chain is not yet modeled from each screen.
            continue
        start_screen = location["id"].split("/", 1)[0]
        if feature.get("screens"):
            primary = (
                start_screen
                if start_screen in feature["screens"]
                else feature["screens"][0]
            )
        if feature.get("screen") == "global" or any(
            a["id"] == "settingsPopup" for a in site.get("ancestors", [])
        ):
            primary = (
                start_screen
                if start_screen in {"Forge", "Library", "Watch", "Activity"}
                else primary
            )
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
        # Inspector controls require the actual Folders route; Issues is another
        # navigation gesture. Selecting an item never teleports from Library home.
        inspector_entry = Path(site["file"]).name == "LibraryFolderInspector.qml"
        in_folders = location["id"] in {"Library/folders", "Library/issues"}
        if not same_context and inspector_entry and not in_folders:
            steps.append(
                {
                    "kind": "navigation",
                    "target": "Library/folders",
                    "basis": "LibraryScene My Files source handler",
                }
            )
        issue_calls = {"downloadSelectedIssue", "requestMissingFileRelink"}
        if inspector_entry and feature["id"] == "dismiss_run":
            issue_calls.add("dismissTerminal")
        if (
            not same_context
            and any(call.rsplit(".", 1)[-1] in issue_calls for call in site["calls"])
            and location["id"] != "Library/issues"
        ):
            steps.append(
                {
                    "kind": "navigation",
                    "target": "Library/issues",
                    "basis": "Folders Issues source mode declaration",
                }
            )
        # The selected item is a precondition: count selecting it from a baseline
        # without selection. A supplied selection-state location can avoid that step.
        if (
            "selected" in feature["precondition"]
            and "selected" not in location["baseline"]
            and inside_context is None
        ):
            steps.append(
                {
                    "kind": "selection",
                    "target": feature["precondition"],
                    "basis": "action applicability declaration",
                }
            )
        for i, ancestor in enumerate(site.get("ancestors", [])):
            if inside_context is not None and i <= inside_context:
                continue
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


def _words(value: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("_", " ").strip()


def _user_site_class(site: dict[str, Any]) -> tuple[str, str]:
    if site["kind"] == "input_control":
        return (
            "declared_input_control",
            "editable/selectable widget declaration; callbacks are not additional controls",
        )
    if site["kind"] == "signal":
        return (
            "signal_declaration",
            "declaration forwards intent; it is not an additional visible control",
        )
    if site["owner_type"] == "Timer":
        return "lifecycle", "Timer handlers are scheduled lifecycle callbacks"
    if site["binding"] in {
        "onPressAction",
        "onReturnPressed",
        "onSpacePressed",
        "onEscapePressed",
    }:
        return (
            "alternative_input",
            "accessibility or keyboard entry to a control; not an additional click",
        )
    if Path(site["file"]).stem in {"StoneButton", "StoneField", "StoneCheckBox"}:
        return (
            "renderer_adapter",
            "shared control implementation forwards input to its instance signal",
        )
    if site["binding"] in _ACTION_BINDINGS:
        return (
            "user_input",
            "direct source input handler; actual availability still needs state/UI evidence",
        )
    if site["binding"].endswith("Requested") or site["binding"] in {
        "onChosen",
        "onTrackRequested",
    }:
        return (
            "forwarding",
            "component signal consumer; source linkage must be reviewed separately",
        )
    return (
        "state_listener_unreviewed",
        "property/lifecycle callback is not a separately declared user input; emitter classification remains open",
    )


def _command_key(site: dict[str, Any]) -> tuple[str, str, bool]:
    """Group equivalent production commands while retaining parameterized entries."""
    calls = [
        call
        for call in site["calls"]
        if re.search(r"(?:^bridge\.|\.appBridge\.|^appBridge\.)", call)
    ]
    # Menu closes and feedback timers must not split the same durable operation.
    if not calls:
        calls = [
            call
            for call in site["calls"]
            if call not in {"if", "function"}
            and not call.startswith(("Math.", "Qt.", "Object.", "String."))
            and not call.endswith((".restart", ".indexOf", ".resolveLibrarySelection"))
        ]
    label = (
        site["properties"].get("accessibilityLabel")
        or site["properties"].get("label")
        or ""
    )
    if calls:
        keys = []
        for call in calls:
            match = re.search(re.escape(call) + r"\s*\(([^\n]*)", site["expression"])
            arguments = match[1].split(")", 1)[0] if match else ""
            # Literals distinguish e.g. Show channels vs Show playlists and
            # opt-in vs opt-out. Dynamic model values are explicitly parameterized.
            literals = re.findall(r'"([^"\\]*)"|\b(true|false)\b', arguments)
            qualifiers = [a or b for a, b in literals]
            production = bool(
                re.search(r"(?:^bridge\.|\.appBridge\.|^appBridge\.)", call)
            )
            key = (
                ("command:" + call.rsplit(".", 1)[-1])
                if production
                else ("ui:" + Path(site["file"]).stem + ":" + call)
            )
            keys.append(key + (":" + "|".join(qualifiers) if qualifiers else ""))
        key = "+".join(sorted(set(keys)))
        title = _words(calls[0].rsplit(".", 1)[-1])
        literal_label = re.fullmatch(r'"([^"\\]*)"', label)
        return (
            key,
            literal_label[1] if literal_label and literal_label[1] else title,
            True,
        )
    assignment = re.search(
        r"\b([A-Za-z_]\w*(?:\.\w+)+)\s*(?:=|\+=|-=)\s*([^;\n}]+)", site["expression"]
    )
    if assignment:
        value = assignment[2].strip()
        literal = re.fullmatch(r'"([^"\\]*)"|true|false', value)
        target = assignment[1]
        key = f"ui:{Path(site['file']).stem}:{target}" + (
            ":" + value if literal else ""
        )
        return (
            key,
            _words(target.rsplit(".", 1)[-1]) + (" " + value if literal else ""),
            not bool(literal),
        )
    return "unresolved:" + site["site"], label or _words(site["binding"][2:]), True


def _resolved_command_site(
    site: dict[str, Any], sites: list[dict[str, Any]]
) -> dict[str, Any]:
    for call in site["calls"]:
        parts = call.split(".")
        if len(parts) != 2:
            continue
        owner, signal = parts
        if not any(
            other["kind"] == "signal"
            and other["file"] == site["file"]
            and other["binding"] == signal
            and other["properties"].get("id") == owner
            for other in sites
        ):
            continue
        binding = "on" + signal[0].upper() + signal[1:]
        consumers = [
            other
            for other in sites
            if other["kind"] == "handler"
            and other["file"] == site["file"]
            and other["binding"] == binding
            and other["properties"].get("id") == owner
        ]
        if len(consumers) == 1 and consumers[0]["site"] != site["site"]:
            return consumers[0]
    return site


def semantic_catalogs(found: dict[str, Any]) -> dict[str, Any]:
    """Actual named contexts and command families, alongside retained discovery gaps."""
    candidates = catalogs(found)
    by_site = {site["site"]: site for site in found["sites"]}
    classifications = [
        {
            "site": site["site"],
            "class": _user_site_class(site)[0],
            "reason": _user_site_class(site)[1],
        }
        for site in found["sites"]
    ]
    semantic = {}
    enrolled = set()
    for declaration in candidates["features"]:
        if declaration["kind"] != "named_action":
            continue
        entries = [
            key
            for key in declaration["sites"]
            if _user_site_class(by_site[key])[0] == "user_input"
        ]
        semantic[declaration["id"]] = {
            **declaration,
            "sites": entries,
            "label": _words(declaration["id"]),
            "kind": "semantic_operation",
            "parameterized": True,
        }
        enrolled.update(entries)
    for site in found["sites"]:
        classification, _reason = _user_site_class(site)
        if classification != "user_input" or site["site"] in enrolled:
            continue
        resolved = _resolved_command_site(site, found["sites"])
        key, label, parameterized = _command_key(resolved)
        feature = semantic.setdefault(
            key,
            {
                "id": key,
                "label": label,
                "kind": "semantic_command_family",
                "sites": [],
                "primary_entries": [],
                "parameterized": parameterized,
                "precondition": "source predicates and item/parameter values must hold",
            },
        )
        feature["sites"].append(site["site"])
        feature["primary_entries"] = sorted(
            set(feature["primary_entries"]) | {site["file"]}
        )
        enrolled.add(site["site"])
    for control in found["sites"]:
        if control["kind"] != "input_control":
            continue
        props = control["properties"]
        name = (
            props.get("objectName", "").strip('"')
            or props.get("id")
            or str(control["line"])
        )
        label = props.get("placeholderText", "").strip('"') or _words(name)
        key = f"control:{Path(control['file']).stem}:{name}"
        callbacks = [
            site
            for site in found["sites"]
            if site["file"] == control["file"]
            and site.get("owner_line") == control["owner_line"]
            and site["kind"] == "handler"
        ]
        semantic[key] = {
            "id": key,
            "label": ("View " if props.get("readOnly") == "true" else "Edit/select ")
            + label,
            "kind": "semantic_input_control",
            "sites": [control["site"]],
            "primary_entries": [control["file"]],
            "parameterized": True,
            "screens": control.get("screens", []),
            "precondition": "control visible and enabled; draft/choice value and target context required",
            "input_callbacks": [site["site"] for site in callbacks],
            "non_click_steps": "typing, keyboard acceptance or drag may be required; focus does not certify the effect",
        }
    # Contexts are actual route/menu/dialog declarations, not each reusable renderer.
    locations = list(LOCATION_CATALOG) + found.get("route_contexts", [])
    context_exclusions = []
    for file in found["files"]:
        for context in file.get("contexts", []):
            if context.get("root_definition") and Path(file["file"]).name != "Main.qml":
                context_exclusions.append(
                    {
                        "context": context["id"],
                        "reason": "root definition of a reusable component; consumer instances establish locations",
                    }
                )
                continue
            qml_id = context.get("qml_id")
            locations.append(
                {
                    "id": context["id"],
                    "label": _words(qml_id or context["type"]),
                    "kind": "declared_menu_dialog",
                    "source": context["id"],
                    "baseline": "open context; target item and parameters unverified",
                }
            )
    locations.append(
        {
            "id": "Forge/idle",
            "base_location": "Forge",
            "kind": "baseline_state",
            "baseline": "idle composer, URL empty, configured output directory, no selected item",
        }
    )
    # Named target-state contexts are bounded contracts, not every runtime interleaving.
    # Their proof is the terminal/queued/active source guard, which remains in entries.
    terminal_states = sorted(
        {
            state
            for contract in found.get("state_contracts", [])
            if contract["function"] == "downloadSelectedIssue"
            for state in contract["states"]
        }
    )
    kinds = sorted(
        {
            state
            for site in found["sites"]
            for state in ("active", "queued")
            if re.search(
                r"kind\s*===\s*[\"\']" + state, " ".join(site["properties"].values())
            )
        }
    )
    states = kinds + terminal_states
    for base in ["Forge", "Library/issues"]:
        for state in states:
            locations.append(
                {
                    "id": base + "/selected-run:" + state,
                    "base_location": base,
                    "kind": "selected_item_state",
                    "item_state": state,
                    "baseline": "selected run " + state,
                    "state_contract": "run state; same selected owner preserved",
                    "source_state_proofs": found.get("state_contracts", []),
                }
            )
    features = list(semantic.values())
    for feature in features:
        feature["entries"] = [
            {
                "site": key,
                "source_predicates": by_site[key]["properties"],
                "source_calls": by_site[key]["calls"],
                "parameter_context": by_site[key]["expression"],
            }
            for key in feature["sites"]
        ]
    return {
        "locations": locations,
        "features": features,
        "source_classifications": classifications,
        "classification_counts": dict(Counter(row["class"] for row in classifications)),
        "context_exclusions": context_exclusions,
        "unresolved_user_inputs": [
            key for key in semantic if key.startswith("unresolved:")
        ],
        "limits": [
            "command families retain parameter and target variants; they are not unique rendered control instances",
            "new input handlers and actual contexts automatically expand this catalog",
            "selected-run states are bounded; saved-file/provider/player/form state catalog remains incomplete",
            "forwarding, keyboard alternatives and state listeners remain independently enumerated",
        ],
    }


def semantic_report(found: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    catalog = semantic_catalogs(found)
    by_site = {site["site"]: site for site in found["sites"]}
    rows = []
    for location in catalog["locations"]:
        for feature in catalog["features"]:
            context = {**location, "id": location.get("base_location", location["id"])}
            modeled = modeled_path(context, feature, found)
            state = location.get("item_state")
            # Restrict applicability only for directly source-guarded named actions.
            applicable_states = {
                "retry_run": {"Failed", "Stopped", "Skipped"},
                "dismiss_run": {"Failed", "Stopped", "Skipped"},
                "remove_queued": {"queued"},
            }
            if (
                state
                and feature["id"] in applicable_states
                and feature["sites"]
                and found.get("state_contracts")
                and any(
                    re.search(
                        r"kind\s*===\s*[\"\'](?:terminal|queued)",
                        by_site[key]["properties"].get("visible", ""),
                    )
                    for key in feature["sites"]
                )
                and state not in applicable_states[feature["id"]]
            ):
                modeled = {
                    "click_count": None,
                    "path": [],
                    "status": "not_applicable",
                    "confidence": "declared selected-run state contract; no target substitution",
                    "reason": "action requires a different run state",
                    "source_predicates": [
                        by_site[key]["properties"].get("visible", "")
                        for key in feature["sites"]
                    ],
                }
            goal = {"from": location["id"], "to": "action:" + feature["id"]}
            observed_edges = []
            for edge in evidence.get("edges", []):
                if edge.get("to") in ["action:" + key for key in feature["sites"]]:
                    observed_edges.append({**edge, "to": goal["to"]})
                else:
                    observed_edges.append(edge)
            validated_report = path_report(
                found, {"edges": observed_edges, "goals": [goal]}
            )
            validated = validated_report["goals"][0]
            rows.append(
                {
                    "location": location["id"],
                    "feature": feature["id"],
                    "label": feature["label"],
                    "baseline": location["baseline"],
                    "modeled": modeled,
                    "validated_click_count": validated.get("steps"),
                    "validated_status": validated["status"],
                    "validated_path": [
                        validated_report["accepted"][i]
                        for i in validated.get("path", [])
                    ],
                    "alternatives": "keyboard/right-click adapters separately enumerated; costs unverified",
                }
            )
    return {
        "catalogs": catalog,
        "rows": rows,
        "matrix_denominator": len(rows),
        "modeled_status_counts": dict(
            Counter(row["modeled"]["status"] for row in rows)
        ),
        "validated_status_counts": dict(
            Counter(row["validated_status"] for row in rows)
        ),
        "source_enumeration_complete": False,
        "runtime_state_enumeration_complete": False,
    }


def native_history(path: Path) -> dict[str, Any]:
    """Verify owner-provided bounded receipts; preserve their original revision."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    manifest = payload.get("artifacts_sha256", {})
    for name, expected_hash in manifest.items():
        artifact = path.parent / name
        if (
            Path(name).name != name
            or not artifact.is_file()
            or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_hash
        ):
            failures.append({"artifact": name, "reason": "missing_or_changed_artifact"})
    required = {"owner.json", "ready.json", "finished.json"}
    if not required <= manifest.keys():
        failures.append({"reason": "missing_owner_ready_finish_bindings"})
    if failures:
        return {"accepted": [], "rejected": failures, "receipt": str(path)}
    owner = json.loads((path.parent / "owner.json").read_text())
    ready = json.loads((path.parent / "ready.json").read_text())
    finish = json.loads((path.parent / "finished.json").read_text())
    if not (
        isinstance(payload.get("source_commit"), str)
        and bool(payload["source_commit"].strip())
        and owner.get("source_commit") == payload.get("source_commit")
        and owner.get("pid") == payload.get("actual_pid") == ready.get("pid")
        and ready.get("window_id") == payload.get("native_window")
        and ready.get("visible") is True
        and finish.get("exit_code") == payload.get("normal_exit") == 0
        and finish.get("owned_process_still_running") is False
        and payload.get("survivor") is False
    ):
        return {
            "accepted": [],
            "rejected": [{"reason": "owner_window_revision_exit_mismatch"}],
            "receipt": str(path),
        }
    operations = {
        "output-folder-picker": "choose_output_folder",
        "Settings output-folder-picker": "choose_output_folder",
        "empty-URL Download feedback": "submit_source",
    }
    accepted = []
    rejected = []
    for observation in payload.get("observations", []):
        feature = operations.get(observation.get("action"))
        sequence = observation.get("sequence", [])
        if (
            not feature
            or not sequence
            or len(sequence) != observation.get("clicks")
            or not str(observation.get("result", "")).startswith("PASS")
        ):
            rejected.append(
                {
                    "observation": observation,
                    "reason": "unsupported_or_inconsistent_bounded_observation",
                }
            )
            continue
        accepted.append(
            {
                "location": observation["location"],
                "feature": feature,
                "source_commit": payload["source_commit"],
                "platform": payload.get("platform"),
                "click_count": observation["clicks"],
                "path": sequence,
                "result": observation["result"],
                "scope": payload.get("scope"),
                "receipt": str(path),
                "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "artifact_hashes_verified": len(manifest),
                "actual_pid": payload["actual_pid"],
                "native_window": payload["native_window"],
                "limits": observation.get("limits", ""),
            }
        )
    return {
        "accepted": accepted,
        "rejected": rejected,
        "receipt": str(path),
        "limits": payload.get("unproven", []),
        "successor_acceptance": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--native-observations", type=Path)
    args = parser.parse_args()
    found = inventory(args.root)
    evidence = json.loads(args.evidence.read_text()) if args.evidence else {}
    evidence = evidence.get("evidence", evidence)
    report = matrix_report(found, evidence)
    semantic = semantic_report(found, evidence)
    historical = (
        native_history(args.native_observations)
        if args.native_observations
        else {"accepted": [], "rejected": []}
    )
    for row in semantic["rows"]:
        row["historical_native_observations"] = [
            obs
            for obs in historical["accepted"]
            if obs["location"] == row["location"] and obs["feature"] == row["feature"]
        ]
    semantic["historical_native_journeys"] = len(historical["accepted"])
    semantic["historical_native_pairs"] = sum(
        bool(row["historical_native_observations"]) for row in semantic["rows"]
    )
    if args.summary:
        print(
            json.dumps(
                {
                    "inventory": found["counts"],
                    "locations": len(report["catalogs"]["locations"]),
                    "features": len(report["catalogs"]["features"]),
                    "semantic_locations": len(semantic["catalogs"]["locations"]),
                    "semantic_features": len(semantic["catalogs"]["features"]),
                    "semantic_pairs": semantic["matrix_denominator"],
                    "historical_native_journeys": semantic[
                        "historical_native_journeys"
                    ],
                    "historical_native_pairs": semantic["historical_native_pairs"],
                    "native_receipt_rejections": historical["rejected"],
                    "semantic_modeled_status_counts": semantic["modeled_status_counts"],
                    "semantic_validated_status_counts": semantic[
                        "validated_status_counts"
                    ],
                    "source_classifications": semantic["catalogs"][
                        "classification_counts"
                    ],
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
        print(
            json.dumps(
                {
                    "schema_version": 2,
                    "inventory": found,
                    "candidate_coverage": report,
                    "semantic_coverage": semantic,
                    "historical_native_receipts": historical,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
