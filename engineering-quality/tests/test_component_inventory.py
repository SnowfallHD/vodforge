import re
from pathlib import Path

import pytest
from quality_harness.component_inventory import scan_button_sites


def test_production_retires_widget_buttons_and_uses_shared_qt_controls():
    root = Path(__file__).resolve().parents[2]
    result = scan_button_sites(root)
    assert not result["counts"]
    assert any(
        re.search(r"\bStoneButton\s*\{", p.read_text())
        for p in (root / "yt_downloader/qt_quick").glob("*.qml")
    )
    assert not result["violations"]


@pytest.mark.parametrize(
    "source",
    [
        'ttk.Button(parent, text="Save", padding=2)',
        'p.button(0, 0, 120, "Play", callback, height=32)',
        'tk.Button(parent, text="Download")',
        'p.button(0, 0, 32, "", callback, icon="copy", height=29)',
    ],
)
def test_inventory_rejects_independent_metrics_or_unregistered_widget(tmp_path, source):
    package = tmp_path / "yt_downloader"
    package.mkdir()
    (package / "view.py").write_text(source)
    result = scan_button_sites(tmp_path)
    assert len(result["violations"]) == 1
