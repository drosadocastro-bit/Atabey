from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

import numpy as np

from atabey.tracking.division_firewall import _angle_between
from atabey.types import Detection, LineageGraph


TRACK_B_CONFIDENCE_THRESHOLD = 0.60


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
    ranking_score: float
    angle_deg: float | None
    distance_ratio: float | None
    max_drift_deg: float | None
    v_sep_1_um_per_frame: float | None
    child_1_distance_um: float
    child_2_distance_um: float
    child_separation_um: float
    local_density_t1_10um: int
    parent_volume: float | None
    child_volume_sum: float | None
    volume_conservation_error: float | None
    parent_intensity: float | None
    child_intensity_sum: float | None
    intensity_conservation_error: float | None
    calibrated_confidence: float | None = None
    confidence_threshold: float = TRACK_B_CONFIDENCE_THRESHOLD
    decision_mode: str = "extractive_flagged"
    confidence_basis: str = "uncalibrated"


@dataclass(frozen=True)
class DivisionRecoveryShadowSummary:
    nodes: int
    edges: int
    candidate_count: int
    accepted_count: int
    proposal_count: int
    flagged_count: int
    candidates: list[DivisionRecoveryCandidate] = field(default_factory=list)


def route_division_recovery_candidate(
    candidate: DivisionRecoveryCandidate,
    *,
    calibrated_confidence: float | None,
    confidence_threshold: float = TRACK_B_CONFIDENCE_THRESHOLD,
    confidence_basis: str = "external_calibrator",
) -> DivisionRecoveryCandidate:
    """Route a Track B candidate without treating its ranking score as confidence.

    The NIC-inspired fallback is intentionally extractive: uncertain candidates
    retain their measured node IDs and feature values, but are not promoted to a
    division proposal. A rejected geometric candidate remains rejected.
    """

    threshold = float(confidence_threshold)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("confidence_threshold must be within [0, 1]")
    if calibrated_confidence is not None:
        calibrated_confidence = float(calibrated_confidence)
        if not 0.0 <= calibrated_confidence <= 1.0:
            raise ValueError("calibrated_confidence must be within [0, 1]")

    if not candidate.accepted:
        decision_mode = "rejected"
    elif calibrated_confidence is not None and calibrated_confidence >= threshold:
        decision_mode = "division_proposal"
    else:
        decision_mode = "extractive_flagged"

    basis = confidence_basis if calibrated_confidence is not None else "uncalibrated_feature_evidence"
    return replace(
        candidate,
        calibrated_confidence=calibrated_confidence,
        confidence_threshold=threshold,
        decision_mode=decision_mode,
        confidence_basis=basis,
    )


def _nodes_by_id(graph: LineageGraph) -> dict[str, Detection]:
    return {detection.node_id: detection for detection in graph.detections}


def _detections_by_t(graph: LineageGraph) -> dict[int, list[Detection]]:
    by_t: dict[int, list[Detection]] = {}
    for detection in graph.detections:
        by_t.setdefault(int(detection.t), []).append(detection)
    return by_t


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


def _detection_intensity(detection: Detection) -> float | None:
    if detection.intensity_mean is not None:
        return float(detection.intensity_mean)
    if detection.intensity_max is not None:
        return float(detection.intensity_max)
    return None


def _relative_error(parent_value: float | None, child_sum: float | None) -> float | None:
    if parent_value is None or child_sum is None or parent_value <= 0.0:
        return None
    return abs(float(child_sum) - float(parent_value)) / max(float(parent_value), 1e-6)


def _local_density(parent: Detection, detections: list[Detection], radius_um: float) -> int:
    parent_pos = np.array(parent.position_um, dtype=float)
    return sum(
        1
        for detection in detections
        if float(np.linalg.norm(np.array(detection.position_um, dtype=float) - parent_pos)) <= float(radius_um)
    )


def _geometry_score(angle: float | None, ratio: float | None, drift: float | None, v_sep_1: float | None) -> float:
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


def _ranking_score(
    geometry_score: float,
    local_density: int,
    child_separation_um: float,
    distance_ratio: float | None,
    volume_error: float | None,
    intensity_error: float | None,
) -> float:
    separation_score = max(0.0, min(1.0, float(child_separation_um) / 15.0))
    ratio_score = 1.0 / (1.0 + abs(float(distance_ratio) - 1.0)) if distance_ratio is not None else 0.5
    density_score = 1.0 / (1.0 + float(local_density))
    volume_score = 1.0 / (1.0 + float(volume_error)) if volume_error is not None else 0.5
    intensity_score = 1.0 / (1.0 + float(intensity_error)) if intensity_error is not None else 0.5
    return float(
        0.40 * separation_score
        + 0.25 * ratio_score
        + 0.20 * float(geometry_score)
        + 0.10 * density_score
        + 0.025 * volume_score
        + 0.025 * intensity_score
    )


def _score_branch(
    graph: LineageGraph,
    parent_id: str,
    child_ids: list[str],
    *,
    fallback_min_angle_deg: float,
    fallback_max_distance_ratio: float,
    multi_frame_max_drift_deg: float,
    multi_frame_min_separation_growth_um: float,
    local_density_radius_um: float,
) -> DivisionRecoveryCandidate | None:
    nodes = _nodes_by_id(graph)
    outgoing = _outgoing(graph)
    by_t = _detections_by_t(graph)
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
    child_separation = _distance_um(child_1, child_2)
    density = _local_density(parent, by_t.get(int(parent.t) + 1, []), local_density_radius_um)

    parent_volume = float(parent.component_volume) if parent.component_volume is not None else None
    child_volume_sum = (
        float(child_1.component_volume + child_2.component_volume)
        if child_1.component_volume is not None and child_2.component_volume is not None
        else None
    )
    volume_error = _relative_error(parent_volume, child_volume_sum)

    parent_intensity = _detection_intensity(parent)
    child_1_intensity = _detection_intensity(child_1)
    child_2_intensity = _detection_intensity(child_2)
    child_intensity_sum = (
        float(child_1_intensity + child_2_intensity)
        if child_1_intensity is not None and child_2_intensity is not None
        else None
    )
    intensity_error = _relative_error(parent_intensity, child_intensity_sum)

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
        geometry = _geometry_score(None, None, max_drift, v_sep_1)
        return DivisionRecoveryCandidate(
            sample_id=graph.sample_id,
            parent_id=parent_id,
            child_1_id=child_ids[0],
            child_2_id=child_ids[1],
            t=int(parent.t),
            accepted=accepted,
            reason=reason,
            score=geometry,
            ranking_score=_ranking_score(geometry, density, child_separation, None, volume_error, intensity_error),
            angle_deg=None,
            distance_ratio=None,
            max_drift_deg=max_drift,
            v_sep_1_um_per_frame=v_sep_1,
            child_1_distance_um=d1,
            child_2_distance_um=d2,
            child_separation_um=child_separation,
            local_density_t1_10um=density,
            parent_volume=parent_volume,
            child_volume_sum=child_volume_sum,
            volume_conservation_error=volume_error,
            parent_intensity=parent_intensity,
            child_intensity_sum=child_intensity_sum,
            intensity_conservation_error=intensity_error,
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

    geometry = _geometry_score(angle, ratio, None, None)
    return DivisionRecoveryCandidate(
        sample_id=graph.sample_id,
        parent_id=parent_id,
        child_1_id=child_ids[0],
        child_2_id=child_ids[1],
        t=int(parent.t),
        accepted=accepted,
        reason=reason,
        score=geometry,
        ranking_score=_ranking_score(geometry, density, child_separation, ratio, volume_error, intensity_error),
        angle_deg=angle,
        distance_ratio=ratio,
        max_drift_deg=None,
        v_sep_1_um_per_frame=None,
        child_1_distance_um=d1,
        child_2_distance_um=d2,
        child_separation_um=child_separation,
        local_density_t1_10um=density,
        parent_volume=parent_volume,
        child_volume_sum=child_volume_sum,
        volume_conservation_error=volume_error,
        parent_intensity=parent_intensity,
        child_intensity_sum=child_intensity_sum,
        intensity_conservation_error=intensity_error,
    )


def compute_division_recovery_shadow(
    graph: LineageGraph,
    *,
    fallback_min_angle_deg: float = 120.0,
    fallback_max_distance_ratio: float = 2.5,
    multi_frame_max_drift_deg: float = 30.0,
    multi_frame_min_separation_growth_um: float = 0.0,
    local_density_radius_um: float = 10.0,
    calibrated_confidence_by_parent_id: Mapping[str, float] | None = None,
    confidence_threshold: float = TRACK_B_CONFIDENCE_THRESHOLD,
    confidence_basis: str = "external_calibrator",
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
            local_density_radius_um=local_density_radius_um,
        )
        if candidate is not None:
            confidence = None
            if calibrated_confidence_by_parent_id is not None:
                confidence = calibrated_confidence_by_parent_id.get(candidate.parent_id)
            candidates.append(
                route_division_recovery_candidate(
                    candidate,
                    calibrated_confidence=confidence,
                    confidence_threshold=confidence_threshold,
                    confidence_basis=confidence_basis,
                )
            )

    accepted_count = sum(1 for candidate in candidates if candidate.accepted)
    proposal_count = sum(1 for candidate in candidates if candidate.decision_mode == "division_proposal")
    flagged_count = sum(1 for candidate in candidates if candidate.decision_mode == "extractive_flagged")
    return DivisionRecoveryShadowSummary(
        nodes=len(graph.detections),
        edges=len(graph.edges),
        candidate_count=len(candidates),
        accepted_count=int(accepted_count),
        proposal_count=int(proposal_count),
        flagged_count=int(flagged_count),
        candidates=candidates,
    )
