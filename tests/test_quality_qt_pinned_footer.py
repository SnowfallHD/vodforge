"""Qt pinned footer contract preserves real reader/control visibility negatives."""

import json

import pytest

from tests.test_quality_e2e import _isolated_launch, _qt_visibility_fields
from yt_downloader.quality_e2e import write_quality_e2e_qt_library_visibility_receipt


def pinned_fields():
    fields = _qt_visibility_fields()
    fields.update(
        {
            "details_bounds": {"x": 700, "y": 300, "width": 380, "height": 278},
            "description_viewport_bounds": {
                "x": 710,
                "y": 335,
                "width": 360,
                "height": 243,
            },
            "footer_bounds": {"x": 700, "y": 586, "width": 380, "height": 74},
            "footer_action_bounds": {"x": 700, "y": 586, "width": 380, "height": 40},
            "footer_visible": True,
            "footer_action_visible": True,
            "location_visible": True,
            "details_footer_gap_px": 8,
        }
    )
    return fields


def test_real_available_reader_space_and_footer_control_geometry(tmp_path):
    environment, *_ = _isolated_launch(tmp_path)
    path = write_quality_e2e_qt_library_visibility_receipt(
        **pinned_fields(), environ=environment
    )
    payload = json.loads(path.read_text())
    assert payload["verified"]
    assert payload["details_minimum_available_height_px"] == 278
    assert payload["description_table_bottom_delta_px"] == -82
    assert payload["footer_table_bottom_delta_px"] == 0
    assert payload["reader_footer_gap_delta_px"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        {"footer_visible": False},
        {"footer_action_visible": False},
        {"location_visible": False},
        {"projected_owner": "wrong-owner"},
        {"description_visible": False},
        {"heading_visible": False},
        {"description_scroll_at_start": False},
        {"location_truncated": False},
        {"footer_bounds": {"x": 700, "y": 581, "width": 380, "height": 74}},
        {"footer_action_bounds": {"x": 700, "y": 570, "width": 380, "height": 40}},
        {
            "description_viewport_bounds": {
                "x": 710,
                "y": 335,
                "width": 360,
                "height": 200,
            }
        },
        {
            "description_viewport_bounds": {
                "x": 710,
                "y": 335,
                "width": 360,
                "height": 118,
            }
        },
    ],
)
def test_missing_or_occluded_control_reader_owner_path_still_fails(tmp_path, mutation):
    environment, *_ = _isolated_launch(tmp_path)
    fields = pinned_fields()
    fields.update(mutation)
    path = write_quality_e2e_qt_library_visibility_receipt(
        **fields, environ=environment
    )
    assert not json.loads(path.read_text())["verified"]


def test_tiny_reader_cannot_pass_even_with_all_edges_aligned(tmp_path):
    environment, *_ = _isolated_launch(tmp_path)
    fields = pinned_fields()
    fields.update(
        {
            "details_bounds": {"x": 700, "y": 450, "width": 380, "height": 128},
            "description_heading_bounds": {
                "x": 710,
                "y": 460,
                "width": 140,
                "height": 20,
            },
            "description_viewport_bounds": {
                "x": 710,
                "y": 485,
                "width": 360,
                "height": 93,
            },
            "description_text_bounds": {
                "x": 710,
                "y": 485,
                "width": 360,
                "height": 800,
            },
        }
    )
    path = write_quality_e2e_qt_library_visibility_receipt(
        **fields, environ=environment
    )
    payload = json.loads(path.read_text())
    assert payload["reader_footer_gap_delta_px"] == 0
    assert payload["footer_table_bottom_delta_px"] == 0
    assert payload["description_first_line_visible"]
    assert not payload["verified"]


def test_footer_cannot_be_attested_without_an_actual_action(tmp_path):
    from yt_downloader.quality_e2e import QualityE2EAttestationError

    environment, *_ = _isolated_launch(tmp_path)
    fields = pinned_fields()
    fields["footer_action_bounds"] = None
    with pytest.raises(QualityE2EAttestationError, match="footer context"):
        write_quality_e2e_qt_library_visibility_receipt(**fields, environ=environment)
