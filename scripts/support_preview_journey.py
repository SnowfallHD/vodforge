"""Native forms -> real HTTPS preview Worker -> remote D1, never production.

Run explicitly with --output and --qa-key. Synthetic data only. Human verification
is disabled on this access-key-gated preview; this is not Turnstile/package proof.
"""

import argparse
import itertools
import json
import subprocess
import time
import tkinter as tk
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

from yt_downloader import support_transport
from yt_downloader.support_diagnostics import FailureContext, redact_line
from yt_downloader.support_transport import SubmissionError, SupportTransport
from yt_downloader.support_ui import REASONS, SupportPanel
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_widgets import ChoiceDropdown, ModernCheckbox

ORIGIN = "https://vodforge-preview.little-mountain-f558.workers.dev"
DATABASE = "924640fb-3be3-47ca-992c-1c7745bd8469"
SITE = Path(__file__).resolve().parents[2] / "vodforge-site"


def sql(command):
    result = subprocess.run(
        [
            str(SITE / "node_modules/.bin/wrangler"),
            "d1",
            "execute",
            DATABASE,
            "--remote",
            "--config",
            str(SITE / "wrangler.preview.jsonc"),
            "--command",
            command,
            "--json",
        ],
        cwd=SITE,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)[0]["results"]


def click(root, widget):
    root.update()
    x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
    for event in ("<Enter>", "<ButtonPress-1>", "<ButtonRelease-1>"):
        widget.event_generate(event, x=x, y=y)
        root.update()


def wait(root, panel):
    deadline = time.monotonic() + 40
    while panel.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)
    assert not panel.busy, "Submission timed out"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qa-key", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    key = args.qa_key.read_text().strip()
    assert len(key) >= 32
    request = urllib.request.Request

    class PreviewRequest(request):
        def __init__(self, url, *a, **kw):
            if not url.startswith(ORIGIN + "/api/support/"):
                raise RuntimeError("Refusing non-preview submission")
            kw.setdefault("headers", {})["X-VODForge-QA-Key"] = key
            super().__init__(url, *a, **kw)

    root = tk.Tk()
    root.title("VODForge — isolated support preview journey")
    root.geometry("960x700")
    apply_product_styles(root)
    root.update()
    root.focus_force()
    transports = [SupportTransport(args.output / f"profile-{i}") for i in range(3)]
    evidence = {
        "origin": ORIGIN,
        "database": DATABASE,
        "human_verification": False,
        "packaged_app": False,
        "cases": [],
    }
    receipt_path = args.output / "receipt.json"
    if receipt_path.exists():
        evidence = json.loads(receipt_path.read_text())
        if evidence["origin"] != ORIGIN or evidence["database"] != DATABASE:
            raise RuntimeError("Receipt belongs to another target")
    evidence["passed"] = False
    retained_panels = []  # Keep Tk objects on the UI thread during worker allocation/GC.
    context = FailureContext(
        redact_line("HTTP Error 403 /Users/example/private Authorization: secret"),
        "https://www.youtube.com/watch?v=8mv2Gonsdog",
    )

    def form(kind, transport, ctx=context):
        panel = SupportPanel(
            root, kind=kind, transport=transport, closed=lambda: None, context=ctx
        )
        root.update()
        retained_panels.append(panel)
        return panel

    def submit(panel, label):
        expected = panel.payload()
        click(root, panel.send)
        wait(root, panel)
        assert panel.sent, str(panel.status.cget("text"))
        credential = panel.transport._credential()["credential_id"]
        uuid.UUID(credential)
        uuid.UUID(panel.request_id)
        table = "feedback_submissions" if panel.kind == "feedback" else "app_reviews"
        rows = sql(
            f"SELECT * FROM {table} WHERE credential_id='{credential}' AND request_id='{panel.request_id}'"
        )
        assert len(rows) == 1
        row = rows[0]
        for field, value in expected.items():
            normalized = int(value) if isinstance(value, bool) else value
            if field in {"diagnostics", "video_url", "reply_email"} and not value:
                normalized = None
            assert row[field] == normalized, (label, field, row[field], normalized)
        if panel.kind == "review":
            assert row["moderation_status"] == "pending"
        receipt = panel.transport.submit(panel.kind, expected, panel.request_id)
        assert receipt == panel.request_id
        evidence["cases"].append(
            {"case": label, "request_id": receipt, "row": row, "exact_retry": True}
        )
        print(label + ": native receipt and exact D1 row verified", flush=True)
        panel.close()

    try:
        with (
            patch.object(support_transport, "ENDPOINT", ORIGIN + "/api/support/"),
            patch.object(support_transport.urllib.request, "Request", PreviewRequest),
        ):
            # Every combination of the three independent feedback permissions;
            # all five reasons selected through the real dropdown keyboard binding.
            for i, (reply, diagnostics, video) in enumerate(
                itertools.product((False, True), repeat=3)
            ):
                if any(
                    c["case"].startswith(f"feedback-{i}-") for c in evidence["cases"]
                ):
                    continue
                panel = form("feedback", transports[i // 5])
                root.focus_force()
                root.update()
                dropdown = next(
                    w
                    for w in panel._descendants(panel.frame)
                    if isinstance(w, ChoiceDropdown)
                )
                dropdown.open_popover()
                root.update()
                menu = dropdown._popover.winfo_children()[0]
                menu.focus_force()
                root.update()
                menu.selection_set(i % len(REASONS))
                menu.event_generate("<Return>")
                root.update()
                assert panel.reason.get() == REASONS[i % len(REASONS)]
                for variable, enabled in (
                    (panel.reply, reply),
                    (panel.diagnostics, diagnostics),
                    (panel.video_url, video),
                ):
                    if enabled:
                        checkbox = next(
                            w
                            for w in panel._descendants(panel.frame)
                            if isinstance(w, ModernCheckbox) and w.variable is variable
                        )
                        click(root, checkbox)
                        assert variable.get()
                panel.email.set("preview@example.invalid")
                panel.message.insert(
                    "1.0", "x" * 2000 if i == 7 else f"Synthetic preview feedback {i}"
                )
                submit(
                    panel,
                    f"feedback-{i}-reply{reply}-diagnostics{diagnostics}-url{video}",
                )

            for i, stars in enumerate((5, 3, 1, 4, 2)):
                if any(c["case"] == f"review-{stars}" for c in evidence["cases"]):
                    continue
                panel = form("review", transports[2 if i < 3 else 1])
                click(root, panel.star_buttons[4])
                click(root, panel.star_buttons[stars - 1])
                assert "".join(
                    b.cget("text") for b in panel.star_buttons
                ) == "★" * stars + "☆" * (5 - stars)
                if i in (1, 3, 4):
                    panel.message.insert(
                        "1.0", "c" * 1000 if i == 4 else "Synthetic honest review"
                    )
                if i in (2, 3, 4):
                    panel.name.set("N" * 80 if i == 4 else "Preview Reviewer")
                submit(panel, f"review-{stars}")

            if not any(c["case"] == "feedback-no-context" for c in evidence["cases"]):
                panel = form("feedback", transports[1], None)
                panel.message.insert("1.0", "b" * 2001)
                root.update()
                assert len(panel.message.get("1.0", "end-1c")) == 2000
                panel.reply.set(True)
                panel._reply_changed()
                panel.email.set("invalid-address")
                click(root, panel.send)
                assert not panel.busy and not panel.sent
                panel.email.set("preview@example.invalid")
                submit(panel, "feedback-no-context")

            if not any(c["case"] == "lost-response-retry" for c in evidence["cases"]):

                class LostResponse(SupportTransport):
                    dropped = False

                    def _post(self, action, body, credential):
                        result = super()._post(action, body, credential)
                        if action == "feedback" and not self.dropped:
                            self.dropped = True
                            raise SubmissionError(
                                "Injected response loss after real server commit"
                            )
                        return result

                transport = LostResponse(args.output / "profile-1")
                panel = form("feedback", transport)
                panel.message.insert("1.0", "Synthetic lost-response retry")
                request_id = panel.request_id
                click(root, panel.send)
                wait(root, panel)
                assert (
                    not panel.sent
                    and panel.message.get("1.0", "end-1c")
                    == "Synthetic lost-response retry"
                )
                assert panel.request_id == request_id
                submit(panel, "lost-response-retry")
                assert panel.request_id == request_id

            # No diagnostics context; cancelled and invalid forms must not create credentials.
            unused = SupportTransport(args.output / "unsent-profile")
            panel = form("feedback", unused, None)
            click(root, panel.send)
            assert not panel.busy and not unused.path.exists()
            panel.close()
            panel = form("review", unused)
            click(root, panel.send)
            assert not panel.busy and not unused.path.exists()
            click(root, panel.star_buttons[0])
            panel.name.set("N" * 81)
            panel.message.insert("1.0", "c" * 1001)
            root.update()
            assert len(panel.message.get("1.0", "end-1c")) == 1000
            click(root, panel.send)
            assert not panel.busy and not unused.path.exists()
            panel.close()
            evidence["cases"].append(
                {"case": "empty-feedback-unrated-review-cancel", "no_credentials": True}
            )

            # Real exhausted per-credential quotas preserve the form and do not report success.
            for kind, transport in (
                ("feedback", transports[0]),
                ("review", transports[2]),
            ):
                panel = form(kind, transport)
                panel.message.insert("1.0", "Synthetic over-quota submission")
                if kind == "review":
                    click(root, panel.star_buttons[0])
                click(root, panel.send)
                wait(root, panel)
                assert (
                    not panel.sent
                    and panel.message.get("1.0", "end-1c")
                    == "Synthetic over-quota submission"
                )
                assert transport.retry_after > time.monotonic()
                evidence["cases"].append({"case": kind + "-quota", "preserved": True})
                panel.close()

            ids = [t._credential()["credential_id"] for t in transports]
            quoted = ",".join("'" + str(uuid.UUID(i)) + "'" for i in ids)
            assert (
                sql(
                    f"SELECT count(*) n FROM telemetry_clients WHERE credential_id IN ({quoted})"
                )[0]["n"]
                == 0
            )
            evidence["telemetry_clients_created"] = 0
            evidence["passed"] = True
    finally:
        (args.output / "receipt.json").write_text(json.dumps(evidence, indent=2))
        root.destroy()


if __name__ == "__main__":
    main()
