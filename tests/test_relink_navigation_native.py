"""Relink navigation preserves real worker and durable-result ownership."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Event

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from yt_downloader import archive_library_ui
from yt_downloader.history import load_history, save_history
from yt_downloader.platform_services import capture_own_widget

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def wait_for(app, predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        pump(app, 0.02)
    assert predicate()


@pytest.mark.parametrize("destination", ["watch", "library", "escape"])
@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
def test_tab_navigation_preserves_relink_settlement(
    application, tmp_path, monkeypatch, destination, boundary
):
    app = application
    seed(app, tmp_path, 1)
    app.history_path = tmp_path / "history.json"
    save_history(app.history_path, app.download_history)
    # Start from the same sanitized records used at application startup; seed()
    # includes legacy/unsaved fixture fields and omits the durable timestamp.
    app.download_history = load_history(app.history_path)
    save_history(app.history_path, app.download_history)
    app._reconcile_library_projection()
    pump(app)
    original_history = json.loads(json.dumps(app.download_history))
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"nonempty test artifact; existence check only")
    entered, release = Event(), Event()
    commit = archive_library_ui.commit_relink

    def gated(*args, **kwargs):
        if boundary == "before_commit":
            entered.set()
            assert release.wait(5)
            return commit(*args, **kwargs)
        result = commit(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(archive_library_ui, "commit_relink", gated)
    app._archive_begin_relink(None, (0,), exact=str(replacement))
    panel = app._archive_overlay

    def ready_button():
        return next(
            (
                w
                for w in descendants(panel)
                if w.winfo_class() == "TButton"
                and str(w.cget("text")) == "Update location"
                and "disabled" not in w.state()
            ),
            None,
        )

    wait_for(app, ready_button)
    output = (
        Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        / f"{boundary}-{destination}"
    )
    output.mkdir(parents=True, exist_ok=True)

    def capture(phase):
        image = capture_own_widget(app)
        assert image is not None
        image.save(output / f"{phase}.png")

    capture("before")
    ready_button().invoke()
    try:
        wait_for(app, entered.is_set)
        callback = app._archive_callback
        if destination == "escape":
            document = next(w for w in descendants(panel) if w.winfo_class() == "Text")
            document.focus_force()
            pump(app, 0.02)
            document.event_generate("<Escape>")
        else:
            app._focus_nav_buttons[destination].invoke()
        pump(app, 0.06)
        assert app._archive_callback is callback, (
            "Navigation discarded the pending commit result"
        )
        assert app._archive_overlay is panel
        assert app._archive_commit_active
        assert app._archive_commit_cancel_reason == "cancel"
        capture("during")
        assert app._focus_selected_view == "library"
    finally:
        release.set()
        # Preserve cleanup even against the defective source.
        wait_for(app, lambda: not app._archive_worker.busy)
        pump(app, 0.15)
        if app._archive_commit_active and app._archive_callback is None:
            app._archive_commit_active = False
    assert not app._archive_commit_active
    durable = load_history(app.history_path)
    assert app.download_history == durable
    if boundary == "before_commit":
        assert durable == original_history
        assert app._archive_overlay is panel
        assert any(
            str(w.cget("text")) == "Back to Library"
            for w in descendants(panel)
            if w.winfo_class() == "TButton"
        )
        app._archive_cancel_relink()
    else:
        assert durable != original_history
        assert app._archive_overlay is None
    target = "library" if destination == "escape" else destination
    app._focus_nav_buttons[target].invoke()
    pump(app)
    assert app._focus_selected_view == target
    capture("after")
    (output / "scope.json").write_text(
        json.dumps(
            {
                "input": "Tk-generated Escape or direct real navigation button invocation; not physical input",
                "boundary": boundary,
                "destination": destination,
                "phases": ["before", "during", "after"],
                "worker": "real ArchiveWorkOwner and atomic history writer with controlled scheduling gate",
                "history_matches_disk": True,
                "limits": "Temporary existence-only media fixture; no playback, physical input, Windows, or packaged claim",
            },
            indent=2,
        )
    )
