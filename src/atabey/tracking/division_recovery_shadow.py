from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from atabey.tracking.division_firewall import _angle_between
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class DivisionRecoveryCandidate:
    sample_id: str
    parent_id: str
    child_1_id: str
    child_2_id: str
    t: int
    accepted: bool
    reason: str
    score: float
    angle_deg: float | None
    distance_ratio: float | None
    max_drift_deg: float | None
    v_sep_1_um_per_frame: float | None


@dataclass(frozen=True)
class DivisionRecoveryShadowSummary:
    nodes: int
    edges: int
    candidate_count: int
    accepted_count: int
    candidates: list[DivisionRecoveryCandidate] = field(default_factory=list)


def _nodes_by_id(graph: LineageGraph) -> dict[str, Detection]:
    return {detection.node_id: detection for detection in graph.detections}


def _outgoing(graph: LineageGraph) -> dict[str, list[str]]:
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_id, []).append(edge.target_id)
    return outgoing


def _descendant_at(
    outgoing: dict[str, list[str]],
    nodes: dict[str, Detection],
    node_id: str,
    target_t: int,
) -> Detection | None:
    current = nodes.get(node_id)
    while current is not None and int(current.t) < int(target_t):
        next_ids = outgoing.get(current.node_id, [])
        if not next_ids:
            return None
        current = nodes.get(next_ids[0])
    return current


def _distance_um(a: Detection, b: Detection) -> float:
    return float(np.linalg.norm(np.array(a.position_um, dtype=float) - np.array(b.position_um, dtype=float)))


def _score(angle: float | None, ratio: float | None, drift: float | None, v_sep_1: float | None) -> float:
    parts: list[float] = []
    if angle is not None:
        parts.append(max(0.0, min(1.0, (float(angle) - 90.0) / 90.0)))
    if ratio is not None:
        parts.append(max(0.0, min(1.0, (2.75 - float(ratio)) / 1.75)))
    if drift is not None:
        parts.append(max(0.0, min(1.0, (30.0 - float(drift)) / 30.0)))
    if v_sep_1 is not None:
        parts.append(max(0.0, min(1.0, float(v_sep_1) / 3.0)))
    return float(sum(parts) / len(parts)) if parts else 0.0


def _score_branch(
    graph: LineageGraph,
    parent_id: str,
    child_ids: list[str],
    *,
    fallback_min_angle_deg: float,
    fallback_max_distance_ratio: float,
    multi_frame_max_drift_deg: float,
    multi_frame_min_separation_growth_um: float,
) -> DivisionRecoveryCandidate | None:
    nodes = _nodes_by_id(graph)
    outgoing = _outgoing(graph)
    parent = nodes.get(parent_id)
    if parent is None or len(child_ids) < 2:
        return None

    child_1 = nodes.get(child_ids[0])
    child_2 = nodes.get(child_ids[1])
    if child_1 is None or child_2 is None:
        return None
    if int(child_1.t) != int(parent.t) + 1 or int(child_2.t) != int(parent.t) + 1:
        return None

    d1 = _distance_um(parent, child_1)
    d2 = _distance_um(parent, child_2)
    if d1 <= d2:
        primary_id, orphan_id = child_1.node_id, child_2.node_id
    else:
        primary_id, orphan_id = child_2.node_id, child_1.node_id

    branch_1: list[Detection | None] = [nodes[primary_id]]
    branch_2: list[Detection | None] = [nodes[orphan_id]]
    for offset in [2, 3]:
        branch_1.append(_descendant_at(outgoing, nodes, branch_1[-1].node_id, int(parent.t) + offset) if branch_1[-1] else None)
        branch_2.append(_descendant_at(outgoing, nodes, branch_2[-1].node_id, int(parent.t) + offset) if branch_2[-1] else None)

    axes: list[np.ndarray] = []
    separations: list[float] = []
    for node_1, node_2 in zip(branch_1, branch_2):
        if node_1 is None or node_2 is None:
            continue
        axis = np.array(node_1.position_um, dtype=float) - np.array(node_2.position_um, dtype=float)
        axes.append(axis)
        separations.append(float(np.linalg.norm(axis)))

    max_drift: float | None = None
    v_sep_1: float | None = None
    if len(axes) >= 3:
        drifts = []
        for index in range(len(axes) - 1):
            angle = _angle_between(axes[index], axes[index + 1])
            drifts.append(min(angle, 180.0 - angle))
        max_drift = max(drifts)
        v_sep_1 = separations[1] - separations[0]
        accepted = max_drift < float(multi_frame_max_drift_deg) and v_sep_1 > float(multi_frame_min_separation_growth_um)
        reason = "multi_frame_positive_divergence" if accepted else "multi_frame_rejected"
        return DivisionRecoveryCandidate(
            sample_id=graph.sample_id,
            parent_id=parent_id,
            child_1_id=child_ids[0],
            child_2_id=child_ids[1],
            t=int(parent.t),
            accepted=accepted,
            reason=reason,
            score=_score(None, None, max_drift, v_sep_1),
            angle_deg=None,
            distance_ratio=None,
            max_drift_deg=max_drift,
            v_sep_1_um_per_frame=v_sep_1,
        )

    v1 = np.array(child_1.position_um, dtype=float) - np.array(parent.position_um, dtype=float)
    v2 = np.array(child_2.position_um, dtype=float) - np.array(parent.position_um, dtype=float)
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    angle = _angle_between(v1, v2)
    if n1 < 1e-6 or n2 < 1e-6:
        ratio = None
        accepted = False
        reason = "fallback_zero_vector"
    else:
        ratio = max(n1, n2) / min(n1, n2)
        accepted = angle >= float(fallback_min_angle_deg) and ratio <= float(fallback_max_distance_ratio)
        reason = "fallback_broad_angle_balanced_split" if accepted else "fallback_rejected"

    return DivisionRecoveryCandidate(
        sample_id=graph.sample_id,
        parent_id=parent_id,
        child_1_id=child_ids[0],
        child_2_id=child_ids[1],
        t=int(parent.t),
        accepted=accepted,
        reason=reason,
        score=_score(angle, ratio, None, None),
        angle_deg=angle,
        distance_ratio=ratio,
        max_drift_deg=None,
        v_sep_1_um_per_frame=None,
    )


def compute_division_recovery_shadow(
    graph: LineageGraph,
    *,
    fallback_min_angle_deg: float = 120.0,
    fallback_max_distance_ratio: float = 2.5,
    multi_frame_max_drift_deg: float = 30.0,
    multi_frame_min_separation_growth_um: float = 0.0,
) -> DivisionRecoveryShadowSummary:
    """Score division candidates without mutating the production lineage graph.

    This is V21 Track B: a shadow-only recovery path. It is intended to run next
    to the frozen V20 topology path and annotate possible true divisions for
    measurement. Accepted candidates are not committed as graph edges here.
    """

    outgoing = _outgoing(graph)
    candidates: list[DivisionRecoveryCandidate] = []
    for parent_id, child_ids in sorted(outgoing.items()):
        if len(child_ids) != 2:
            continue
        candidate = _score_branch(
            graph,
            parent_id,
            child_ids,
            fallback_min_angle_deg=fallback_min_angle_deg,
            fallback_max_distance_ratio=fallback_max_distance_ratio,
            multi_frame_max_drift_deg=multi_frame_max_drift_deg,
            multi_frame_min_separation_growth_um=multi_frame_min_separation_growth_um,
        )
        if candidate is not None:
            candidates.append(candidate)

    accepted_count = sum(1 for candidate in candidates if candidate.accepted)
    return DivisionRecoveryShadowSummary(
        nodes=len(graph.detections),
        edges=len(graph.edges),
        candidate_count=len(candidates),
        accepted_count=int(accepted_count),
        candidates=candidates,
    )
