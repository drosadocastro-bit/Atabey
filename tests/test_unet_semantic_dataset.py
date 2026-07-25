from atabey.tracking.unet_action_availability import (
    AnchoredDivisionAction,
    UnetShadowPeak,
)
from atabey.tracking.unet_semantic_dataset import (
    action_conflicts,
    deterministic_action_sample,
    select_actions_for_official_labeling,
)
from atabey.tracking.unet_semantic_features import semantic_action_id


def _peak(peak_id: str, t: int) -> UnetShadowPeak:
    return UnetShadowPeak(peak_id, "sample", t, 0.0, 0.0, 0.0, 0.99)


def _action(
    suffix: str,
    *,
    anchor: str = "anchor",
    parent: str = "parent",
    child_1: str | None = None,
    child_2: str | None = None,
) -> AnchoredDivisionAction:
    return AnchoredDivisionAction(
        "sample",
        2,
        anchor,
        _peak(parent, 2),
        _peak(child_1 or f"left_{suffix}", 3),
        _peak(child_2 or f"right_{suffix}", 3),
        0.0,
    )


def test_conflicts_cover_anchor_parent_and_daughter_ownership():
    positive = _action("positive")
    assert action_conflicts(positive, _action("a", anchor="anchor"))
    assert action_conflicts(
        positive, _action("b", anchor="other_anchor", parent="parent")
    )
    assert action_conflicts(
        positive,
        _action(
            "c",
            anchor="other_anchor",
            parent="other_parent",
            child_1="left_positive",
        ),
    )
    assert not action_conflicts(
        positive,
        _action("d", anchor="other_anchor", parent="other_parent"),
    )


def test_hash_sampling_is_order_independent_and_namespace_sensitive():
    actions = [_action(str(index), anchor=f"a{index}", parent=f"p{index}") for index in range(8)]
    first = deterministic_action_sample(actions, limit=3, namespace="one")
    reversed_result = deterministic_action_sample(
        reversed(actions), limit=3, namespace="one"
    )
    other = deterministic_action_sample(actions, limit=3, namespace="two")

    assert [semantic_action_id(action) for action in first] == [
        semantic_action_id(action) for action in reversed_result
    ]
    assert [semantic_action_id(action) for action in first] != [
        semantic_action_id(action) for action in other
    ]


def test_label_selection_always_keeps_positive_and_respects_caps():
    positive = _action("positive")
    conflicts = [
        _action(str(index), child_1="left_positive")
        for index in range(10)
    ]
    background = [
        _action(
            f"background_{index}",
            anchor=f"anchor_{index}",
            parent=f"parent_{index}",
        )
        for index in range(10)
    ]

    selected = select_actions_for_official_labeling(
        [positive, *conflicts, *background],
        [positive],
        conflict_cap_per_positive=3,
        background_cap_per_event=2,
        namespace="test",
    )

    assert selected[semantic_action_id(positive)] == ("registered_positive",)
    assert sum("conflict_sample" in reasons for reasons in selected.values()) == 3
    assert sum("background_sample" in reasons for reasons in selected.values()) == 2
    assert len(selected) <= 6
