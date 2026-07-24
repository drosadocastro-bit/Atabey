from __future__ import annotations

from dataclasses import dataclass, replace
import json
from itertools import combinations
from typing import Iterable, Literal

import numpy as np

from atabey.io.geff_reader import SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


ActionType = Literal["continue", "divide", "terminate", "abstain"]
OfficialLabel = Literal[
    "not_evaluated",
    "not_applicable",
    "official_tp",
    "official_fp",
    "official_unsupported",
]


@dataclass(frozen=True)
class JointSemanticEvidence:
    """Raw, unscored evidence for one parent-centered action.

    This record is intentionally not a proposal. Phase 0 emits only abstaining
    evidence rows and never imports or invokes an assignment solver.
    """

    sample_id: str
    parent_id: str
    t: int
    action_type: ActionType
    child_1_id: str | None
    child_2_id: str | None
    candidate_set_complete: bool
    formation_radius_um: float
    continuity_horizon: int
    decision: str
    decision_reason: str
    semantic_score: float | None
    calibrated_confidence: float | None
    parent_predecessor_count: int
    parent_speed_um_per_frame: float | None
    child_1_distance_um: float | None
    child_2_distance_um: float | None
    child_distance_ratio: float | None
    child_separation_um: float | None
    split_angle_deg: float | None
    pair_midpoint_parent_offset_um: float | None
    pair_midpoint_prediction_error_um: float | None
    split_axis_parent_velocity_alignment_deg: float | None
    local_density_t1_10um: int | None
    child_1_continuity_coverage: float | None
    child_2_continuity_coverage: float | None
    child_1_prediction_error_um: float | None
    child_2_prediction_error_um: float | None
    immediate_separation_growth_um: float | None
    max_branch_axis_drift_deg: float | None
    child_1_competing_parent_margin_um: float | None
    child_2_competing_parent_margin_um: float | None
    parent_volume: float | None
    child_volume_sum: float | None
    volume_conservation_error: float | None
    daughter_volume_balance: float | None
    parent_intensity: float | None
    child_intensity_sum: float | None
    intensity_conservation_error: float | None
    daughter_intensity_balance: float | None
    mean_detection_confidence: float | None
    available_features: tuple[str, ...]
    missing_features: tuple[tuple[str, str], ...]
    official_label: OfficialLabel = "not_evaluated"
    official_label_basis: str = "not_evaluated"

    def missing_reason(self, feature: str) -> str | None:
        return dict(self.missing_features).get(feature)


@dataclass(frozen=True)
class JointSemanticShadowSummary:
    sample_id: str
    source_nodes: int
    source_edges: int
    parent_count: int
    action_count: int
    continue_count: int
    divide_count: int
    terminate_count: int
    abstain_count: int
    evidence: tuple[JointSemanticEvidence, ...]


def _distance(left: Detection, right: Detection) -> float:
    return float(
        np.linalg.norm(
            np.asarray(left.position_um, dtype=float)
            - np.asarray(right.position_um, dtype=float)
        )
    )


def _angle(left: np.ndarray, right: np.ndarray) -> float | None:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-9 or right_norm <= 1e-9:
        return None
    cosine = float(np.dot(left, right) / (left_norm * right_norm))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def _relative_error(reference: float | None, observed: float | None) -> float | None:
    if reference is None or observed is None or reference <= 0.0:
        return None
    return abs(float(observed) - float(reference)) / max(float(reference), 1e-9)


def _balance(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    denominator = max(abs(float(left)) + abs(float(right)), 1e-9)
    return abs(float(left) - float(right)) / denominator


def _intensity(detection: Detection) -> float | None:
    if detection.intensity_mean is not None:
        return float(detection.intensity_mean)
    if detection.intensity_max is not None:
        return float(detection.intensity_max)
    return None


def _index_graph(
    graph: LineageGraph,
) -> tuple[
    dict[str, Detection],
    dict[int, list[Detection]],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    nodes = {node.node_id: node for node in graph.detections}
    by_t: dict[int, list[Detection]] = {}
    for node in graph.detections:
        by_t.setdefault(int(node.t), []).append(node)
    for detections in by_t.values():
        detections.sort(key=lambda node: node.node_id)

    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.source_id not in nodes or edge.target_id not in nodes:
            continue
        incoming.setdefault(edge.target_id, []).append(edge.source_id)
        outgoing.setdefault(edge.source_id, []).append(edge.target_id)
    for adjacency in (incoming, outgoing):
        for node_ids in adjacency.values():
            node_ids.sort()
    return nodes, by_t, incoming, outgoing


def _valid_previous(
    parent: Detection,
    incoming: dict[str, list[str]],
    nodes: dict[str, Detection],
) -> list[Detection]:
    return sorted(
        (
            nodes[node_id]
            for node_id in incoming.get(parent.node_id, ())
            if node_id in nodes and int(nodes[node_id].t) == int(parent.t) - 1
        ),
        key=lambda node: (_distance(node, parent), node.node_id),
    )


def _single_continuation(
    start: Detection,
    nodes: dict[str, Detection],
    outgoing: dict[str, list[str]],
    horizon: int,
) -> tuple[list[Detection], str | None]:
    path = [start]
    current = start
    for _ in range(horizon):
        successors = [
            nodes[node_id]
            for node_id in outgoing.get(current.node_id, ())
            if node_id in nodes and int(nodes[node_id].t) == int(current.t) + 1
        ]
        if not successors:
            return path, "daughter_track_ends"
        if len(successors) > 1:
            return path, "ambiguous_daughter_continuation"
        current = successors[0]
        path.append(current)
    return path, None


def _mean_prediction_error(
    parent: Detection,
    path: list[Detection],
) -> float | None:
    if len(path) < 2:
        return None
    positions = [
        np.asarray(parent.position_um, dtype=float),
        *(np.asarray(node.position_um, dtype=float) for node in path),
    ]
    errors: list[float] = []
    for index in range(2, len(positions)):
        predicted = positions[index - 1] + (positions[index - 1] - positions[index - 2])
        errors.append(float(np.linalg.norm(positions[index] - predicted)))
    return float(np.mean(errors)) if errors else None


def _competing_parent_margin(
    focal_parent: Detection,
    child: Detection,
    previous: list[Detection],
) -> float | None:
    other_distances = [
        _distance(parent, child)
        for parent in previous
        if parent.node_id != focal_parent.node_id
    ]
    if not other_distances:
        return None
    return float(min(other_distances) - _distance(focal_parent, child))


def _feature_state(
    values: dict[str, float | int | None],
    reasons: dict[str, str],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    available = tuple(sorted(name for name, value in values.items() if value is not None))
    missing = tuple(
        sorted(
            (
                name,
                reasons.get(name, "unavailable"),
            )
            for name, value in values.items()
            if value is None
        )
    )
    return available, missing


def _base_values() -> dict[str, float | int | None]:
    return {
        "parent_speed_um_per_frame": None,
        "child_1_distance_um": None,
        "child_2_distance_um": None,
        "child_distance_ratio": None,
        "child_separation_um": None,
        "split_angle_deg": None,
        "pair_midpoint_parent_offset_um": None,
        "pair_midpoint_prediction_error_um": None,
        "split_axis_parent_velocity_alignment_deg": None,
        "local_density_t1_10um": None,
        "child_1_continuity_coverage": None,
        "child_2_continuity_coverage": None,
        "child_1_prediction_error_um": None,
        "child_2_prediction_error_um": None,
        "immediate_separation_growth_um": None,
        "max_branch_axis_drift_deg": None,
        "child_1_competing_parent_margin_um": None,
        "child_2_competing_parent_margin_um": None,
        "parent_volume": None,
        "child_volume_sum": None,
        "volume_conservation_error": None,
        "daughter_volume_balance": None,
        "parent_intensity": None,
        "child_intensity_sum": None,
        "intensity_conservation_error": None,
        "daughter_intensity_balance": None,
        "mean_detection_confidence": None,
    }


def _no_target_evidence(
    graph: LineageGraph,
    parent: Detection,
    action_type: Literal["terminate", "abstain"],
    *,
    predecessor_count: int,
    formation_radius_um: float,
    continuity_horizon: int,
) -> JointSemanticEvidence:
    values = _base_values()
    reasons = {name: "not_applicable_for_no_target_action" for name in values}
    available, missing = _feature_state(values, reasons)
    return JointSemanticEvidence(
        sample_id=graph.sample_id,
        parent_id=parent.node_id,
        t=int(parent.t),
        action_type=action_type,
        child_1_id=None,
        child_2_id=None,
        candidate_set_complete=True,
        formation_radius_um=float(formation_radius_um),
        continuity_horizon=int(continuity_horizon),
        decision="abstain",
        decision_reason="phase0_unscored_evidence",
        semantic_score=None,
        calibrated_confidence=None,
        parent_predecessor_count=predecessor_count,
        available_features=available,
        missing_features=missing,
        official_label="not_applicable",
        official_label_basis="no_division_action",
        **values,
    )


def _target_evidence(
    graph: LineageGraph,
    parent: Detection,
    child_1: Detection,
    child_2: Detection | None,
    *,
    nodes: dict[str, Detection],
    by_t: dict[int, list[Detection]],
    incoming: dict[str, list[str]],
    outgoing: dict[str, list[str]],
    formation_radius_um: float,
    continuity_horizon: int,
    local_density_radius_um: float,
) -> JointSemanticEvidence:
    action_type: Literal["continue", "divide"] = "divide" if child_2 is not None else "continue"
    predecessors = _valid_previous(parent, incoming, nodes)
    predecessor = predecessors[0] if predecessors else None
    parent_position = np.asarray(parent.position_um, dtype=float)
    parent_velocity = (
        parent_position - np.asarray(predecessor.position_um, dtype=float)
        if predecessor is not None
        else None
    )
    predicted_parent = parent_position + parent_velocity if parent_velocity is not None else None

    values = _base_values()
    reasons: dict[str, str] = {}
    values["parent_speed_um_per_frame"] = (
        float(np.linalg.norm(parent_velocity)) if parent_velocity is not None else None
    )
    if predecessor is None:
        reasons["parent_speed_um_per_frame"] = "no_parent_history"

    t1_nodes = by_t.get(int(parent.t) + 1, [])
    values["local_density_t1_10um"] = sum(
        _distance(parent, detection) <= float(local_density_radius_um)
        for detection in t1_nodes
    )
    values["child_1_distance_um"] = _distance(parent, child_1)
    values["child_1_competing_parent_margin_um"] = _competing_parent_margin(
        parent,
        child_1,
        by_t.get(int(parent.t), []),
    )
    if values["child_1_competing_parent_margin_um"] is None:
        reasons["child_1_competing_parent_margin_um"] = "no_competing_parent"

    child_1_path, child_1_path_reason = _single_continuation(
        child_1,
        nodes,
        outgoing,
        continuity_horizon,
    )
    values["child_1_continuity_coverage"] = (
        (len(child_1_path) - 1) / float(continuity_horizon)
        if continuity_horizon > 0
        else 1.0
    )
    values["child_1_prediction_error_um"] = _mean_prediction_error(parent, child_1_path)
    if values["child_1_prediction_error_um"] is None:
        reasons["child_1_prediction_error_um"] = child_1_path_reason or "insufficient_future_frames"

    parent_volume = float(parent.component_volume) if parent.component_volume is not None else None
    parent_intensity = _intensity(parent)
    values["parent_volume"] = parent_volume
    values["parent_intensity"] = parent_intensity
    if parent_volume is None:
        reasons["parent_volume"] = "no_component_volume"
    if parent_intensity is None:
        reasons["parent_intensity"] = "no_detection_intensity"

    confidence_values = [
        parent.detection_confidence,
        child_1.detection_confidence,
        *([child_2.detection_confidence] if child_2 is not None else []),
    ]
    values["mean_detection_confidence"] = (
        float(np.mean([float(value) for value in confidence_values]))
        if all(value is not None for value in confidence_values)
        else None
    )
    if values["mean_detection_confidence"] is None:
        reasons["mean_detection_confidence"] = (
            "no_detection_confidence"
            if all(value is None for value in confidence_values)
            else "partial_detection_confidence"
        )

    if child_2 is None:
        not_applicable = (
            "child_2_distance_um",
            "child_distance_ratio",
            "child_separation_um",
            "split_angle_deg",
            "pair_midpoint_parent_offset_um",
            "pair_midpoint_prediction_error_um",
            "split_axis_parent_velocity_alignment_deg",
            "child_2_continuity_coverage",
            "child_2_prediction_error_um",
            "immediate_separation_growth_um",
            "max_branch_axis_drift_deg",
            "child_2_competing_parent_margin_um",
            "child_volume_sum",
            "volume_conservation_error",
            "daughter_volume_balance",
            "child_intensity_sum",
            "intensity_conservation_error",
            "daughter_intensity_balance",
        )
        reasons.update({name: "not_applicable_for_continue_action" for name in not_applicable})
    else:
        child_1_position = np.asarray(child_1.position_um, dtype=float)
        child_2_position = np.asarray(child_2.position_um, dtype=float)
        vector_1 = child_1_position - parent_position
        vector_2 = child_2_position - parent_position
        distance_1 = float(values["child_1_distance_um"])
        distance_2 = _distance(parent, child_2)
        values["child_2_distance_um"] = distance_2
        values["child_distance_ratio"] = (
            max(distance_1, distance_2) / min(distance_1, distance_2)
            if min(distance_1, distance_2) > 1e-9
            else None
        )
        if values["child_distance_ratio"] is None:
            reasons["child_distance_ratio"] = "zero_parent_child_distance"
        values["child_separation_um"] = _distance(child_1, child_2)
        values["split_angle_deg"] = _angle(vector_1, vector_2)
        if values["split_angle_deg"] is None:
            reasons["split_angle_deg"] = "zero_parent_child_vector"

        midpoint = 0.5 * (child_1_position + child_2_position)
        values["pair_midpoint_parent_offset_um"] = float(np.linalg.norm(midpoint - parent_position))
        values["pair_midpoint_prediction_error_um"] = (
            float(np.linalg.norm(midpoint - predicted_parent))
            if predicted_parent is not None
            else None
        )
        if predicted_parent is None:
            reasons["pair_midpoint_prediction_error_um"] = "no_parent_history"

        split_axis = child_1_position - child_2_position
        directed_alignment = (
            _angle(split_axis, parent_velocity) if parent_velocity is not None else None
        )
        values["split_axis_parent_velocity_alignment_deg"] = (
            min(directed_alignment, 180.0 - directed_alignment)
            if directed_alignment is not None
            else None
        )
        if values["split_axis_parent_velocity_alignment_deg"] is None:
            reasons["split_axis_parent_velocity_alignment_deg"] = (
                "no_parent_history" if parent_velocity is None else "zero_split_or_velocity_vector"
            )

        values["child_2_competing_parent_margin_um"] = _competing_parent_margin(
            parent,
            child_2,
            by_t.get(int(parent.t), []),
        )
        if values["child_2_competing_parent_margin_um"] is None:
            reasons["child_2_competing_parent_margin_um"] = "no_competing_parent"

        child_2_path, child_2_path_reason = _single_continuation(
            child_2,
            nodes,
            outgoing,
            continuity_horizon,
        )
        values["child_2_continuity_coverage"] = (
            (len(child_2_path) - 1) / float(continuity_horizon)
            if continuity_horizon > 0
            else 1.0
        )
        values["child_2_prediction_error_um"] = _mean_prediction_error(parent, child_2_path)
        if values["child_2_prediction_error_um"] is None:
            reasons["child_2_prediction_error_um"] = child_2_path_reason or "insufficient_future_frames"

        paired_length = min(len(child_1_path), len(child_2_path))
        axes = [
            np.asarray(child_1_path[index].position_um, dtype=float)
            - np.asarray(child_2_path[index].position_um, dtype=float)
            for index in range(paired_length)
        ]
        separations = [float(np.linalg.norm(axis)) for axis in axes]
        values["immediate_separation_growth_um"] = (
            separations[1] - separations[0] if len(separations) >= 2 else None
        )
        if values["immediate_separation_growth_um"] is None:
            reasons["immediate_separation_growth_um"] = (
                child_1_path_reason
                or child_2_path_reason
                or "insufficient_paired_future_frames"
            )

        drifts = []
        for left_axis, right_axis in zip(axes, axes[1:]):
            angle = _angle(left_axis, right_axis)
            if angle is not None:
                drifts.append(min(angle, 180.0 - angle))
        values["max_branch_axis_drift_deg"] = max(drifts) if drifts else None
        if values["max_branch_axis_drift_deg"] is None:
            reasons["max_branch_axis_drift_deg"] = (
                child_1_path_reason
                or child_2_path_reason
                or "insufficient_paired_future_frames"
            )

        child_1_volume = (
            float(child_1.component_volume) if child_1.component_volume is not None else None
        )
        child_2_volume = (
            float(child_2.component_volume) if child_2.component_volume is not None else None
        )
        values["child_volume_sum"] = (
            child_1_volume + child_2_volume
            if child_1_volume is not None and child_2_volume is not None
            else None
        )
        values["volume_conservation_error"] = _relative_error(
            parent_volume,
            values["child_volume_sum"],
        )
        values["daughter_volume_balance"] = _balance(child_1_volume, child_2_volume)
        if values["child_volume_sum"] is None:
            reasons["child_volume_sum"] = "no_component_volume"
        if values["volume_conservation_error"] is None:
            reasons["volume_conservation_error"] = (
                "no_parent_component_volume"
                if parent_volume is None
                else "no_daughter_component_volume"
            )
        if values["daughter_volume_balance"] is None:
            reasons["daughter_volume_balance"] = "no_daughter_component_volume"

        child_1_intensity = _intensity(child_1)
        child_2_intensity = _intensity(child_2)
        values["child_intensity_sum"] = (
            child_1_intensity + child_2_intensity
            if child_1_intensity is not None and child_2_intensity is not None
            else None
        )
        values["intensity_conservation_error"] = _relative_error(
            parent_intensity,
            values["child_intensity_sum"],
        )
        values["daughter_intensity_balance"] = _balance(
            child_1_intensity,
            child_2_intensity,
        )
        if values["child_intensity_sum"] is None:
            reasons["child_intensity_sum"] = "no_detection_intensity"
        if values["intensity_conservation_error"] is None:
            reasons["intensity_conservation_error"] = (
                "no_parent_detection_intensity"
                if parent_intensity is None
                else "no_daughter_detection_intensity"
            )
        if values["daughter_intensity_balance"] is None:
            reasons["daughter_intensity_balance"] = "no_daughter_detection_intensity"

    available, missing = _feature_state(values, reasons)
    return JointSemanticEvidence(
        sample_id=graph.sample_id,
        parent_id=parent.node_id,
        t=int(parent.t),
        action_type=action_type,
        child_1_id=child_1.node_id,
        child_2_id=child_2.node_id if child_2 is not None else None,
        candidate_set_complete=True,
        formation_radius_um=float(formation_radius_um),
        continuity_horizon=int(continuity_horizon),
        decision="abstain",
        decision_reason="phase0_unscored_evidence",
        semantic_score=None,
        calibrated_confidence=None,
        parent_predecessor_count=len(predecessors),
        available_features=available,
        missing_features=missing,
        **values,
    )


def extract_joint_semantic_evidence(
    graph: LineageGraph,
    *,
    parent_ids: Iterable[str] | None = None,
    formation_radius_um: float = 14.0,
    continuity_horizon: int = 2,
    local_density_radius_um: float = 10.0,
) -> JointSemanticShadowSummary:
    """Enumerate unscored parent actions without mutating the lineage graph."""
    if formation_radius_um <= 0.0:
        raise ValueError("formation_radius_um must be positive")
    if continuity_horizon < 0:
        raise ValueError("continuity_horizon must be non-negative")
    if local_density_radius_um <= 0.0:
        raise ValueError("local_density_radius_um must be positive")

    nodes, by_t, incoming, outgoing = _index_graph(graph)
    selected = (
        sorted(set(parent_ids))
        if parent_ids is not None
        else sorted(
            node.node_id
            for node in graph.detections
            if int(node.t) + 1 in by_t
        )
    )
    missing_parent_ids = [node_id for node_id in selected if node_id not in nodes]
    if missing_parent_ids:
        raise KeyError(f"Unknown parent IDs: {missing_parent_ids}")

    evidence: list[JointSemanticEvidence] = []
    for parent_id in selected:
        parent = nodes[parent_id]
        next_nodes = [
            child
            for child in by_t.get(int(parent.t) + 1, ())
            if _distance(parent, child) <= float(formation_radius_um)
        ]
        next_nodes.sort(key=lambda child: (_distance(parent, child), child.node_id))
        for child in next_nodes:
            evidence.append(
                _target_evidence(
                    graph,
                    parent,
                    child,
                    None,
                    nodes=nodes,
                    by_t=by_t,
                    incoming=incoming,
                    outgoing=outgoing,
                    formation_radius_um=formation_radius_um,
                    continuity_horizon=continuity_horizon,
                    local_density_radius_um=local_density_radius_um,
                )
            )
        for child_1, child_2 in combinations(next_nodes, 2):
            ordered = sorted((child_1, child_2), key=lambda child: child.node_id)
            evidence.append(
                _target_evidence(
                    graph,
                    parent,
                    ordered[0],
                    ordered[1],
                    nodes=nodes,
                    by_t=by_t,
                    incoming=incoming,
                    outgoing=outgoing,
                    formation_radius_um=formation_radius_um,
                    continuity_horizon=continuity_horizon,
                    local_density_radius_um=local_density_radius_um,
                )
            )
        predecessor_count = len(_valid_previous(parent, incoming, nodes))
        evidence.append(
            _no_target_evidence(
                graph,
                parent,
                "terminate",
                predecessor_count=predecessor_count,
                formation_radius_um=formation_radius_um,
                continuity_horizon=continuity_horizon,
            )
        )
        evidence.append(
            _no_target_evidence(
                graph,
                parent,
                "abstain",
                predecessor_count=predecessor_count,
                formation_radius_um=formation_radius_um,
                continuity_horizon=continuity_horizon,
            )
        )

    evidence.sort(
        key=lambda row: (
            row.t,
            row.parent_id,
            {"continue": 0, "divide": 1, "terminate": 2, "abstain": 3}[row.action_type],
            row.child_1_id or "",
            row.child_2_id or "",
        )
    )
    return JointSemanticShadowSummary(
        sample_id=graph.sample_id,
        source_nodes=len(graph.detections),
        source_edges=len(graph.edges),
        parent_count=len(selected),
        action_count=len(evidence),
        continue_count=sum(row.action_type == "continue" for row in evidence),
        divide_count=sum(row.action_type == "divide" for row in evidence),
        terminate_count=sum(row.action_type == "terminate" for row in evidence),
        abstain_count=sum(row.action_type == "abstain" for row in evidence),
        evidence=tuple(evidence),
    )


def label_division_action_official(
    evidence: JointSemanticEvidence,
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
) -> JointSemanticEvidence:
    """Label one division action through the patched official scorer on a graph copy."""
    if evidence.action_type != "divide":
        return replace(
            evidence,
            official_label="not_applicable",
            official_label_basis="non_division_action",
        )
    if evidence.child_1_id is None or evidence.child_2_id is None:
        raise ValueError("Division action requires two child IDs")

    from atabey.evaluation.official_division_metric import evaluate_official_divisions

    retained_edges = [
        edge
        for edge in graph.edges
        if edge.source_id != evidence.parent_id
    ]
    projected = LineageGraph(
        sample_id=graph.sample_id,
        detections=list(graph.detections),
        edges=[
            *retained_edges,
            LineageEdge(evidence.parent_id, evidence.child_1_id, relation="division"),
            LineageEdge(evidence.parent_id, evidence.child_2_id, relation="division"),
        ],
    )
    result = evaluate_official_divisions(projected, ground_truth)
    if evidence.parent_id in result.tp_fork_ids:
        label: OfficialLabel = "official_tp"
    elif evidence.parent_id in result.fp_fork_ids:
        label = "official_fp"
    else:
        label = "official_unsupported"
    return replace(
        evidence,
        official_label=label,
        official_label_basis="patched_official_projected_graph",
    )


def evidence_as_row(evidence: JointSemanticEvidence) -> dict[str, object]:
    row = {
        field: getattr(evidence, field)
        for field in evidence.__dataclass_fields__
        if field not in {"available_features", "missing_features"}
    }
    row["available_features"] = json.dumps(evidence.available_features)
    row["missing_features"] = json.dumps(dict(evidence.missing_features), sort_keys=True)
    return row
