"""Measure current catalog projection separately from bounded native drawing."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pytest

from tests.test_archive_native import application as _application

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1" or sys.platform != "darwin",
    reason="explicit Mac native scale measurement required",
)


def test_large_catalog_projection_and_render_costs_are_separate(application, tmp_path):
    import resource

    app = application
    app.geometry("1414x900")
    app._select_focus_view("watch")
    watch = app.focus_watch
    source_root = Path(__file__).resolve().parents[1]

    def source_binding():
        return {
            str(path.relative_to(source_root)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted((source_root / "yt_downloader").glob("*.py"))
        }

    source_before = source_binding()
    observations = []
    for count in (5000, 20000):
        records = tuple(
            {
                "id": f"scale-{index}",
                "title": f"Saved video {index}",
                "channel": f"Creator {index // 200}",
                "playlist_id": f"list-{index // 20}",
                "playlist_title": f"Playlist {index // 20}",
                "vodforge_output_dir": str(tmp_path),
                "vodforge_output_path": str(tmp_path / f"media-{index}.mp4"),
            }
            for index in range(count)
        )
        watch._scene_open("videos")
        cold_start = time.perf_counter()
        watch.set_records(records)
        projection_ms = (time.perf_counter() - cold_start) * 1000
        watch._render()
        app.update_idletasks()
        cold_presentation_ms = (time.perf_counter() - cold_start) * 1000
        # Memory instrumentation is a separate uncached query, outside timings.
        tracemalloc.start()
        watch._scene_projection("", "Saved", False)
        _, projection_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        start = time.perf_counter()
        watch._render()
        app.update_idletasks()
        render_ms = (time.perf_counter() - start) * 1000
        first_count = len(watch.canvas.find_all())
        assert first_count < 500
        watch.canvas.yview_moveto(1)
        start = time.perf_counter()
        watch._render()
        app.update_idletasks()
        last_render_ms = (time.perf_counter() - start) * 1000
        assert len(watch.canvas.find_all()) < 500
        assert len(watch._presentation_rendered) <= 40
        videos = watch._scene_projection("", "", False)[1]
        assert videos[-1].key in watch._presentation_rendered
        observations.append(
            {
                "records": count,
                "projection_ms": projection_ms,
                "cold_first_presentation_ms": cold_presentation_ms,
                "uncached_query_python_peak_bytes": projection_peak,
                "current_process_rss_bytes": int(
                    subprocess.check_output(
                        ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())], text=True
                    ).strip()
                )
                * 1024,
                "first_page_warm_render_ms": render_ms,
                "last_page_warm_render_ms": last_render_ms,
                "first_canvas_items": first_count,
                "last_canvas_items": len(watch.canvas.find_all()),
                "rendered_media": len(watch._presentation_rendered),
                "rss_high_water_native_units": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
            }
        )
    destination = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "catalog-scale-baseline.json").write_text(
        json.dumps(
            {
                "scope": "Current paged Watch catalog; real Tk, synthetic metadata, missing media/artwork. Cold first presentation includes set_records and first synchronous draw/layout, excluding image completion. Warm draws reuse projection. Uncached-query tracemalloc allocations are separate from timed runs, current process RSS and RSS high-water. No disk catalog, decoder, physical input, or frame-rate claim.",
                "source_root": str(source_root),
                "source_before": source_before,
                "source_after": source_binding(),
                "observations": observations,
            },
            indent=2,
        )
        + chr(10)
    )


def test_continuous_catalog_decoded_artwork_traversal_anchor_and_route_lifetime(
    application, tmp_path, monkeypatch
):
    import gc

    from PIL import Image

    app = application
    errors = []
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    app.geometry("1414x900")
    app._select_focus_view("watch")
    watch = app.focus_watch
    fixtures = []
    for index in range(12):
        path = tmp_path / f"decoded-{index}.jpg"
        Image.new("RGB", (640, 360), (index * 19, 90, 180)).save(path)
        fixtures.append(path)
    monkeypatch.setattr(
        watch, "_artwork_source_path", lambda row, *_args: fixtures[int(row["id"]) % 12]
    )
    records = tuple(
        {
            "id": str(index),
            "title": f"Saved video {index}",
            "channel": "Fixture channel",
            "vodforge_output_dir": str(tmp_path),
            "vodforge_output_path": str(tmp_path / f"media-{index}.mp4"),
        }
        for index in range(2000)
    )

    def ready():
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            app.update()
            wanted = watch._artwork_wanted
            if (
                watch._render_after is None
                and not watch._artwork_owner.busy
                and wanted
                and all(key in watch._artwork_images for key in wanted)
            ):
                return
            time.sleep(0.005)
        raise AssertionError("Visible artwork did not finish within the test deadline")

    def rss():
        return (
            int(
                subprocess.check_output(
                    ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())], text=True
                ).strip()
            )
            * 1024
        )

    watch._scene_open("videos")
    started = time.perf_counter()
    watch.set_records(records)
    ready()
    cold_art_ready_ms = (time.perf_counter() - started) * 1000
    samples = []
    round_rss = []
    for round_index in range(4):
        for fraction in (0, 0.25, 0.5, 0.75, 1, 0.5, 0):
            watch.canvas.yview_moveto(fraction)
            app.update()
            top = watch.canvas.canvasy(0)
            started = time.perf_counter()
            ready()
            assert abs(watch.canvas.canvasy(0) - top) <= 1
            assert len(watch.canvas.find_all()) < 400
            assert len(watch._artwork_images) <= 64
            assert len(watch._artwork_displayed) <= 40
            assert watch._artwork_requested_count <= 24
            videos = watch._scene_projection("", "", False)[1]
            if fraction == 0:
                assert videos[0].key in watch._presentation_rendered
            if fraction == 1:
                assert videos[-1].key in watch._presentation_rendered
            samples.append(
                {
                    "round": round_index,
                    "fraction": fraction,
                    "visible_art_ready_ms": (time.perf_counter() - started) * 1000,
                    "canvas_items": len(watch.canvas.find_all()),
                    "cached_images": len(watch._artwork_images),
                    "displayed_images": len(watch._artwork_displayed),
                    "last_requested_batch": watch._artwork_requested_count,
                }
            )
        gc.collect()
        round_rss.append(rss())
    assert max(round_rss[1:]) - min(round_rss[1:]) < 64 * 1024 * 1024

    watch.canvas.yview_moveto(0.5)
    ready()
    watch._remember_scene_anchor()
    anchor = watch._scene_anchor
    assert anchor
    additions = tuple({**records[0], "id": str(3000 + i)} for i in range(5))
    watch.set_records(additions + records)
    ready()
    assert watch._scene_anchor[1] == anchor[1]
    watch.set_records(records)
    ready()
    assert watch._scene_anchor[1] == anchor[1]

    # Change route while a new viewport's artwork is still being requested.
    watch.canvas.yview_moveto(0.9)
    app.update()
    watch._scene_open("channels")
    app.update()
    watch._scene_open("videos")
    ready()
    assert watch._scene_route == "videos"
    assert (
        watch._scene_projection("", "", False)[1][0].key in watch._presentation_rendered
    )
    assert not errors, errors

    destination = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "continuous-artwork-traversal.json").write_text(
        json.dumps(
            {
                "scope": "Real Tk and decoded generated JPEG artwork; four first/middle/end/back traversals, additions/removals before viewport, route changes. Observed steady-state RSS range is a bounded-run check, not a universal leak proof. No physical input or packaged claim.",
                "cold_visible_art_ready_ms": cold_art_ready_ms,
                "samples": samples,
                "round_process_rss_bytes": round_rss,
                "post_warmup_rss_range_bytes": max(round_rss[1:]) - min(round_rss[1:]),
                "errors": errors,
            },
            indent=2,
        )
        + chr(10)
    )


def test_library_continuous_media_and_groups_keep_bounded_decoded_views(
    application, tmp_path, monkeypatch
):
    from PIL import Image

    app = application
    errors = []
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    app.geometry("1414x900")
    app._select_focus_view("library")
    view = app.library_scene
    image = tmp_path / "library-art.jpg"
    Image.new("RGB", (640, 360), "#345f78").save(image)
    monkeypatch.setattr(view, "_artwork_source_path", lambda *_args: image)
    records = tuple(
        {
            "id": str(index),
            "title": f"Saved video {index}",
            "channel": f"Creator {index}",
            "channel_id": f"creator-{index}",
            "playlist_id": f"playlist-{index // 3}",
            "playlist_title": f"Playlist {index // 3}",
            "vodforge_user_category": f"Collection {index // 5}",
            "vodforge_output_dir": str(tmp_path),
            "vodforge_output_path": str(tmp_path / f"media-{index}.mp4"),
        }
        for index in range(2000)
    )
    view.set_records(records)

    def ready():
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            app.update()
            wanted = view._artwork_wanted
            if (
                view._render_after is None
                and not view._artwork_owner.busy
                and wanted
                and all(key in view._artwork_images for key in wanted)
            ):
                return
            time.sleep(0.005)
        raise AssertionError("Library visible artwork did not settle")

    samples = []
    for route in ("all", "channels", "playlists", "collections"):
        view.navigate(route)
        ready()
        for fraction in (0, 0.5, 1, 0.5, 0):
            view.canvas.yview_moveto(fraction)
            app.update()
            top = view.canvas.canvasy(0)
            ready()
            assert abs(view.canvas.canvasy(0) - top) <= 1
            items, kind, columns, stride, origin, span, _route = view._catalog_window
            assert view._rendered_count <= 40
            assert len(view._artwork_images) <= 64
            assert len(view.canvas.find_all()) < 800
            viewport_top = view.canvas.canvasy(0)
            viewport_bottom = viewport_top + view.canvas.winfo_height()
            card_width = (
                max(360, view.canvas.winfo_width() - 4) - 14 * (columns - 1)
            ) // columns
            expected_art = 0
            for index in range(span[0] * columns, min(len(items), span[1] * columns)):
                row_y = origin + index // columns * stride
                # Channel cards intentionally have one centered 96px avatar,
                # not the retired banner-plus-avatar composition.
                intervals = (
                    [(row_y + 14, row_y + 110)]
                    if kind == "channels"
                    else [
                        (
                            row_y,
                            row_y + (card_width * 9 // 16 if kind == "media" else 125),
                        )
                    ]
                )
                expected_art += sum(
                    bottom > viewport_top and top < viewport_bottom
                    for top, bottom in intervals
                )
            visible_art = sum(
                bool(
                    (bounds := view.canvas.bbox(item))
                    and bounds[3] > viewport_top
                    and bounds[1] < viewport_bottom
                )
                for item in view.canvas.find_withtag("presentation-artwork")
            )
            assert visible_art == expected_art, (
                route,
                fraction,
                visible_art,
                expected_art,
            )
            if fraction == 0:
                assert span[0] == 0
            if fraction == 1:
                assert span[1] * columns >= len(items)
            samples.append(
                {
                    "route": route,
                    "fraction": fraction,
                    "matching": len(items),
                    "rendered": view._rendered_count,
                    "canvas_items": len(view.canvas.find_all()),
                    "decoded_images": len(view._artwork_images),
                }
            )
    view.navigate("all")
    ready()
    view.canvas.yview_scroll(1, "pages")
    ready()
    expected_page_top = view.canvas.canvasy(0)
    view.canvas.yview_moveto(0)
    ready()
    view.canvas.focus_force()
    app.update()
    view.canvas.event_generate("<Next>")
    ready()
    assert abs(view.canvas.canvasy(0) - expected_page_top) <= 1
    view.canvas.event_generate("<Prior>")
    ready()
    assert view.canvas.yview()[0] == 0
    view.canvas.yview_moveto(0.5)
    ready()
    view._remember_catalog_anchor()
    anchor = view._catalog_anchor
    assert anchor
    columns = view._catalog_window[2]
    additions = tuple(
        {
            **records[0],
            "id": str(3000 + i),
            "vodforge_output_path": str(tmp_path / f"added-{i}.mp4"),
        }
        for i in range(columns)
    )
    view.set_records(additions + records)
    ready()
    view._remember_catalog_anchor()
    assert view._catalog_anchor[1] == anchor[1]
    view.set_records(records)
    ready()
    view._remember_catalog_anchor()
    assert view._catalog_anchor[1] == anchor[1]
    view.set_query("Saved")
    ready()
    assert view.canvas.yview()[0] == 0, "A new search starts at its first result"
    assert not errors, errors
    destination = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "library-continuous-traversal.json").write_text(
        json.dumps(
            {
                "scope": "Native Library media/channel/playlist/collection first-middle-end-back traversal with generated decoded JPEG; bounded finite run, no physical input or installed claim.",
                "samples": samples,
                "errors": errors,
            },
            indent=2,
        )
        + chr(10)
    )


def test_watch_horizontal_rows_all_items_keys_retirement_and_nested_scroll(
    application, tmp_path
):
    from PIL import Image

    app = application
    app.geometry("1414x900")
    app._select_focus_view("watch")
    view = app.focus_watch
    art = tmp_path / "rail.jpg"
    Image.new("RGB", (640, 360), "#386d91").save(art)
    view._artwork_source_path = lambda _record, *_args: art
    records = tuple(
        {
            "id": f"rail-{i}",
            "title": f"Saved {i:03}",
            "channel": f"Creator {i:03}",
            "channel_id": f"channel-{i}",
            "playlist_id": f"playlist-{i}",
            "playlist_title": f"Playlist {i:03}",
            "vodforge_user_category": f"Collection {i:03}",
            "vodforge_output_dir": str(tmp_path),
            "vodforge_output_path": str(tmp_path / f"item-{i}.mp4"),
        }
        for i in range(240)
    )
    view.set_records(records)
    view.show_home()

    def ready():
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            app.update()
            if (
                view._render_after is None
                and not view._artwork_owner.busy
                and all(key in view._artwork_images for key in view._artwork_wanted)
            ):
                return
            time.sleep(0.005)
        raise AssertionError(
            (
                "Watch horizontal row did not settle",
                {
                    key: (
                        rail._span,
                        rail._visible_span(),
                        rail._active,
                        rail.visible(),
                        rail.canvas.winfo_width(),
                        rail.canvas.xview(),
                        rail._y,
                    )
                    for key, rail in view._scene_rails.items()
                },
                view._render_after,
                view._artwork_owner.busy,
            )
        )

    ready()
    strips = view._scene_rails
    assert list(strips) == ["recent", "collections", "playlists", "channels"]
    assert strips["recent"]._y < strips["collections"]._y < strips["playlists"]._y
    observed = []
    for name in tuple(strips):
        rail = strips[name]
        region = tuple(map(float, view.canvas.cget("scrollregion").split()))
        view.canvas.yview_moveto(rail._y / region[3])
        ready()
        assert rail._active
        seen = set()
        for fraction in (0, 0.25, 0.5, 0.75, 1, 0.5, 0):
            rail.canvas.xview_moveto(fraction)
            ready()
            seen.update(rail._item_targets)
            assert len(rail._item_targets) <= 9
            assert len(rail.canvas.find_all()) < 250
            assert len(rail._images) <= 9
            if fraction == 1:
                assert len(rail._items) - 1 in rail._item_targets
            if fraction == 0:
                assert 0 in rail._item_targets
            observed.append(
                {
                    "rail": name,
                    "fraction": fraction,
                    "rendered": len(rail._item_targets),
                    "canvas_items": len(rail.canvas.find_all()),
                }
            )
        rail.canvas.xview_moveto(0.5)
        ready()
        anchor = rail._items[int(rail.canvas.canvasx(0) // rail._stride)].key
        app.geometry("1180x900")
        ready()
        assert rail._items[int(rail.canvas.canvasx(0) // rail._stride)].key == anchor
        app.geometry("1414x900")
        ready()
        rail.canvas.xview_moveto(0)
        ready()
        # Shared precise-axis owner: horizontal moves this row, vertical moves outer scene.
        rail._scroll_binding.scroll(60, 0)
        app.update()
        assert rail.canvas.xview()[0] > 0
        ready()
        rail.canvas.focus_force()
        rail.canvas.event_generate("<End>")
        ready()
        assert rail._focus_index == len(rail._items) - 1
        assert rail._focused() is not None
        rail.canvas.event_generate("<Home>")
        ready()
        assert rail._focus_index == 0
        if name == "recent":
            actions = []
            original = view._on_play
            view._on_play = actions.append
            rail._on_play = actions.append
            view._render()
            ready()
            rail.canvas.event_generate("<Return>")
            ready()
            assert actions == [0]
            view._on_play = original
        before = view.canvas.yview()[0]
        rail._scroll_binding.scroll(0, -60)
        app.update()
        assert view.canvas.yview()[0] < before
        ready()
    # Each row has an independent viewport even when a video appears in several.
    view.show_home()
    ready()
    recent, collections = view._scene_rails["recent"], view._scene_rails["collections"]
    recent.canvas.xview_moveto(0.25)
    ready()
    assert recent.canvas.xview()[0] > 0.20
    assert collections.canvas.xview()[0] == 0
    # A record replacement must retire all live actions synchronously.
    view.set_records(records[1:])
    assert all(not rail._targets for rail in view._scene_rails.values())
    ready()
    assert all(
        record["id"] != "rail-0"
        for rail in view._scene_rails.values()
        for record in rail._records
    )
    retired = tuple(view._scene_rails.values())
    view._scene_open("videos")
    assert all(not rail._targets for rail in retired)
    ready()
    assert not view._scene_rails
    assert all(rail._closed for rail in retired)
    # Group views no longer have a final inaccessible page or unbounded live cards.
    for route in ("channels", "playlists", "collections"):
        view._scene_open(route)
        ready()
        view.canvas.yview_moveto(1)
        ready()
        _count, columns, _stride, _y, span, groups = view._scene_window
        assert span[1] * columns >= len(groups) == len(view._records)
        assert len(view.canvas.find_all()) < 800
    output = Path(os.environ.get("VODFORGE_NATIVE_ARTIFACTS", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / "watch-horizontal-rows.json").write_text(
        json.dumps(observed, indent=2) + "\n"
    )


def test_library_projection_and_warm_drawing_costs_are_separate(application, tmp_path):
    app = application
    app.geometry("1414x900")
    app._select_focus_view("library")
    view = app.library_scene
    samples = []
    for count in (5000, 20000):
        records = tuple(
            {
                "id": str(i),
                "title": f"Saved {i:05}",
                "channel": f"Creator {i // 200}",
                "playlist_id": f"list-{i // 20}",
                "playlist_title": f"Playlist {i // 20}",
                "vodforge_output_dir": str(tmp_path),
                "vodforge_output_path": str(tmp_path / f"item-{i}.mp4"),
            }
            for i in range(count)
        )
        start = time.perf_counter()
        view.set_records(records)
        projection_ms = (time.perf_counter() - start) * 1000
        view.navigate("all")
        view._render()
        app.update_idletasks()
        cold_ms = (time.perf_counter() - start) * 1000
        draws = []
        for fraction in (0, 0.5, 1, 0):
            view.canvas.yview_moveto(fraction)
            start = time.perf_counter()
            view._render()
            app.update_idletasks()
            draws.append((time.perf_counter() - start) * 1000)
            assert len(view.canvas.find_all()) < 800
            assert view._rendered_count <= 40
        samples.append(
            {
                "records": count,
                "set_records_ms": projection_ms,
                "cold_sync_layout_ms": cold_ms,
                "warm_draw_ms": draws,
            }
        )
    output = Path(os.environ.get("VODFORGE_NATIVE_ARTIFACTS", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / "library-scale-costs.json").write_text(
        json.dumps(samples, indent=2) + "\n"
    )


def test_watch_row_replacement_during_decode_rejects_retired_actions(
    application, tmp_path
):
    from threading import Event

    from PIL import Image

    app = application
    app.geometry("1414x900")
    app._select_focus_view("watch")
    view = app.focus_watch
    art = tmp_path / "delayed.jpg"
    Image.new("RGB", (640, 360), "#537c94").save(art)
    entered, release = Event(), Event()

    def source(_record, *_args):
        entered.set()
        release.wait(3)
        return art

    view._artwork_source_path = source
    rows = tuple(
        {
            "id": str(i),
            "title": f"Before {i}",
            "vodforge_output_dir": str(tmp_path),
            "vodforge_output_path": str(tmp_path / f"{i}.mp4"),
            "vodforge_user_category": "Shared",
            "playlist_id": "same",
            "playlist_title": "Shared playlist",
            "channel": "Shared channel",
        }
        for i in range(8)
    )
    view.set_records(rows)
    view.show_home()
    deadline = time.monotonic() + 3
    while not entered.is_set() and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert entered.is_set()
    stale = tuple(view._scene_rails.values())
    changed = tuple({**row, "title": "After " + row["id"]} for row in rows[1:])
    view.set_records(changed)
    assert all(not rail._targets and not rail._records for rail in stale)
    release.set()
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        app.update()
        if view._render_after is None and not view._artwork_owner.busy:
            break
        time.sleep(0.01)
    assert all(
        row["title"].startswith("After")
        for rail in view._scene_rails.values()
        for row in rail._records
    )
    played, details = [], []
    recent = view._scene_rails["recent"]
    view._on_play, view._on_details = played.append, details.append
    view._render()
    app.update()
    recent.canvas.focus_force()
    recent.canvas.event_generate("<Home>")
    recent.canvas.event_generate("<Return>")
    assert played == [0] and changed[played[0]]["id"] == "1"
    recent.canvas.event_generate("<Down>")
    recent.canvas.event_generate("<Return>")
    assert details == [0]
    # Empty/singleton states retire the old rows, without duplicate featured media.
    view.set_records(changed[:1])
    view._render()
    app.update()
    assert set(view._scene_rails) == {"collections"}
    assert not recent.winfo_exists()
    collection = view._scene_rails["collections"]
    assert len(collection._items) == 1
    assert len(collection._items[0].videos) == 1
    assert collection._items[0].videos[0].indices == (0,)
    assert collection._records[0]["id"] == "1"
    opened = []
    view._scene_open = lambda route, **kwargs: opened.append((route, kwargs))
    view._render()
    collection.canvas.yview_moveto(0)
    collection._focus_index = 0
    # Reveal this below-fold section before dispatching its current target.
    view.canvas.yview_moveto(
        collection._y / float(view.canvas.cget("scrollregion").split()[3])
    )
    app.update()
    view._render()
    collection = view._scene_rails["collections"]
    collection._activate()
    assert opened == [("playlist", {"playlist": collection._items[0].key})]
    view.set_records(())
    view._render()
    app.update()
    assert not view._scene_rails


def test_channel_see_all_keeps_membership_and_returns_to_its_origin(
    application, tmp_path
):
    from tests.test_archive_native import pump, seed

    app = application
    seed(app, tmp_path, count=17)
    app.geometry("1414x900")
    app._select_focus_view("watch")
    view = app.focus_watch
    view._navigate("channels")
    pump(app)
    channel_action = next(
        action
        for _box, action in view._targets
        if getattr(getattr(action, "func", None), "__name__", "") == "_navigate"
        and len(getattr(action, "args", ())) == 2
    )
    channel_action()
    pump(app)
    channel = view._channel
    assert channel
    see_all = next(
        action
        for _box, action in view._targets
        if getattr(getattr(action, "func", None), "__name__", "") == "_scene_open"
        and getattr(action, "args", ()) == ("playlists",)
    )
    see_all()
    pump(app)
    assert view._scene_route == "playlists" and view._channel == channel
    assert view._scene_window and view._scene_window[0] == 2
    back = next(
        (
            box
            for box, item, _color, _enabled in view._button_labels
            if view.canvas.itemcget(item, "text") == "Back to channel"
        ),
        None,
    )
    assert back is not None, (
        "See All must expose a return to the channel which opened it"
    )
    next(action for box, action in view._targets if box == back)()
    pump(app)
    assert view._scene_route == "channel" and view._channel == channel
