from pathlib import Path

import pytest
from quality_harness.component_inventory import scan_button_sites


def test_production_labeled_action_sites_have_no_metric_bypasses():
    root = Path(__file__).resolve().parents[2]
    result = scan_button_sites(root)
    assert result["counts"].get("ProductButton", 0) > 0
    assert result["counts"].get("p.button", 0) > 0
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
