from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Iterable

from atabey.tracking.unet_action_availability import AnchoredDivisionAction
from atabey.tracking.unet_semantic_features import semantic_action_id


def action_conflicts(
    left: AnchoredDivisionAction,
    right: AnchoredDivisionAction,
) -> bool:
    """Return whether two division actions compete for local ownership."""

    if left.sample_id != right.sample_id or int(left.t) != int(right.t):
        return False
    if left.anchor_id == right.anchor_id:
        return True
    if left.parent.peak_id == right.parent.peak_id:
        return True
    left_children = {left.child_1.peak_id, left.child_2.peak_id}
    right_children = {right.child_1.peak_id, right.child_2.peak_id}
    return bool(left_children & right_children)


def deterministic_action_sample(
    actions: Iterable[AnchoredDivisionAction],
    *,
    limit: int,
    namespace: str,
) -> tuple[AnchoredDivisionAction, ...]:
    """Choose a stable, score-independent sample by namespaced hash."""

    if limit < 0:
        raise ValueError("limit must be non-negative")
    unique = {semantic_action_id(action): action for action in actions}
    ordered = sorted(
        unique.values(),
        key=lambda action: (
            hashlib.sha256(
                f"{namespace}|{semantic_action_id(action)}".encode("utf-8")
            ).hexdigest(),
            semantic_action_id(action),
        ),
    )
    return tuple(ordered[:limit])


def select_actions_for_official_labeling(
    actions: Iterable[AnchoredDivisionAction],
    positive_actions: Iterable[AnchoredDivisionAction],
    *,
    conflict_cap_per_positive: int,
    background_cap_per_event: int,
    namespace: str = "v22-semantic-label-v1",
) -> dict[str, tuple[str, ...]]:
    """Select pre-registered actions for direct official scoring.

    Positives are always retained. Conflict and background samples are selected
    without using semantic features or model scores.
    """

    if conflict_cap_per_positive < 0 or background_cap_per_event < 0:
        raise ValueError("sampling caps must be non-negative")

    action_list = tuple(actions)
    positive_list = tuple(positive_actions)
    reasons: dict[str, set[str]] = defaultdict(set)
    positive_ids = {semantic_action_id(action) for action in positive_list}
    for positive in positive_list:
        reasons[semantic_action_id(positive)].add("registered_positive")
        conflicts = (
            action
            for action in action_list
            if semantic_action_id(action) not in positive_ids
            and action_conflicts(action, positive)
        )
        for action in deterministic_action_sample(
            conflicts,
            limit=conflict_cap_per_positive,
            namespace=(
                f"{namespace}|conflict|{semantic_action_id(positive)}"
            ),
        ):
            reasons[semantic_action_id(action)].add("conflict_sample")

    for action in deterministic_action_sample(
        (
            action
            for action in action_list
            if semantic_action_id(action) not in positive_ids
        ),
        limit=background_cap_per_event,
        namespace=f"{namespace}|background",
    ):
        reasons[semantic_action_id(action)].add("background_sample")

    return {
        action_id: tuple(sorted(action_reasons))
        for action_id, action_reasons in sorted(reasons.items())
    }
