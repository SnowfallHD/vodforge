"""Bounded workflow discovery and independent state reconciliation, no native input."""

import copy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engineering-quality"))
from quality_harness.workflow_coverage import (
    inventory,
    path_report,
    reconcile_views,
    scan_qml,
)


def test_lexical_inventory_ignores_decoys_and_preserves_unknowns():
    found = scan_qml(
        "Scene.qml",
        """Item {
        // onClicked: pretend()
        property string bait: "onClicked: fake() { }"
        StoneButton {
            objectName: "real"
            visible: state.ready
            onActivated: { bridge.remove(owner); popup.close() }
        }
        signal routeRequested(string owner)
        onMysteryChanged: refresh()
    }""",
    )
    assert {s["binding"] for s in found["sites"]} == {
        "onActivated",
        "routeRequested",
        "onMysteryChanged",
    }
    site = next(s for s in found["sites"] if s["binding"] == "onActivated")
    assert site["owner_type"] == "StoneButton"
    assert site["properties"]["objectName"] == '"real"'
    assert site["calls"] == ["bridge.remove", "popup.close"]
    assert found["unbalanced_braces"] == 0


def example():
    discovered = {
        "sites": scan_qml(
            "Scene.qml", "StoneButton {\n onActivated: bridge.retry(owner)\n}"
        )["sites"]
    }
    site = discovered["sites"][0]
    edge = {
        "site": site["site"],
        "binding_sha256": site["binding_sha256"],
        "file_sha256": site["file_sha256"],
        "tier": "headless_ui",
        "receipt": "fixture-observation",
        "visible": True,
        "enabled": True,
        "from": "failed/deck",
        "to": "queued/issues",
        "steps": ["menu", "action"],
    }
    return discovered, {
        "edges": [edge],
        "goals": [{"from": "failed/deck", "to": "queued/issues"}],
    }


@pytest.mark.parametrize(
    "fault",
    [
        "removed",
        "changed",
        "file_changed",
        "invisible",
        "disabled",
        "source_only",
        "receipt",
        "steps",
    ],
)
def test_observation_faults_do_not_certify_reachability(fault):
    discovered, evidence = example()
    if fault == "removed":
        discovered["sites"] = []
    elif fault == "changed":
        evidence["edges"][0]["binding_sha256"] = "stale"
    elif fault == "file_changed":
        evidence["edges"][0]["file_sha256"] = "stale"
    elif fault in {"invisible", "disabled"}:
        evidence["edges"][0][{"invisible": "visible", "disabled": "enabled"}[fault]] = (
            False
        )
    elif fault == "source_only":
        evidence["edges"][0]["tier"] = "source"
    elif fault == "receipt":
        evidence["edges"][0]["receipt"] = ""
    else:
        evidence["edges"][0]["steps"] = ["magic"]
    report = path_report(discovered, evidence)
    assert report["counts"]["rejected_edges"] == 1
    assert report["goals"][0]["status"] == "unverified"


def test_costs_keep_safety_and_find_shortest_witnessed_path():
    discovered, evidence = example()
    edge = evidence["edges"][0]
    edge["steps"] = ["navigation", "menu", "selection", "action", "confirmation"]
    assert path_report(discovered, evidence)["goals"][0]["steps"] == 5
    assert path_report(discovered, evidence)["goals"][0]["status"] == "ux_review"
    evidence["edges"].append({**edge, "steps": ["menu", "action", "confirmation"]})
    goal = path_report(discovered, evidence)["goals"][0]
    assert goal["steps"] == 3
    assert goal["step_types"]["confirmation"] == 1


@pytest.mark.parametrize(
    "fault",
    ["stale_state", "wrong_target", "wrong_attempt", "duplicate", "missing_view"],
)
def test_cross_view_negative_controls(fault):
    authority = [
        {
            "run_id": "retry",
            "origin_run_id": "original",
            "retry_of_run_id": "original",
            "state": "Queued",
        }
    ]
    views = {"deck": copy.deepcopy(authority), "issues": copy.deepcopy(authority)}
    expected = {"deck": {"retry"}, "issues": {"retry"}}
    assert not reconcile_views(authority, views, expected)
    if fault == "stale_state":
        views["issues"][0]["state"] = "Failed"
    elif fault == "wrong_target":
        views["issues"][0]["run_id"] = "other"
    elif fault == "wrong_attempt":
        views["issues"][0]["retry_of_run_id"] = "other"
    elif fault == "duplicate":
        views["issues"].append(views["issues"][0])
    else:
        del views["issues"]
    assert reconcile_views(authority, views, expected)


def test_source_discovery_finds_product_actions_and_flags_unmapped():
    found = inventory(ROOT)
    assert found["counts"]["qml_files"] == len(
        list((ROOT / "yt_downloader/qt_quick").glob("*.qml"))
    )
    dismiss = [
        s for s in found["sites"] if "deck.appBridge.dismissTerminal" in s["calls"]
    ]
    assert len(dismiss) == 1
    assert dismiss[0]["properties"]["objectName"] == '"dismissTerminalRun"'
    empty = path_report(found, {})
    assert empty["counts"]["observed_handler_sites"] == 0
    assert empty["counts"]["unresolved_handler_sites"] == (
        found["counts"]["handler"] + found["counts"]["input_control"]
    )


def test_real_runtime_retry_views_and_durable_outcome(tmp_path, monkeypatch):
    # Run Deck -> Issues -> queue removal -> Run Deck, with another active owner.
    from tests.test_qt_scene_port import make_job, qt_app, qt_main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    runtime = bridge._runtime
    failed = make_job(tmp_path)
    runtime.recovery.terminal_attempt(failed, "Failed", "Original failure")
    runtime.recovered = runtime.recovery.store.load_terminal_jobs()
    active = replace(make_job(tmp_path), run_id="independent-active")
    runtime.recovery.begin(active)
    runtime.active_job = active
    runtime.events.put(("status", "Independent active download"))
    runtime.poll()
    try:
        assert bridge.retryTerminal(failed.run_id)
        retry = runtime.queued[0]
        assert retry.run_id != failed.run_id
        assert retry.retry_of_run_id == failed.run_id
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        components = bridge.libraryFolders["components"]
        assert len(components) == 1
        assert bridge.selectLibraryFolderComponent(components[0]["key"])
        inspector = bridge.libraryFolderInspector
        assert inspector["status"] == "Queued"
        deck = [r for r in bridge.runDeck["records"] if r["runId"] == retry.run_id]
        assert len(deck) == 1
        assert deck[0]["status"] == "Queued"
        durable = runtime.recovery.store.load_queued_jobs()
        assert durable[0].run_id == retry.run_id
        assert bridge.removeQueued(retry.run_id)
        assert runtime.active_job.run_id == "independent-active"
        assert runtime.active_status == "Independent active download"
        assert not runtime.recovery.store.load_queued_jobs()
        assert not bridge.libraryFolders["components"]
        assert not [r for r in bridge.runDeck["records"] if r["runId"] == retry.run_id]
    finally:
        bridge.close()


def test_matrix_expands_both_catalogs_without_dropping_unknowns():
    from quality_harness.workflow_coverage import matrix_report

    found = inventory(ROOT)
    report = matrix_report(found, {})
    locations = report["catalogs"]["locations"]
    features = report["catalogs"]["features"]
    assert len(report["coverage"]["goals"]) == len(locations) * len(features)
    assert all(row["click_count"] is None for row in report["coverage"]["goals"])
    assert all(row["status"] == "unverified" for row in report["coverage"]["goals"])
    extra = scan_qml("NewScene.qml", "Item { StoneButton { onClicked: newAction() } }")
    found["files"].append(extra)
    found["sites"].extend(extra["sites"])
    expanded = matrix_report(found, {})
    assert len(expanded["catalogs"]["locations"]) == len(locations) + 1
    assert len(expanded["catalogs"]["features"]) == len(features) + 1
    assert expanded["matrix_denominator"] == (len(locations) + 1) * (len(features) + 1)


def test_headless_pointer_observation_binds_navigation_to_source(tmp_path, monkeypatch):
    import json
    import os

    from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest

    from tests.test_qt_scene_port import make_job, qt_app, qt_main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    QQuickStyle.setStyle("Basic")
    bridge = qt_main.Bridge(None)
    bridge._engagement.presented_welcome()
    bridge._runtime.active_job = make_job(tmp_path)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.show()
        QTest.qWait(100)
        button = window.findChild(QObject, "allRunsButton")
        assert button.property("visible") and button.property("enabled")
        point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
        assert bridge.selection == "Forge"
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(point.x()), round(point.y())),
        )
        app.processEvents()
        assert bridge.selection == "Library"
        found = inventory(ROOT)
        from quality_harness.workflow_coverage import runtime_controls

        live = runtime_controls(window, found)
        assert live["counts"]["interactive_candidates"] > 0
        assert live["counts"]["unmapped_runtime_candidates"] > 0
        site = next(
            s
            for s in found["sites"]
            if s["binding"] == "onClicked"
            and s["expression"] == "allRunsButton.activated()"
        )
        evidence = {
            "edges": [
                {
                    "site": site["site"],
                    "binding_sha256": site["binding_sha256"],
                    "file_sha256": site["file_sha256"],
                    "tier": "headless_ui",
                    "receipt": "test_headless_pointer_observation_binds_navigation_to_source",
                    "visible": True,
                    "enabled": True,
                    "from": "Forge",
                    "to": "Library",
                    "steps": ["navigation"],
                }
            ],
            "goals": [{"from": "Forge", "to": "Library"}],
        }
        evidence["edges"].append(
            {**evidence["edges"][0], "to": "action:" + site["site"]}
        )
        report = path_report(found, evidence)
        assert report["goals"][0]["steps"] == 1
        assert report["counts"]["observed_handler_sites"] == 1
        if os.environ.get("VODFORGE_WORKFLOW_EVIDENCE"):
            Path(os.environ["VODFORGE_WORKFLOW_EVIDENCE"]).write_text(
                json.dumps(
                    {"evidence": evidence, "report": report, "runtime_inventory": live},
                    indent=2,
                )
            )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_modeled_practical_paths_count_nested_routes_and_missing_binding():
    from quality_harness.workflow_coverage import matrix_report

    found = inventory(ROOT)
    report = matrix_report(found, {})

    def row(location, feature):
        return next(
            r
            for r in report["coverage"]["goals"]
            if r["from"] == location and r["feature"] == feature
        )

    assert row("Library/issues", "find_missing_media")["modeled"]["click_count"] == 2
    assert row("Forge", "find_missing_media")["modeled"]["click_count"] == 4
    assert row("Forge", "review_trash_saved_media")["modeled"]["click_count"] == 4
    assert row("Library", "review_trash_saved_media")["modeled"]["click_count"] == 3
    removed = [
        s
        for s in found["sites"]
        if not any(
            (
                call.endswith(".requestMissingFileRelink")
                or call == "relinkFileDialog.open"
            )
            for call in s["calls"]
        )
    ]
    found["sites"] = removed
    broken = matrix_report(found, {})
    missing = next(
        r
        for r in broken["coverage"]["goals"]
        if r["from"] == "Library/issues" and r["feature"] == "find_missing_media"
    )
    assert missing["modeled"]["click_count"] is None


def test_semantic_catalog_groups_commands_but_retains_all_source_classifications():
    from quality_harness.workflow_coverage import semantic_catalogs

    texts = [
        (
            "Scene.qml",
            """Item {
            StoneButton { label: "Remove"; onActivated: bridge.removeQueued(owner) }
            StoneButton { label: "Remove"; onActivated: { panel.appBridge.removeQueued(owner); menu.close() } }
            Timer { onTriggered: poll() }
            Item { onMysteryChanged: refresh() }
        }""",
        ),
    ]
    files = [scan_qml(path, text) for path, text in texts]
    found = {"files": files, "sites": [s for f in files for s in f["sites"]]}
    result = semantic_catalogs(found)
    operation = next(f for f in result["features"] if f["id"] == "remove_queued")
    assert len(operation["sites"]) == 2
    assert len(result["source_classifications"]) == len(found["sites"])
    assert result["classification_counts"]["lifecycle"] == 1
    assert result["classification_counts"]["state_listener_unreviewed"] == 1
    assert not [f for f in result["features"] if "poll" in f["id"]]


def test_semantic_selected_state_does_not_substitute_another_target():
    from quality_harness.workflow_coverage import semantic_report

    report = semantic_report(inventory(ROOT), {})
    active = next(
        r
        for r in report["rows"]
        if r["location"] == "Forge/selected-run:active" and r["feature"] == "retry_run"
    )
    failed = next(
        r
        for r in report["rows"]
        if r["location"] == "Forge/selected-run:Failed" and r["feature"] == "retry_run"
    )
    assert active["modeled"]["status"] == "not_applicable"
    assert active["modeled"]["click_count"] is None
    assert failed["modeled"]["click_count"] == 2
    assert report["matrix_denominator"] == len(report["catalogs"]["locations"]) * len(
        report["catalogs"]["features"]
    )


@pytest.mark.parametrize("fault", ["none", "tamper", "owner", "count"])
def test_native_history_preserves_original_revision_and_rejects_faults(tmp_path, fault):
    import hashlib
    import json

    from quality_harness.workflow_coverage import native_history

    artifacts = {
        "owner.json": {"pid": 11, "source_commit": "original"},
        "ready.json": {"pid": 11, "window_id": 12, "visible": True},
        "finished.json": {"exit_code": 0, "owned_process_still_running": False},
    }
    for name, contents in artifacts.items():
        (tmp_path / name).write_text(json.dumps(contents))
    payload = {
        "source_commit": "original",
        "actual_pid": 11,
        "native_window": 12,
        "normal_exit": 0,
        "survivor": False,
        "observations": [
            {
                "location": "Forge/idle",
                "action": "output-folder-picker",
                "clicks": 1,
                "sequence": ["Choose output folder"],
                "result": "PASS",
            }
        ],
        "artifacts_sha256": {
            name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
            for name in artifacts
        },
    }
    if fault == "tamper":
        (tmp_path / "owner.json").write_text("{}")
    elif fault == "owner":
        payload["actual_pid"] = 99
    elif fault == "count":
        payload["observations"][0]["clicks"] = 2
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(payload))
    result = native_history(path)
    if fault == "none":
        assert result["accepted"][0]["source_commit"] == "original"
        assert result["accepted"][0]["click_count"] == 1
        assert result["successor_acceptance"] is False
    else:
        assert not result["accepted"]
        assert result["rejected"]


def test_semantic_validated_path_survives_unrelated_rejected_edge():
    from quality_harness.workflow_coverage import semantic_report

    found = inventory(ROOT)
    site = next(
        s
        for s in found["sites"]
        if s["binding"] == "onActivated" and ".removeQueued" in s["expression"]
    )
    valid = {
        "site": site["site"],
        "binding_sha256": site["binding_sha256"],
        "file_sha256": site["file_sha256"],
        "tier": "headless_ui",
        "receipt": "controlled regression",
        "visible": True,
        "enabled": True,
        "from": "Forge",
        "to": "action:remove_queued",
        "steps": ["menu", "action"],
    }
    report = semantic_report(
        found, {"edges": [{"site": "missing", "from": "Forge", "to": "stale"}, valid]}
    )
    row = next(
        r
        for r in report["rows"]
        if r["location"] == "Forge" and r["feature"] == "remove_queued"
    )
    assert row["validated_click_count"] == 2
    assert row["validated_path"] == [valid]


@pytest.mark.parametrize("revision", [None, "", " "])
def test_native_history_rejects_missing_revision_even_when_owners_agree(
    tmp_path, revision
):
    import hashlib
    import json

    from quality_harness.workflow_coverage import native_history

    blobs = {
        "owner.json": {"pid": 11, "source_commit": revision},
        "ready.json": {"pid": 11, "window_id": 12, "visible": True},
        "finished.json": {"exit_code": 0, "owned_process_still_running": False},
    }
    for name, blob in blobs.items():
        (tmp_path / name).write_text(json.dumps(blob))
    payload = {
        "source_commit": revision,
        "actual_pid": 11,
        "native_window": 12,
        "normal_exit": 0,
        "survivor": False,
        "observations": [
            {
                "location": "Forge/idle",
                "action": "output-folder-picker",
                "clicks": 1,
                "sequence": ["Choose output folder"],
                "result": "PASS",
            }
        ],
        "artifacts_sha256": {
            name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
            for name in blobs
        },
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(payload))
    report = native_history(path)
    assert not report["accepted"]
    assert report["rejected"][0]["reason"] == "owner_window_revision_exit_mismatch"


def test_terminal_dismissal_requires_issues_route_from_home_and_visible_popup_is_one_click():
    from quality_harness.workflow_coverage import semantic_report

    report = semantic_report(inventory(ROOT), {})
    row = next(
        r
        for r in report["rows"]
        if r["location"] == "Library" and r["feature"] == "dismiss_run"
    )
    assert row["modeled"]["click_count"] == 4
    candidates = [
        r
        for r in report["rows"]
        if r["feature"] == "find_missing_media"
        and r["location"].startswith("yt_downloader/qt_quick/Main.qml:")
        and r["modeled"]["click_count"] == 1
    ]
    assert len(candidates) == 3


def test_independent_right_click_area_is_not_erased_as_button_adapter(
    tmp_path, monkeypatch
):
    from PySide6.QtCore import QCoreApplication, QEvent, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from quality_harness.workflow_coverage import runtime_controls

    from tests.test_qt_scene_port import qt_app, qt_main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
StoneButton { objectName: "fixtureButton"; label: "Fixture"
    MouseArea { objectName: "independentRightClick"; acceptedButtons: Qt.RightButton }
    MouseArea { acceptedButtons: Qt.RightButton }
}""",
        QUrl.fromLocalFile(str(ROOT / "yt_downloader/qt_quick/coverage_fixture.qml")),
    )
    widget = component.create(QQmlEngine.contextForObject(window))
    try:
        assert widget is not None, [str(e) for e in component.errors()]
        report = runtime_controls(widget, inventory(ROOT))
        areas = [
            c for c in report["controls"] if c["qt_type"].startswith("QQuickMouseArea")
        ]
        right = [c for c in areas if c["accepted_buttons"] & 2]
        assert len(right) == 2
        assert all(c["exclusion_reason"] is None for c in right)
        assert any(
            c["exclusion_reason"] for c in areas if not c["accepted_buttons"] & 2
        )
    finally:
        if widget is not None:
            widget.deleteLater()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_inherited_popup_and_window_consumers_are_discovered_without_name_heuristics(
    tmp_path,
):
    from quality_harness.workflow_coverage import semantic_catalogs

    source = tmp_path / "yt_downloader/qt_quick"
    source.mkdir(parents=True)
    (source / "OverlayPanel.qml").write_text("Popup { id: base }")
    (source / "FilmControls.qml").write_text(
        "Item { OverlayPanel { id: captions } Window { id: floating } }"
    )
    found = inventory(tmp_path)
    catalog = semantic_catalogs(found)
    contexts = [
        location["source"]
        for location in catalog["locations"]
        if location["kind"] == "declared_menu_dialog"
    ]
    assert any(
        context.endswith(":OverlayPanel") and "FilmControls.qml" in context
        for context in contexts
    )
    assert any(context.endswith(":Window") for context in contexts)
    assert not any("OverlayPanel.qml" in context for context in contexts)


def test_same_file_signal_adapter_and_consumer_share_one_semantic_action():
    from quality_harness.workflow_coverage import semantic_catalogs

    file = scan_qml(
        "yt_downloader/qt_quick/Scene.qml",
        """Item { id: entry
        signal activated()
        onActivated: bridge.select("Library")
        MouseArea { onClicked: entry.activated() }
    }""",
    )
    found = {
        "files": [file],
        "sites": file["sites"],
        "route_contexts": [],
        "state_contracts": [],
    }
    catalog = semantic_catalogs(found)
    actual = [feature for feature in catalog["features"] if feature["sites"]]
    assert len(actual) == 1
    assert len(actual[0]["sites"]) == 2
    assert actual[0]["id"] == "command:select:Library"


def test_data_entry_control_without_callback_remains_in_semantic_catalog(tmp_path):
    from quality_harness.workflow_coverage import semantic_catalogs

    source = tmp_path / "yt_downloader/qt_quick"
    source.mkdir(parents=True)
    (source / "Main.qml").write_text("""Item { visible: bridge.selection === "Forge"
       TextField { objectName: "draftSource"; placeholderText: "Source URL" }
    }""")
    found = inventory(tmp_path)
    catalog = semantic_catalogs(found)
    field = next(
        feature
        for feature in catalog["features"]
        if feature["id"] == "control:Main:draftSource"
    )
    assert field["screens"] == ["Forge"]
    assert field["input_callbacks"] == []
    assert "typing" in field["non_click_steps"]
    assert catalog["classification_counts"]["declared_input_control"] == 1
