"""Window visibility shares the attestation deadline and exact process owner."""

import importlib.util
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "runners" / "macos-native-startup.py"
spec = importlib.util.spec_from_file_location("native_intel_startup", RUNNER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Clock:
    def __init__(self, initial=8.0):
        self.value = initial

    def now(self):
        return self.value

    def pause(self, seconds):
        self.value += seconds


def window(**overrides):
    return dict(
        owner_pid=1234, layer=0, bounds={"Width": 1100, "Height": 740}, **overrides
    )


def observe(clock, sample, *, alive=lambda: True, observations=None):
    return module.wait_for_native_window(
        pid=1234,
        deadline=20.0,
        sample=sample,
        alive=alive,
        observations=observations if observations is not None else [],
        now=clock.now,
        pause=clock.pause,
    )


def test_window_server_publication_after_attestation_is_observed():
    clock = Clock()
    samples = iter([[], [], [window()]])
    observations = []
    assert observe(clock, lambda: next(samples), observations=observations) == [
        window()
    ]
    assert len(observations) == 3
    assert clock.value == pytest.approx(8.2)
    assert observations[:2] == [
        {"seconds_remaining": 12.0, "owned_windows": []},
        {"seconds_remaining": 11.9, "owned_windows": []},
    ]


@pytest.mark.parametrize(
    "invalid",
    [
        {"owner_pid": 5678},
        {"layer": 1},
        {"bounds": {"Width": 0, "Height": 740}},
        {"bounds": {"Width": 1100, "Height": 0}},
    ],
)
def test_wrong_owner_or_invisible_geometry_cannot_qualify(invalid):
    clock = Clock()
    candidate = window()
    candidate.update(invalid)
    with pytest.raises(RuntimeError, match="original 20-second"):
        observe(clock, lambda: [candidate])
    assert clock.value == 20.0


def test_attestation_time_is_not_added_to_the_window_deadline():
    clock = Clock(20.0)
    with pytest.raises(RuntimeError, match="original 20-second"):
        observe(clock, lambda: pytest.fail("deadline already expired"))


def test_window_query_finishing_after_deadline_cannot_qualify():
    clock = Clock(19.9)

    def late_window():
        clock.pause(0.2)
        return [window()]

    with pytest.raises(RuntimeError, match="original 20-second"):
        observe(clock, late_window)


def test_exited_owned_process_cannot_qualify():
    with pytest.raises(RuntimeError, match="exited before"):
        observe(Clock(), lambda: [window()], alive=lambda: False)
