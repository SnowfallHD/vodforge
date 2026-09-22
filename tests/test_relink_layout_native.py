"""Relink sizing uses current wrapped text metrics, without observer event pumping."""

from __future__ import annotations

import json
import os
import time
import tkinter as tk
from pathlib import Path

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


@pytest.mark.parametrize("width", [980, 1440])
@pytest.mark.parametrize("count", [1, 25, 5000])
def test_relink_measurements_match_final_wrapped_content(
    application, tmp_path, monkeypatch, width, count
):
    app = application
    rows = seed(app, tmp_path, count)
    rows[0]["title"] = "A naïve café 🎬 — {first export}"
    rows[-1]["title"] = "Last export — 日本語 and {literal braces}"
    app._reconcile_library_projection()
    app.geometry(f"{width}x820+50+60")
    app._select_focus_view("library")
    pump(app, 0.3)
    app._archive_worker.close()
    replacement = tmp_path / ("long-selected-location-" * 5 + ".mp4")
    replacement.write_bytes(b"existence fixture")
    original_count = tk.Text.count
    observations = []
    events = []
    original_register = tk.Misc._register

    def observed_register(widget, callback, *args, **kwargs):
        if getattr(callback, "__name__", "") == "fit_review":
            actual = callback

            def traced(*values):
                events.append({"event": "fit_started", "time": time.monotonic()})
                try:
                    return actual(*values)
                finally:
                    events.append({"event": "fit_completed", "time": time.monotonic()})

            callback = traced
        return original_register(widget, callback, *args, **kwargs)

    monkeypatch.setattr(tk.Misc, "_register", observed_register)

    def observed_count(widget, index1, index2, *options):
        start = time.monotonic()
        result = original_count(widget, index1, index2, *options)
        if "ypixels" in options:
            pixels = result if isinstance(result, int) else (result or (0,))[0]
            observations.append(
                {
                    "width": widget.winfo_width(),
                    "pixels": int(pixels),
                    "end_index": widget.index(index2),
                    "available_height": app._archive_overlay.grid_bbox(0, 2, 1, 2)[3],
                    "elapsed_ms": (time.monotonic() - start) * 1000,
                }
            )
        return result

    monkeypatch.setattr(tk.Text, "count", observed_count)
    original_delete, original_insert = tk.Text.delete, tk.Text.insert
    replacements = {}
    insert_seconds = []

    def observed_delete(widget, *args):
        replacements.setdefault(str(widget), []).append(0)
        return original_delete(widget, *args)

    def observed_insert(widget, *args):
        passes = replacements.get(str(widget))
        if passes:
            passes[-1] += 1
        began = time.monotonic()
        result = original_insert(widget, *args)
        insert_seconds.append(time.monotonic() - began)
        return result

    monkeypatch.setattr(tk.Text, "delete", observed_delete)
    monkeypatch.setattr(tk.Text, "insert", observed_insert)

    def open_review():
        events.append({"event": "open_started", "time": time.monotonic()})
        app._archive_begin_relink(None, tuple(range(count)), exact=str(replacement))
        events.append({"event": "open_completed", "time": time.monotonic()})

    def quit_observed():
        events.append({"event": "quit_started", "time": time.monotonic()})
        app.quit()

    events.append({"event": "open_and_quit_scheduled", "time": time.monotonic()})
    app.after(0, open_review)
    app.after(1200, quit_observed)
    # The observer does not service update/idle events or request a screenshot.
    began = time.monotonic()
    app.mainloop()
    mainloop_seconds = time.monotonic() - began
    panel = app._archive_overlay
    surface = panel._archive_relink_review
    document = next(w for w in surface.winfo_children() if isinstance(w, tk.Text))
    before_reference = {
        "surface_height": surface.winfo_height(),
        "requested_height": int(surface.cget("height")),
        "available_height": panel.grid_bbox(0, 2, 1, 2)[3],
        "document_height": document.winfo_height(),
    }
    # Independent exact reference is taken only AFTER the ordinary-loop sample.
    expected = int(
        document.tk.call(document._w, "count", "-update", "-ypixels", "1.0", "end")
    )
    width_now = document.winfo_width()
    comparable = [row for row in observations if row["width"] == width_now]
    line_height = max(
        1, int(document.tk.call("font", "metrics", document.cget("font"), "-linespace"))
    )
    for row in comparable:
        row["exact_reference"] = int(
            document.tk.call(
                document._w, "count", "-update", "-ypixels", "1.0", row["end_index"]
            )
        )
    titles = document.tag_ranges("review-title")
    copied_text = document.get("1.0", "end")
    checks = {
        "all_record_titles_tagged": len(titles) == 2 * count,
        "first_and_last_unicode_title_retained": bool(titles)
        and document.get(titles[0], titles[1]) == rows[0]["title"] + "\n"
        and document.get(titles[-2], titles[-1]) == rows[-1]["title"] + "\n",
        # File-mode selection supplies one exact destination; remaining entries
        # intentionally have no destination. Every recorded source still appears.
        "exact_selected_path_copied_once": copied_text.count(str(replacement)) == 1,
        "all_recorded_paths_copied": {
            str(row["vodforge_output_path"]) for row in rows
        }.issubset(set(copied_text.splitlines())),
        "document_replacement_native_calls_bounded": bool(
            replacements.get(str(document))
        )
        and max(replacements[str(document)]) <= 1,
        "measurements_observed": bool(comparable),
        "all_current_width_measurements_exact": bool(comparable)
        and all(row["pixels"] == row["exact_reference"] for row in comparable),
        "measurement_work_bounded_by_viewport": bool(comparable)
        and all(
            int(row["end_index"].split(".")[0])
            <= max(100, row["available_height"]) // line_height + 2
            for row in comparable
        ),
        "height_matches_full_document_clamp": surface.winfo_height()
        == min(max(100, panel.grid_bbox(0, 2, 1, 2)[3]), max(100, expected + 34)),
        "review_within_available_space": surface.winfo_height()
        <= panel.grid_bbox(0, 2, 1, 2)[3],
        "document_retains_full_path": str(replacement) in document.get("1.0", "end"),
    }
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    (output / f"relink-metrics-{width}-{count}.json").write_text(
        json.dumps(
            {
                "scope": "Real Text measurement during ordinary mainloop; not temporal pixel or physical-input acceptance",
                "width": width,
                "count": count,
                "expected_pixels": expected,
                "mainloop_seconds": mainloop_seconds,
                "before_reference": before_reference,
                "callback_events": [
                    {**row, "time": row["time"] - began} for row in events
                ],
                "native_insert_calls_per_replacement": replacements.get(str(document)),
                "native_insert_seconds": insert_seconds,
                "copied_text_characters": len(copied_text),
                "title_tag_ranges": len(titles),
                "after_reference": {
                    "surface_height": surface.winfo_height(),
                    "requested_height": int(surface.cget("height")),
                    "available_height": panel.grid_bbox(0, 2, 1, 2)[3],
                    "document_height": document.winfo_height(),
                },
                "observations": observations,
                "checks": checks,
            },
            indent=2,
        )
    )
    assert all(checks.values()), checks
