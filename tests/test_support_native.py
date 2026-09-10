"""Native popup journey contracts, no network or user profile access."""

import os
import time
import tkinter as tk

import pytest

from yt_downloader.engagement_state import WELCOME_SLIDES
from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.support_ui import SupportPanel
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.whats_new_ui import WhatsNewPanel

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="requires native Tcl/Tk"
)


@pytest.fixture
def root():
    app = tk.Tk()
    app.geometry("1000x700")
    apply_product_styles(app)
    app.update()
    yield app
    app.destroy()


@pytest.mark.parametrize("size", ["1000x700", "620x560"])
def test_playlist_welcome_example_is_off_and_centered(root, size):
    from yt_downloader.whats_new import NativePreview

    assert WELCOME_SLIDES[4].key == "playlists"
    assert WELCOME_SLIDES[5].key == "youtube-access"
    assert WELCOME_SLIDES[4].preview is NativePreview.PLAYLISTS
    root.geometry(size)
    panel = WhatsNewPanel(
        root, WELCOME_SLIDES, lambda: None, finish_label="Start using VODForge"
    )
    panel.render(4)
    root.update()
    panel._cancel_transition()
    panel._transition(10)
    root.update()
    demo = panel.activity_demo
    assert demo.variables[0].get() is False
    assert (
        abs(demo.winfo_x() + demo.winfo_width() / 2 - panel.preview.winfo_width() / 2)
        <= 1
    )
    assert (
        abs(demo.winfo_y() + demo.winfo_height() / 2 - panel.preview.winfo_height() / 2)
        <= 1
    )
    panel.close()


@pytest.mark.parametrize("size", ["1000x700", "620x560"])
def test_access_tour_uses_browser_example_and_centered_controls(root, size):
    from yt_downloader.ui_widgets import ChoiceDropdown
    from yt_downloader.youtube_access import (
        COOKIE_BROWSER_OPTIONS,
        COOKIE_SOURCE_OPTIONS,
    )

    assert COOKIE_SOURCE_OPTIONS == ("Public", "Browser", "cookies.txt")
    root.geometry(size)
    panel = WhatsNewPanel(
        root, WELCOME_SLIDES, lambda: None, finish_label="Start using VODForge"
    )
    index = next(
        i for i, slide in enumerate(WELCOME_SLIDES) if slide.key == "youtube-access"
    )
    panel.render(index)
    root.update()
    panel._cancel_transition()
    panel._transition(10)
    root.update()
    demo = panel.activity_demo
    assert demo.variables[0].get() == "Browser"
    assert demo.variables[1].get() == "Chrome"
    dropdown = next(
        child for child in demo.winfo_children() if isinstance(child, ChoiceDropdown)
    )
    assert tuple(dropdown.cget("values")) == tuple(COOKIE_BROWSER_OPTIONS)
    assert (
        abs(demo.winfo_x() + demo.winfo_width() / 2 - panel.preview.winfo_width() / 2)
        <= 1
    )
    assert (
        dropdown.winfo_rooty() + dropdown.winfo_height()
        <= demo.winfo_rooty() + demo.winfo_height()
    )
    assert (
        panel.finish_button.winfo_rooty() + panel.finish_button.winfo_height()
        <= root.winfo_rooty() + root.winfo_height()
    )
    panel.close()


@pytest.mark.parametrize("kind", ["feedback", "review"])
@pytest.mark.parametrize("size", ["1000x700", "760x600"])
def test_forms_footer_consent_limits_and_dismissal(root, kind, size):
    root.geometry(size)
    root.update()
    panel = SupportPanel(
        root,
        kind=kind,
        transport=None,
        closed=lambda: None,
        context=FailureContext(
            "HTTP Error 403", "https://www.youtube.com/watch?v=8mv2Gonsdog"
        ),
    )
    root.update()
    panel.message.insert("1.0", "hello")
    if kind == "feedback":
        assert panel.reason.get() == "Select one…"
        with pytest.raises(ValueError, match="select a reason"):
            panel.payload()
        panel.reason.set("Download problem")
        assert panel.payload()["diagnostics"] == ""
        assert panel.payload()["video_url"] == ""
        panel.diagnostics.set(True)
        assert panel.payload()["diagnostics"] == "HTTP Error 403"
        assert panel.payload()["video_url"] == ""
        panel.reply.set(True)
        panel._reply_changed()
        root.update()
    else:
        panel.star_buttons[0].invoke()
        assert panel.payload()["stars"] == 1
        assert panel.payload()["display_name"] == "Anonymous"
        assert panel.payload()["publication_consent"] is True
        assert panel.send.cget("text") == "Submit public review"
        assert not hasattr(panel, "publish")
    root.update()
    assert panel.frame.winfo_height() <= (510 if kind == "feedback" else 480)
    bottom = panel.frame.winfo_rooty() + panel.frame.winfo_height()
    assert panel.backdrop.last == (
        root.winfo_width(),
        root.winfo_height(),
        panel.frame.winfo_x(),
        panel.frame.winfo_y(),
        panel.frame.winfo_width(),
        panel.frame.winfo_height(),
    )
    assert panel.send.winfo_rooty() + panel.send.winfo_height() < bottom
    assert panel.message.winfo_height() > 25
    assert panel.cancel.winfo_viewable()
    panel.close()
    assert root.grab_current() is None
    assert not panel.frame.winfo_exists()


def test_welcome_all_slides_native_and_finish(root):
    dismissed = []
    panel = WhatsNewPanel(
        root,
        WELCOME_SLIDES,
        lambda: dismissed.append(True),
        heading="Welcome to VODForge",
        finish_label="Start using VODForge",
    )
    from yt_downloader.ui_theme import THEME

    forge = next(
        label for label in panel.heading_labels if label.cget("text") == "Forge"
    )
    assert str(forge.cget("foreground")) == THEME["text"]
    for index in range(len(WELCOME_SLIDES)):
        panel.render(index)
        root.update()
        assert panel.activity_demo is not None
        if index == 2:
            demo = panel.activity_demo
            demo.panel.toggle._choose(True)
            assert demo.panel.toggle.technical is True
            assert demo.interval_ms == 200
            demo._cancel()
            demo.step = 12
            demo._tick()
            assert demo.panel.toggle.technical is False
            demo._cancel()
            demo.step = 6
            demo._tick()
            assert demo.panel.toggle.technical is True
    root.update()
    assert panel.finish_button.winfo_viewable()
    panel.finish_button.invoke()
    assert dismissed == [True]
    assert root.grab_current() is None


def test_feedback_dropdown_belongs_to_modal_grab(root):
    from yt_downloader.ui_widgets import ChoiceDropdown

    panel = SupportPanel(root, kind="feedback", transport=None, closed=lambda: None)
    root.update()
    field = next(
        w for w in panel.surface.body.winfo_children() if isinstance(w, ChoiceDropdown)
    )
    field.open_popover()
    root.update()
    popup = field._popover
    assert popup is not None
    assert popup.master is root.grab_current() is panel.frame
    menu = popup.winfo_children()[0]
    menu.selection_set(1)
    menu.event_generate("<ButtonRelease-1>")
    root.update()
    assert panel.reason.get() == "Playback problem"
    assert field._popover is None
    assert root.grab_current() is panel.frame
    panel.close()


@pytest.mark.parametrize("size", ["1000x700", "620x560"])
def test_welcome_content_and_navigation_centered(root, size):
    root.geometry(size)
    root.update()
    panel = WhatsNewPanel(
        root, WELCOME_SLIDES, lambda: None, finish_label="Start using VODForge"
    )
    for index in (0, 2):
        panel.render(index)
        root.update()
        panel._cancel_transition()
        panel._transition(10)
        root.update()
        demo = panel.activity_demo
        assert demo is not None
        assert demo.winfo_width() <= 300
        assert (
            abs(
                demo.winfo_x()
                + demo.winfo_width() / 2
                - panel.preview.winfo_width() / 2
            )
            <= 1
        )
        assert (
            abs(
                demo.winfo_y()
                + demo.winfo_height() / 2
                - panel.preview.winfo_height() / 2
            )
            <= 1
        )
        arrows_center = (
            panel.back.winfo_rootx()
            + panel.next.winfo_rootx()
            + panel.next.winfo_width()
        ) / 2
        assert (
            abs(
                arrows_center
                - (panel.frame.winfo_rootx() + panel.frame.winfo_width() / 2)
            )
            <= 2
        )
        assert isinstance(panel.skip_button, tk.Label)
        assert (
            panel.skip_button.winfo_rootx()
            > panel.next.winfo_rootx() + panel.next.winfo_width()
        )
    panel.render(len(WELCOME_SLIDES) - 1)
    root.update()
    assert (
        abs(
            panel.finish_button.winfo_rootx()
            + panel.finish_button.winfo_width() / 2
            - (panel.frame.winfo_rootx() + panel.frame.winfo_width() / 2)
        )
        <= 2
    )
    assert panel.back.winfo_viewable()
    panel.render(2)
    root.update()
    assert not panel.finish_balance.winfo_ismapped()
    panel.skip_button.event_generate("<Button-1>")
    root.update()
    assert panel.closed


def test_submission_freezes_consent_preserves_failure_and_confirms_receipt(root):
    from yt_downloader.support_transport import SubmissionError

    class Transport:
        def __init__(self):
            self.calls = []

        def submit(self, kind, payload, request_id):
            self.calls.append((kind, payload, request_id))
            if len(self.calls) == 1:
                raise SubmissionError("Unavailable")
            return request_id

    transport = Transport()
    panel = SupportPanel(
        root, kind="feedback", transport=transport, closed=lambda: None
    )
    panel.message.insert("1.0", "Reproduction steps")
    panel.reason.set("Other")
    for expected in (False, True):
        panel._submit()
        assert panel.message.cget("state") == "disabled"
        deadline = time.monotonic() + 3
        while panel.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert not panel.busy
        assert panel.sent is expected
        assert panel.message.get("1.0", "end-1c") == "Reproduction steps"
    assert transport.calls[0][2] == transport.calls[1][2]
    panel.close()


def test_automatic_prompts_wait_for_consent_and_secondary_windows(root, tmp_path):
    from yt_downloader.engagement_ui import EngagementUI

    ready = [False]
    owner = EngagementUI(
        root,
        tmp_path / "installation.json",
        ready=lambda: ready[0],
        suppress_showcase=lambda: None,
    )
    root.focus_force()
    root.update()
    owner._poll()
    assert owner.panel is None
    ready[0] = True
    dialog = tk.Toplevel(root)
    root.update()
    owner._poll()
    assert owner.panel is None
    dialog.destroy()
    root.focus_force()
    root.update()
    owner._poll()
    assert isinstance(owner.panel, WhatsNewPanel)
    owner.panel.close()
    owner._poll()
    assert owner.panel is None
    owner.close()
