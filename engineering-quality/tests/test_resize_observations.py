"""Guard against dropping the only released sample with the old geometry."""

import pytest
from quality_harness.resize_observations import (
    overlapping_heartbeat_gaps,
    released_geometry_samples,
)


def test_first_released_geometry_is_not_discarded():
    pressed = {
        "sample_started": 1.247,
        "button_sample_ended": 1.248,
        "button": True,
        "bounds": (1164, 646),
    }
    first_up = {
        "sample_started": 1.259,
        "button_sample_ended": 1.260,
        "button": False,
        "bounds": (1164, 646),
    }
    final = {
        "sample_started": 1.271,
        "button_sample_ended": 1.272,
        "button": False,
        "bounds": (1172, 648),
    }
    rows = released_geometry_samples([pressed, first_up, final], first_up)
    assert rows == [first_up, final]
    assert len({row["bounds"] for row in rows}) == 2


def test_stable_release_and_unavailable_boundary():
    first = {"button_sample_ended": 1.0, "bounds": (1172, 648)}
    later = {"button_sample_ended": 1.1, "bounds": (1172, 648)}
    assert released_geometry_samples([first, later], None) == []
    assert (
        len({row["bounds"] for row in released_geometry_samples([first, later], first)})
        == 1
    )


@pytest.mark.parametrize(
    "callback,gap,expected",
    [
        (2.0, 500, [500]),  # Both callbacks inside drag.
        (4.0, 2500, [2500]),  # Timer resumes after mouse-up.
        (2.0, 1500, [1500]),  # Timer stall begins before mouse-down.
        (5.0, 5000, [5000]),  # Entire drag falls between callbacks.
        (0.5, 100, []),  # Earlier unrelated callback.
        (5.0, 100, []),  # Later unrelated callback.
    ],
)
def test_timer_stall_selection_preserves_boundary_crossings(callback, gap, expected):
    assert (
        overlapping_heartbeat_gaps([{"t": callback, "gap_ms": gap}], [(1.0, 3.0)])
        == expected
    )


def test_one_stall_overlapping_two_gestures_is_counted_once():
    assert overlapping_heartbeat_gaps(
        [{"t": 5.0, "gap_ms": 5000}], [(1.0, 2.0), (3.0, 4.0)]
    ) == [5000]
    assert overlapping_heartbeat_gaps([{"t": 5.0, "gap_ms": 5000}], []) == []
