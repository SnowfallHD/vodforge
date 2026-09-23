"""Actual Tk geometry and live application use-site propagation, isolated data."""

import os
import time
from dataclasses import replace
from tkinter import ttk

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from tests.test_archive_native import application as _application
from yt_downloader import app as app_module
from yt_downloader import ui_button_contract as contract
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.library_collection_ui import LibraryCollectionDialog
from yt_downloader.whats_new import WhatsNewOwner

application = _application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="Native display required"
)


@pytest.mark.parametrize(
    "height,font_pixels,bypass", [(44, 15, False), (50, 17, False), (44, 15, True)]
)
def test_shared_primary_metrics_reach_live_forge_library_watch_and_dialog(
    monkeypatch, height, font_pixels, bypass
):
    monkeypatch.setitem(
        contract.BUTTON_METRICS,
        "default",
        replace(contract.button_metrics(), height=height, font_pixels=font_pixels),
    )
    for owner in (AnalyticsStartup, EngagementUI, WhatsNewOwner):
        monkeypatch.setattr(owner, "start", lambda self: None)
    with isolated_preview_services():
        app = app_module.DownloaderApp()
        app.geometry("1414x1008+70+50")
        app.deiconify()
        errors = []
        app.report_callback_exception = lambda *args: errors.append(str(args[1]))

        def pump():
            deadline = time.monotonic() + 0.35
            while time.monotonic() < deadline:
                app.update()
                time.sleep(0.005)

        def scene_button(scene, label):
            matches = [
                (box, item)
                for box, item, _, _ in scene._button_labels
                if scene.canvas.itemcget(item, "text") == label
            ]
            assert len(matches) == 1, (label, matches)
            box, item = matches[0]
            assert box[3] - box[1] == height
            font = app.tk.splitlist(scene.canvas.itemcget(item, "font"))
            assert int(font[1]) == -font_pixels
            text_box = scene.canvas.bbox(item)
            assert text_box[1] >= box[1] and text_box[3] <= box[3]

        try:
            pump()
            if bypass:
                # Reintroduce the original local style override after the common
                # owner runs. The same live-geometry oracle must reject it.
                ttk.Style(app).configure("Media.Accent.TButton", padding=(5, 0))
                pump()
                with pytest.raises(AssertionError):
                    assert app.download_button.winfo_height() == height
                return
            assert app.download_button.winfo_height() == height
            assert ttk.Style(app).lookup("Media.Accent.TButton", "font") == ttk.Style(
                app
            ).lookup("Accent.TButton", "font")
            app.download_history = []
            app._reconcile_library_projection()
            app._select_focus_view("library")
            app.library_scene.navigate("home")
            pump()
            scene_button(app.library_scene, "Go to Forge")
            app._select_focus_view("watch")
            pump()
            scene_button(app.focus_watch, "Go to Forge")
            saved = []
            dialog = LibraryCollectionDialog(
                app, [("one", "One video")], lambda *args: saved.append(args)
            )
            pump()
            assert dialog.save_button.winfo_height() == height
            dialog.save_button.state(["disabled"])
            dialog.save_button.invoke()
            assert not saved
            dialog.popup.destroy()
            assert not errors
        finally:
            app._request_application_close()
            deadline = time.monotonic() + 3
            while app.tk.call("info", "commands", ".") and time.monotonic() < deadline:
                app.update()
                time.sleep(0.005)
            if app.tk.call("info", "commands", "."):
                app.destroy()


@pytest.mark.parametrize(
    "retire", ["outside", "disabled", "replaced", "other_instance", "hidden"]
)
def test_shared_native_button_retires_pointer_without_cross_instance_actions(retire):
    import tkinter as tk

    from yt_downloader.ui_styles import apply_product_styles

    root = tk.Tk()
    apply_product_styles(root)
    calls = []
    first = contract.ProductButton(
        root, text="First", command=lambda: calls.append("first")
    )
    second = contract.ProductButton(
        root, text="Second", command=lambda: calls.append("second")
    )
    first.pack()
    second.pack()
    root.update()
    try:
        first.event_generate("<Enter>")
        first.event_generate("<ButtonPress-1>", x=12, y=12)
        root.update()
        assert calls == []
        if retire == "disabled":
            first.state(["disabled"])
            first.state(["!disabled"])
        elif retire == "replaced":
            first.configure(command=lambda: calls.append("replacement"))
        elif retire == "hidden":
            first.pack_forget()
            root.update()
            first.pack()
            root.update()
        target = second if retire == "other_instance" else first
        target.event_generate(
            "<ButtonRelease-1>", x=-2 if retire == "outside" else 12, y=12
        )
        root.update()
        assert calls == []
        # An ordinary new click still belongs to its own instance.
        second.event_generate("<Enter>")
        second.event_generate("<ButtonPress-1>", x=12, y=12)
        second.event_generate("<ButtonRelease-1>", x=12, y=12)
        root.update()
        assert calls == ["second"]
    finally:
        root.destroy()


def _exercise_button_sequences(button_type, seed, sequences=32, evidence_dir=None):
    """Independent intent model; assert every prefix, not only settled results."""
    import json
    import random
    import tkinter as tk
    from collections import Counter
    from pathlib import Path

    from yt_downloader.ui_styles import apply_product_styles

    rng = random.Random(seed)
    root = tk.Tk()
    apply_product_styles(root)
    expected, observed, trace = [], [], []
    serial = 0
    button = None
    operations, transitions = Counter(), Counter()
    pointer_commits = direct_invocations = retired_releases = 0
    passed = False
    try:
        for trial in range(sequences):
            if button is not None:
                button.destroy()
            serial += 1
            revision = 0
            enabled = True
            pressed = None
            token = (serial, revision)
            button = button_type(
                root,
                text="Generated action",
                command=lambda value=token: observed.append(value),
            )
            button.pack()
            root.update()
            # Always exercise an outside release, then vary state interleavings.
            steps = ["press", "release", "press", "outside"]
            steps += rng.choices(
                [
                    "press",
                    "release",
                    "outside",
                    "disable",
                    "enable",
                    "replace",
                    "replace_widget",
                    "invoke",
                ],
                k=16,
            )
            for step in steps:
                trace.append((trial, step))
                operations[step] += 1
                transitions[
                    f"{step}:enabled={enabled}:admitted={pressed is not None}:current={pressed == (serial, revision)}"
                ] += 1
                if step == "press":
                    pressed = (serial, revision) if enabled else None
                    button.event_generate("<Enter>")
                    button.event_generate("<ButtonPress-1>", x=12, y=12)
                elif step in {"release", "outside"}:
                    if step == "release" and enabled and pressed == (serial, revision):
                        expected.append((serial, revision))
                        pointer_commits += 1
                    else:
                        retired_releases += 1
                    pressed = None
                    if step == "outside":
                        button.event_generate("<Leave>")
                    button.event_generate(
                        "<ButtonRelease-1>", x=-2 if step == "outside" else 12, y=12
                    )
                elif step == "disable":
                    enabled, pressed = False, None
                    button.state(["disabled"])
                elif step == "enable":
                    enabled = True
                    button.state(["!disabled"])
                elif step == "replace":
                    revision += 1
                    token = (serial, revision)
                    button.configure(command=lambda value=token: observed.append(value))
                elif step == "replace_widget":
                    button.destroy()
                    serial += 1
                    revision, enabled, pressed = 0, True, None
                    token = (serial, revision)
                    button = button_type(
                        root,
                        text="Replacement action",
                        command=lambda value=token: observed.append(value),
                    )
                    button.pack()
                elif step == "invoke":
                    if enabled:
                        expected.append((serial, revision))
                        direct_invocations += 1
                    button.invoke()
                root.update()
                assert observed == expected, (
                    "action model mismatch",
                    seed,
                    trace[-25:],
                    expected,
                    observed,
                )
        assert pointer_commits >= sequences, (
            "Every episode must include an accepted pointer action"
        )
        assert retired_releases >= sequences, (
            "Every episode must include a retired pointer action"
        )
        if sequences > 1:
            assert set(operations) == {
                "press",
                "release",
                "outside",
                "disable",
                "enable",
                "replace",
                "replace_widget",
                "invoke",
            }
        passed = True
    finally:
        if evidence_dir is not None:
            output = Path(evidence_dir)
            output.mkdir(parents=True, exist_ok=True)
            (output / f"button-model-{button_type.__name__}-{seed}.json").write_text(
                json.dumps(
                    {
                        "seed": seed,
                        "episodes": sequences,
                        "passed": passed,
                        "operations": dict(operations),
                        "transitions": dict(transitions),
                        "pointer_commits": pointer_commits,
                        "direct_invocations": direct_invocations,
                        "retired_releases": retired_releases,
                        "trace": trace,
                        "expected": expected,
                        "observed": observed,
                    },
                    indent=2,
                )
                + "\n"
            )
        root.destroy()


_MODEL_SEEDS = [7149, 27183, 49157]
if os.environ.get("VODFORGE_NATIVE_PROFILE") == "deep":
    _MODEL_SEEDS += [104729, 130363, 155921, 196613, 262147, 327673]


@pytest.mark.parametrize("seed", _MODEL_SEEDS)
def test_generated_shared_button_event_sequences_match_intent_model(seed, tmp_path):
    _exercise_button_sequences(
        contract.ProductButton,
        seed,
        evidence_dir=os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)),
    )


def test_generated_sequence_model_detects_native_release_bypass(tmp_path):
    # The native ttk class is the real pre-fix bypass, not a fixture error.
    with pytest.raises(AssertionError, match="action model mismatch"):
        _exercise_button_sequences(
            ttk.Button,
            7149,
            sequences=1,
            evidence_dir=os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)),
        )


@pytest.mark.parametrize("inline_size,bypass", [(32, False), (36, False), (32, True)])
def test_library_icon_metrics_reach_cards_tags_and_saved_location(
    request, monkeypatch, tmp_path, inline_size, bypass
):
    """Observe real rendered hit regions at each live icon call site."""
    import inspect
    import json
    from pathlib import Path

    from tests.test_archive_native import pump, seed
    from yt_downloader.scene_components import ScenePainter

    app = request.getfixturevalue("application")
    monkeypatch.setitem(
        contract.BUTTON_METRICS,
        "inline",
        replace(
            contract.button_metrics(),
            height=inline_size,
            font_pixels=14,
            icon_pixels=18,
        ),
    )
    observed = {}
    original = ScenePainter.button
    roles = {
        ("_detail_panel", "copy"): inline_size,
        ("_detail_notes", "copy"): inline_size,
        ("_detail_notes", "plus"): inline_size,
        ("_media_card", "more"): contract.button_metrics().height,
        ("_collection_card", "more"): inline_size,
    }

    def record(painter, *args, **kwargs):
        caller = inspect.currentframe().f_back.f_code.co_name
        key = (caller, kwargs.get("icon"))
        if bypass and key == ("_detail_notes", "copy"):
            kwargs["variant"] = "default"
        result = original(painter, *args, **kwargs)
        if key in roles:
            box = painter.view._targets[-1][0]
            observed[key] = list(box)
        return result

    monkeypatch.setattr(ScenePainter, "button", record)
    seed(app, tmp_path, count=9)
    app.geometry("1280x760+20+60")
    app._select_focus_view("library")
    scene = app.library_scene
    for route in ("videos", "channels"):
        scene.navigate(route)
        pump(app, 0.4)
    scene.show_details(0)
    pump(app, 0.5)
    receipt = {
        "/".join(key): {"bounds": box, "expected_size": roles[key]}
        for key, box in observed.items()
    }
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / f"library-icon-metrics-{inline_size}-{bypass}.json").write_text(
        json.dumps(receipt, indent=2)
    )
    assert set(observed) == set(roles), receipt

    def assert_sizes():
        assert all(
            box[2] - box[0] == roles[key] and box[3] - box[1] == roles[key]
            for key, box in observed.items()
        ), receipt

    if bypass:
        with pytest.raises(AssertionError):
            assert_sizes()
    else:
        assert_sizes()


@pytest.mark.parametrize("retire", [False, True])
def test_library_inline_copy_has_visible_feedback_and_current_render_ownership(
    application, monkeypatch, tmp_path, retire
):
    """Generated Tk input, actual Library layout; no system clipboard mutation."""
    import inspect
    import json
    from pathlib import Path

    from tests.test_archive_native import pump, seed
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.scene_components import ScenePainter

    app = application
    seed(app, tmp_path, count=1)
    app.geometry("1280x760+20+60")
    app._select_focus_view("library")
    scene = app.library_scene
    copies, copy_targets = [], []
    monkeypatch.setattr(scene, "_copy_value", copies.append)
    original = ScenePainter.button

    def record(painter, *args, **kwargs):
        caller = inspect.currentframe().f_back.f_code.co_name
        result = original(painter, *args, **kwargs)
        if caller == "_detail_notes" and kwargs.get("icon") == "copy":
            copy_targets.append(painter.view._targets[-1])
        return result

    monkeypatch.setattr(ScenePainter, "button", record)
    scene.show_details(0)
    pump(app, 0.6)
    canvas = scene.canvas
    box = copy_targets[-1][0]
    extent = float(canvas.tk.splitlist(canvas.cget("scrollregion"))[3])
    canvas.yview_moveto(max(0, box[1] - 70) / extent)
    pump(app, 0.2)
    box = copy_targets[-1][0]
    x, y = (
        round((box[0] + box[2]) / 2 - canvas.canvasx(0)),
        round((box[1] + box[3]) / 2 - canvas.canvasy(0)),
    )
    assert 0 < x < canvas.winfo_width() and 0 < y < canvas.winfo_height()
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    states = []
    material = canvas._action_material
    assert box in material.controls
    item = material.controls[box][0]
    assert canvas.type(item) == "image"

    def snapshot(phase):
        canvas.update_idletasks()
        assert not canvas.find_withtag("pointer-state")
        current_item = material.controls[box][0]
        assert canvas.type(current_item) == "image"
        image = capture_own_widget(canvas)
        assert image is not None
        image.save(output / f"inline-copy-{retire}-{phase}.png")
        states.append(
            {
                "phase": phase,
                "copy_count": len(copies),
                "material_image": canvas.itemcget(current_item, "image"),
            }
        )
        return image

    before = snapshot("before")
    canvas.event_generate("<Motion>", x=x, y=y)
    hover = snapshot("hover")
    assert not canvas.find_withtag("pointer-state")
    canvas.event_generate("<ButtonPress-1>", x=x, y=y)
    pressed = snapshot("pressed")
    from PIL import ImageChops

    assert states[-1]["material_image"] != states[0]["material_image"]
    assert ImageChops.difference(before, hover).getbbox() is not None
    assert ImageChops.difference(hover, pressed).getbbox() is not None
    assert copies == []
    if retire:
        scene._render()
    canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    snapshot("released")
    assert copies == ([] if retire else [""])
    # A fresh gesture works after retirement; a second release cannot repeat it.
    if retire:
        canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    assert copies == [""]
    (output / f"inline-copy-{retire}.json").write_text(
        json.dumps(
            {
                "input": "generated Tk events, not physical input",
                "states": states,
                "retired_between_press_and_release": retire,
                "copies": copies,
            },
            indent=2,
        )
    )
