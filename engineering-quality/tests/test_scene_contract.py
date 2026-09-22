from quality_harness.release_gate import (
    DEEP_REQUIRED_SCENARIOS,
    NORMAL_REQUIRED_SCENARIOS,
)
from quality_harness.scene_contract import REQUIRED_SCENARIOS, SCENE_CLASSES


def test_all_scene_defect_classes_are_mandatory_in_normal_and_deep():
    assert set(SCENE_CLASSES) == {
        "file_action_integrity",
        "shared_scroll_ownership",
        "shared_keyboard_ownership",
        "shared_pointer_ownership",
        "readable_descriptions",
        "library_restraint",
        "watch_queue",
        "window_chrome",
        "channel_membership",
        "channel_artwork",
        "artwork_fidelity",
        "progress_lifetime",
        "volume_truth",
        "bounded_navigation",
        "import_integrity",
        "detail_geometry",
        "annotation_ownership",
        "history_publication",
        "player_related",
        "player_presentation",
    }
    assert REQUIRED_SCENARIOS <= NORMAL_REQUIRED_SCENARIOS
    assert REQUIRED_SCENARIOS <= DEEP_REQUIRED_SCENARIOS
    assert all(
        minimum > 0 and selectors for minimum, selectors in SCENE_CLASSES.values()
    )


def test_semantic_scene_probes_are_enrolled_in_their_required_classes():
    from quality_harness.scene_contract import SCENE_REQUIRED_TESTS

    for name, nodes in SCENE_REQUIRED_TESTS.items():
        enrolled = {selector.split("::")[0] for selector in SCENE_CLASSES[name][1]}
        assert nodes
        assert {node.split("::")[0] for node in nodes} <= enrolled
    projection = [
        node
        for node in SCENE_REQUIRED_TESTS["bounded_navigation"]
        if node.startswith("tests/test_scene_projection.py::")
    ]
    assert len(projection) == 8
    assert any(
        "continuous_media_window" in node
        for node in SCENE_REQUIRED_TESTS["bounded_navigation"]
    )
