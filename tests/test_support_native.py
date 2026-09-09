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
        assert panel.payload()["publication_consent"] is False
    root.update()
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
    for index in range(len(WELCOME_SLIDES)):
        panel.render(index)
        root.update()
        assert panel.activity_demo is not None
        if index == 2:
            demo = panel.activity_demo
            demo.toggle._choose(True)
            assert demo.toggle.technical is True
    root.update()
    assert panel.finish_button.winfo_viewable()
    panel.finish_button.invoke()
    assert dismissed == [True]
    assert root.grab_current() is None


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
