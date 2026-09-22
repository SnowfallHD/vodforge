"""Native Tk layout/edit/copy checks; generated Tk keys, not physical input."""

from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path

import pytest

from yt_downloader.ui_editable_text import EditableTextSection
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_widgets import ActionDialogSurface, KeyboardScope

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native display required",
)


def test_inline_description_full_copy_bounded_height_and_scoped_cancel(tmp_path):
    root = tk.Tk()
    root.geometry("560x420+260+120")
    apply_product_styles(root)
    calls, parent_keys, errors = [], [], []
    root.report_callback_exception = lambda *args: errors.append(str(args[1]))
    KeyboardScope(root, {"<Escape>": lambda: parent_keys.append("escape")})
    surface = ActionDialogSurface(root, allow_body_scroll=True, padx=8, pady=8)
    section = EditableTextSection(
        surface.body,
        title="Description",
        save=lambda owner, value: calls.append((owner, value)) or True,
        changed=lambda: None,
    )
    section.pack(fill="x")
    tk.Frame(surface.body, height=600).pack(fill="x")
    source = "Source paragraph with the full description.\n" * 400
    try:
        section.present("owner-a", source, "Source description")
        assert section.text.bind("<MouseWheel>")
        binding = section.text._vodforge_scroll_binding
        assert (
            section.text in binding._targets and section.scrollbar in binding._targets
        )
        root.update()
        assert section._copy_icon is not None
        assert str(section.copy_button["text"]) == ""
        assert section.copy_button.winfo_width() >= section._copy_icon.width()
        assert (
            len(
                [
                    1
                    for widget, key, _ in binding._bindings
                    if widget is section.text and key == "<MouseWheel>"
                ]
            )
            == 1
        )
        for editing in (False, True):
            if editing:
                section.begin()
            for target in (section.text, section.scrollbar):
                section.text.yview_moveto(0.4)
                root.update()
                before = section.text.yview()[0]
                parent_before = surface.viewport.yview()
                target.event_generate("<MouseWheel>", delta=-12)
                root.update()
                assert section.text.yview()[0] > before
                assert surface.viewport.yview() == parent_before
            if editing:
                section.cancel()
        assert section.height_for_width(400) < 300
        assert section.text.get("1.0", "end-1c") == source
        section.copy()
        assert root.clipboard_get() == source
        section.text.yview_moveto(1)
        root.update()
        section.text.see("end-1c")
        root.update()
        # Programmatic final-line reachability is separate from wheel movement above.
        line = section.text.dlineinfo("end-2c")
        assert line is not None
        assert line[1] >= 0
        assert line[1] + line[3] <= section.text.winfo_height()
        section.begin()
        section.text.delete("1.0", "end")
        section.text.insert("1.0", "Temporary edit")
        section.text.focus_force()
        root.update()
        section.text.event_generate("<Escape>")
        root.update()
        assert not section._editing
        assert section.text.get("1.0", "end-1c") == source
        assert not parent_keys and not calls
        section.begin()
        section.text.delete("1.0", "end")
        section.commit()
        assert calls == [("owner-a", "")]
        section.begin()
        section.text.insert("1.0", "Must not follow owner")
        section.present("owner-b", "Second source", "Source description")
        assert not section._editing
        section.commit()
        assert calls == [("owner-a", "")]
        assert section.text.get("1.0", "end-1c") == "Second source"
        assert not errors
        output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        (output / "inline-description-native.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "source_characters": len(source),
                    "scope": "Native Tk widgets and generated Tk Escape; no physical input claim",
                    "checks": [
                        "text plus sibling wheel before/after Map",
                        "nested text and scrollbar routing in read/edit modes",
                        "full source copy",
                        "bounded document height",
                        "last line reachable",
                        "Escape cancels edit only",
                        "empty override saves exact owner",
                        "owner change retires edit",
                        "clean callbacks",
                    ],
                },
                indent=2,
            )
        )
    finally:
        root.destroy()


@pytest.mark.parametrize("width", [380, 560])
@pytest.mark.parametrize("dpi", [None, 192])
def test_inline_description_measured_caption_and_edit_actions_remain_visible(
    width, dpi, tmp_path
):
    from yt_downloader.ui_layout import install_window_logical_metrics

    root = tk.Tk()
    if dpi:
        install_window_logical_metrics(root, dpi=dpi)
        width *= 2
    root.geometry("1180x820+20+30" if dpi else "680x620+200+100")
    apply_product_styles(root)
    section = EditableTextSection(
        root, title="Description", save=lambda *_: True, changed=lambda: None
    )
    try:
        section.present(
            "owner",
            "Long full description. " * 200,
            "Source description retained separately from your personal edits. " * 3,
        )
        for editing in (False, True):
            if editing:
                section.begin()
            root.update()
            height = section.height_for_width(width)
            section.place(x=20, y=20, width=width, height=height)
            root.update()
            assert height + 20 <= root.winfo_height()
            assert (
                section.caption.winfo_rooty() + section.caption.winfo_height()
                <= section.winfo_rooty() + height
            )
            assert (
                section.copy_button.winfo_rootx() + section.copy_button.winfo_width()
                <= section.winfo_rootx() + width
            )
            assert section._copy_icon is not None and not section.copy_button["text"]
            if editing:
                assert (
                    section.actions.winfo_rooty() + section.actions.winfo_height()
                    <= section.winfo_rooty() + height
                )
                assert (
                    section.text.winfo_height()
                    >= section._font.metrics("linespace") * 3
                )
            from yt_downloader.platform_services import capture_own_widget

            output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
            output.mkdir(parents=True, exist_ok=True)
            capture_own_widget(section).save(
                output
                / f"description-{width}-{'edit' if editing else 'read'}-caption.png"
            )
    finally:
        root.destroy()
