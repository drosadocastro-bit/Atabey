from __future__ import annotations

from dataclasses import dataclass
import math

from atabey.tracking.bounded_ilp_shadow import (
    BoundedIlpShadowResult,
    audit_bounded_ilp_window,
)
from atabey.tracking.commitment_shadow import (
    CommitmentShadowRecord,
    CommitmentShadowSummary,
)
from atabey.types import LineageGraph


@dataclass(frozen=True)
class CommitmentIlpShadowRecord:
    source_id: str
    target_id: str
    changed_assignment_count: int
    reconverged: bool
    minimum_margin_um: float | None
    primary: BoundedIlpShadowResult
    zero_penalty_diagnostic: BoundedIlpShadowResult


@dataclass(frozen=True)
class CommitmentIlpShadowSummary:
    sample_id: str
    root_changed_window_count: int
    root_persistent_window_count: int
    evaluated_window_count: int
    primary_alternative_count: int
    zero_penalty_alternative_count: int
    persistent_zero_penalty_overlap_count: int
    max_ilp_windows: int
    records: tuple[CommitmentIlpShadowRecord, ...]


def audit_commitment_ilp_funnel(
    graph: LineageGraph,
    commitment: CommitmentShadowSummary,
    *,
    baseline_change_penalty_um: float = 2.0,
    minimum_improvement_um: float = 0.5,
    max_ilp_windows: int = 16,
    max_variables: int = 512,
    time_limit_seconds: float = 5.0,
) -> CommitmentIlpShadowSummary:
    """Adjudicate commitment-sensitive windows with a bounded ILP shadow.

    The commitment audit supplies intervention-based sensitivity; the ILP
    supplies joint assignment alternatives. Neither signal confirms identity.
    """

    if graph.sample_id != commitment.sample_id:
        raise ValueError("Graph and commitment summary sample IDs must match")
    if max_ilp_windows < 0:
        raise ValueError("max_ilp_windows must be non-negative")

    changed = [
        record
        for record in commitment.records
        if record.changed_assignment_count > 0
    ]
    persistent = [record for record in changed if not record.reconverged]
    selected = sorted(changed, key=_selection_key)[:max_ilp_windows]
    records: list[CommitmentIlpShadowRecord] = []
    for trigger in selected:
        common = {
            "trigger_source_id": trigger.source_id,
            "trigger_target_id": trigger.target_id,
            "max_variables": max_variables,
            "time_limit_seconds": time_limit_seconds,
        }
        primary = audit_bounded_ilp_window(
            graph,
            baseline_change_penalty_um=baseline_change_penalty_um,
            minimum_improvement_um=minimum_improvement_um,
            **common,
        )
        zero_penalty = audit_bounded_ilp_window(
            graph,
            baseline_change_penalty_um=0.0,
            minimum_improvement_um=0.0,
            **common,
        )
        records.append(
            CommitmentIlpShadowRecord(
                source_id=trigger.source_id,
                target_id=trigger.target_id,
                changed_assignment_count=trigger.changed_assignment_count,
                reconverged=trigger.reconverged,
                minimum_margin_um=_minimum_margin(trigger),
                primary=primary,
                zero_penalty_diagnostic=zero_penalty,
            )
        )

    return CommitmentIlpShadowSummary(
        sample_id=graph.sample_id,
        root_changed_window_count=len(changed),
        root_persistent_window_count=len(persistent),
        evaluated_window_count=len(records),
        primary_alternative_count=sum(
            record.primary.recommendation == "shadow_alternative"
            for record in records
        ),
        zero_penalty_alternative_count=sum(
            record.zero_penalty_diagnostic.recommendation == "shadow_alternative"
            for record in records
        ),
        persistent_zero_penalty_overlap_count=sum(
            not record.reconverged
            and record.zero_penalty_diagnostic.recommendation == "shadow_alternative"
            for record in records
        ),
        max_ilp_windows=max_ilp_windows,
        records=tuple(records),
    )


def _minimum_margin(record: CommitmentShadowRecord) -> float | None:
    margins = [
        margin
        for margin in (record.forward_margin_um, record.reverse_margin_um)
        if margin is not None and math.isfinite(margin)
    ]
    return min(margins, default=None)


def _selection_key(record: CommitmentShadowRecord) -> tuple[bool, float, str, str]:
    margin = _minimum_margin(record)
    return (
        record.reconverged,
        margin if margin is not None else math.inf,
        record.source_id,
        record.target_id,
    )