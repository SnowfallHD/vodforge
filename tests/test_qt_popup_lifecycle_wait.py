"""A delayed event dispatch must not assert a cached pre-dispatch popup state."""

from types import SimpleNamespace

import pytest

from tests import test_qt_popup_toggle_order as owner


@pytest.mark.parametrize("terminal", ["opened", "closed", "still-moving"])
def test_settle_liquid_rechecks_state_after_last_event_dispatch(monkeypatch, terminal):
    clock = [0.0]
    state = {
        "liquidMotion": True,
        "visible": True,
        "reveal": 0.2,
        "exitInProgress": False,
    }
    popup = SimpleNamespace(property=lambda name: state[name])
    window = SimpleNamespace(findChildren=lambda _kind: [popup])

    def delayed_dispatch(_milliseconds):
        # One dispatch crosses the whole wait budget.
        clock[0] = owner.LIQUID_SETTLE_BUDGET_S + 0.2
        if terminal == "opened":
            state["reveal"] = 1.0
        elif terminal == "closed":
            state["visible"] = False

    monkeypatch.setattr(owner, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(owner, "QTest", SimpleNamespace(qWait=delayed_dispatch))
    if terminal == "still-moving":
        with pytest.raises(AssertionError, match="lifecycle did not finish"):
            owner.settle_liquid(window)
    else:
        owner.settle_liquid(window)


def test_settle_liquid_waits_for_an_exit_that_has_not_moved_yet(monkeypatch):
    """Right after close() the reveal is still 1.0; that is not settled-open."""
    clock = [0.0]
    state = {
        "liquidMotion": True,
        "visible": True,
        "reveal": 1.0,
        "exitInProgress": True,
    }
    popup = SimpleNamespace(property=lambda name: state[name])
    window = SimpleNamespace(findChildren=lambda _kind: [popup])
    waits = []

    def dispatch(_milliseconds):
        waits.append(_milliseconds)
        clock[0] += 0.05
        if len(waits) == 3:
            state.update(visible=False, reveal=0.0, exitInProgress=False)

    monkeypatch.setattr(owner, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(owner, "QTest", SimpleNamespace(qWait=dispatch))
    owner.settle_liquid(window)
    assert len(waits) == 3 and not state["visible"]
