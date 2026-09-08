"""Explicit preview-only observation of the real application startup journey.

No transport or consent decisions are replaced. Automated choices invoke the
same visible buttons as a user. Receipts live only in the isolated QA profile.
"""

from __future__ import annotations

import json
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path

from .telemetry_policy import preview_telemetry_allowed


def observe_startup(app: tk.Tk, arguments: list[str]) -> None:
    if not preview_telemetry_allowed():
        raise ValueError("Startup observation requires an isolated preview artifact")
    if len(arguments) != 3 or arguments[0] not in {"allow", "deny", "none"}:
        raise ValueError("Expected choice, choice delay, and duration")
    choice, delay, duration = arguments[0], float(arguments[1]), float(arguments[2])
    if not 0 <= delay <= 180 or not 1 <= duration <= 240:
        raise ValueError("Observation duration is out of bounds")
    from .history import application_data_dir

    receipt = Path(application_data_dir()) / "startup-journey.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    events: list[dict[str, object]] = []
    original_open = webbrowser.open
    chosen = False
    prompt_seen = False
    lock = threading.Lock()

    def record(kind: str, **values: object) -> None:
        with lock:
            events.append(
                {
                    "kind": kind,
                    "seconds": round(time.monotonic() - started, 3),
                    **values,
                }
            )
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"provider": "excluded", "events": events}, indent=2)
            )
            temporary.replace(receipt)

    def opened(url: str, new: int = 0, autoraise: bool = True) -> bool:
        record("browser_requested", url=url, autoraise=autoraise)
        result = original_open(url, new=new, autoraise=autoraise)
        record("browser_adapter_returned", result=result)
        return result

    def descendants(widget: tk.Misc):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    def poll() -> None:
        nonlocal chosen, prompt_seen
        elapsed = time.monotonic() - started
        for widget in descendants(app):
            if "text" not in widget.keys():  # noqa: SIM118 - Tk widget is not a mapping
                continue
            label = str(widget.cget("text"))
            if (
                label == "Share analytics"
                and widget.winfo_ismapped()
                and not prompt_seen
            ):
                prompt_seen = True
                record("permission_prompt_visible")
                panel = app.analytics_startup.permission_panel
                record(
                    "permission_surface",
                    native_backdrop_bands=len(panel.backdrop.views),
                    centered=(
                        abs(
                            panel.frame.winfo_x()
                            + panel.frame.winfo_width() / 2
                            - app.winfo_width() / 2
                        )
                        <= 2
                        and abs(
                            panel.frame.winfo_y()
                            + panel.frame.winfo_height() / 2
                            - app.winfo_height() / 2
                        )
                        <= 2
                    ),
                )
                app.after(
                    1200,
                    lambda: record(
                        "permission_focus_observed",
                        focused=app.focus_displayof() is not None,
                        requested=app.analytics_startup.consent_focus_requested,
                    ),
                )
            target = "Share analytics" if choice == "allow" else "Not now"
            if (
                choice != "none"
                and not chosen
                and elapsed >= delay
                and label == target
                and widget.winfo_ismapped()
            ):
                chosen = True
                record("permission_choice", choice=choice)
                widget.invoke()
                break
        if elapsed >= duration:
            record(
                "observation_finished", prompt_seen=prompt_seen, choice_invoked=chosen
            )
            webbrowser.open = original_open
            app.event_generate("<<QAObservationFinished>>", when="tail")
        else:
            app.after(50, poll)

    webbrowser.open = opened
    record("app_constructed")
    app.after(50, poll)
