"""Temporal owner contract from72b0491's entry trace, not native pixel proof."""

from PySide6.QtTest import QTest

from tests.test_qt_native_header_host import native_owner_rig  # noqa: F401


def test_pending_entry_recovers_on_native_event_without_composer_input(
    native_owner_rig,  # noqa: F811
):
    rig = native_owner_rig
    owner = rig.make()
    surface = rig.surface
    parent = rig.header.parentItem()
    rig.state.update(unallocated=True, fullscreen=True, transition=1)
    owner._native_changed()
    assert (
        rig.window._native_header_diagnostic["stage"]
        == "native_header_pending_allocation"
    )
    assert rig.window.property("nativeHeaderInputReady") is False
    # The captured gap is577ms. Time alone must not guess that allocation is
    # complete, retire the exact native child, or re-enable stale hit geometry.
    QTest.qWait(577)
    assert not owner.retired
    assert rig.surface is surface and rig.header.parentItem() is parent
    assert rig.window.property("nativeHeaderInputReady") is False
    rig.state.update(
        unallocated=False, fullscreen=True, transition=0, controls_hidden=True
    )
    owner._native_changed()
    # No focus/click/event-loop wait: the genuine allocation callback owns the
    # recovery. The native record recovered9.56s before the later composer click.
    assert not owner.retired
    assert rig.surface is surface and rig.header.parentItem() is parent
    assert rig.window.property("nativeHeaderInputReady") is True
    assert rig.window._native_header_diagnostic["stage"] == "success"
    owner.close()
