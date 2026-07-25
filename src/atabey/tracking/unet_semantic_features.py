from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import dist
from typing import Any, Iterable

import numpy as np
from scipy.spatial import cKDTree

from atabey.tracking.unet_action_availability import (
    ActionEnumeration,
    AnchoredDivisionAction,
    UnetShadowPeak,
)
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class EventFeatureContext:
    sample_id: str
    parent_t: int
    nodes: dict[str, Detection]
    incoming: dict[str, tuple[str, ...]]
    parent_peaks: dict[str, UnetShadowPeak]
    daughter_peaks: dict[str, UnetShadowPeak]
    parent_density_10um: dict[str, int]
    daughter_density_10um: dict[str, int]
    parent_competing_anchor_margin_um: dict[str, float | None]
    daughter_competing_parent_margin_um: dict[tuple[str, str], float | None]


def semantic_action_id(action: AnchoredDivisionAction) -> str:
    payload = "|".join(
        (
            action.sample_id,
            str(action.t),
            action.anchor_id,
            action.parent.peak_id,
            action.child_1.peak_id,
            action.child_2.peak_id,
        )
    )
    return "v22a:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def build_event_feature_context(
    graph: LineageGraph,
    peaks: Iterable[UnetShadowPeak],
    enumeration: ActionEnumeration,
    *,
    density_radius_um: float = 10.0,
) -> EventFeatureContext:
    if density_radius_um <= 0.0:
        raise ValueError("density_radius_um must be positive")

    peak_list = [
        peak
        for peak in peaks
        if peak.sample_id == graph.sample_id
        and peak.t in {enumeration.t, enumeration.t + 1}
    ]
    parent_peaks = {
        peak.peak_id: peak for peak in peak_list if peak.t == enumeration.t
    }
    daughter_peaks = {
        peak.peak_id: peak for peak in peak_list if peak.t == enumeration.t + 1
    }
    nodes = {node.node_id: node for node in graph.detections}
    incoming_lists: dict[str, list[str]] = {}
    for edge in graph.edges:
        incoming_lists.setdefault(edge.target_id, []).append(edge.source_id)
    incoming = {
        node_id: tuple(sorted(source_ids))
        for node_id, source_ids in incoming_lists.items()
    }

    parent_density = _density_counts(list(parent_peaks.values()), density_radius_um)
    daughter_density = _density_counts(
        list(daughter_peaks.values()), density_radius_um
    )

    anchors = sorted(
        (
            node
            for node in graph.detections
            if int(node.t) == int(enumeration.t) - 1
        ),
        key=lambda node: node.node_id,
    )
    anchor_predictions = [
        _predict_anchor_position(anchor, nodes, incoming) for anchor in anchors
    ]
    parent_margin: dict[str, float | None] = {}
    if anchor_predictions:
        anchor_tree = cKDTree(np.asarray(anchor_predictions, dtype=float))
        for parent in parent_peaks.values():
            distances, _ = anchor_tree.query(
                np.asarray(parent.position_um, dtype=float),
                k=min(2, len(anchor_predictions)),
            )
            distance_values = np.atleast_1d(distances).astype(float)
            parent_margin[parent.peak_id] = (
                float(distance_values[1] - distance_values[0])
                if len(distance_values) >= 2
                else None
            )
    else:
        parent_margin = {peak_id: None for peak_id in parent_peaks}

    parent_values = list(parent_peaks.values())
    parent_tree = (
        cKDTree(np.asarray([peak.position_um for peak in parent_values], dtype=float))
        if parent_values
        else None
    )
    daughter_margin: dict[tuple[str, str], float | None] = {}
    for parent in parent_values:
        for daughter in daughter_peaks.values():
            if parent_tree is None or len(parent_values) < 2:
                daughter_margin[(parent.peak_id, daughter.peak_id)] = None
                continue
            distances, indices = parent_tree.query(
                np.asarray(daughter.position_um, dtype=float),
                k=min(3, len(parent_values)),
            )
            alternatives = sorted(
                float(distance_um)
                for distance_um, index in zip(
                    np.atleast_1d(distances),
                    np.atleast_1d(indices),
                    strict=True,
                )
                if parent_values[int(index)].peak_id != parent.peak_id
            )
            daughter_margin[(parent.peak_id, daughter.peak_id)] = (
                alternatives[0] - dist(parent.position_um, daughter.position_um)
                if alternatives
                else None
            )

    return EventFeatureContext(
        sample_id=graph.sample_id,
        parent_t=int(enumeration.t),
        nodes=nodes,
        incoming=incoming,
        parent_peaks=parent_peaks,
        daughter_peaks=daughter_peaks,
        parent_density_10um=parent_density,
        daughter_density_10um=daughter_density,
        parent_competing_anchor_margin_um=parent_margin,
        daughter_competing_parent_margin_um=daughter_margin,
    )


def division_action_feature_row(
    action: AnchoredDivisionAction,
    context: EventFeatureContext,
) -> dict[str, Any]:
    if action.sample_id != context.sample_id or action.t != context.parent_t:
        raise ValueError("Action does not belong to the feature context")

    anchor = context.nodes.get(action.anchor_id)
    if anchor is None:
        raise KeyError(f"Unknown anchor: {action.anchor_id}")
    parent = action.parent
    child_1 = action.child_1
    child_2 = action.child_2

    parent_position = np.asarray(parent.position_um, dtype=float)
    anchor_position = np.asarray(anchor.position_um, dtype=float)
    child_1_position = np.asarray(child_1.position_um, dtype=float)
    child_2_position = np.asarray(child_2.position_um, dtype=float)
    parent_step = parent_position - anchor_position
    vector_1 = child_1_position - parent_position
    vector_2 = child_2_position - parent_position
    distance_1 = float(np.linalg.norm(vector_1))
    distance_2 = float(np.linalg.norm(vector_2))
    midpoint = 0.5 * (child_1_position + child_2_position)
    predicted_midpoint = parent_position + parent_step

    predecessor = _nearest_predecessor(anchor, context.nodes, context.incoming)
    anchor_speed = (
        dist(predecessor.position_um, anchor.position_um)
        if predecessor is not None
        else None
    )
    split_axis = child_1_position - child_2_position

    values: dict[str, float | int | None] = {
        "anchor_prediction_distance_um": float(
            action.anchor_prediction_distance_um
        ),
        "anchor_speed_um_per_frame": anchor_speed,
        "anchor_to_parent_distance_um": float(np.linalg.norm(parent_step)),
        "child_1_distance_um": distance_1,
        "child_2_distance_um": distance_2,
        "child_distance_ratio": (
            max(distance_1, distance_2) / min(distance_1, distance_2)
            if min(distance_1, distance_2) > 1e-9
            else None
        ),
        "child_separation_um": float(np.linalg.norm(child_1_position - child_2_position)),
        "split_angle_deg": _angle(vector_1, vector_2),
        "pair_midpoint_parent_offset_um": float(np.linalg.norm(midpoint - parent_position)),
        "pair_midpoint_prediction_error_um": float(
            np.linalg.norm(midpoint - predicted_midpoint)
        ),
        "split_axis_parent_step_alignment_deg": _undirected_angle(
            split_axis, parent_step
        ),
        "parent_confidence": parent.confidence,
        "child_1_confidence": child_1.confidence,
        "child_2_confidence": child_2.confidence,
        "mean_detection_confidence": _mean_optional(
            parent.confidence,
            child_1.confidence,
            child_2.confidence,
        ),
        "minimum_detection_confidence": _min_optional(
            parent.confidence,
            child_1.confidence,
            child_2.confidence,
        ),
        "parent_density_10um": context.parent_density_10um.get(parent.peak_id),
        "child_1_density_10um": context.daughter_density_10um.get(child_1.peak_id),
        "child_2_density_10um": context.daughter_density_10um.get(child_2.peak_id),
        "parent_competing_anchor_margin_um": (
            context.parent_competing_anchor_margin_um.get(parent.peak_id)
        ),
        "child_1_competing_parent_margin_um": (
            context.daughter_competing_parent_margin_um.get(
                (parent.peak_id, child_1.peak_id)
            )
        ),
        "child_2_competing_parent_margin_um": (
            context.daughter_competing_parent_margin_um.get(
                (parent.peak_id, child_2.peak_id)
            )
        ),
        "immediate_separation_growth_um": None,
        "max_branch_axis_drift_deg": None,
        "volume_conservation_error": None,
        "intensity_conservation_error": None,
    }
    reasons = {
        "anchor_speed_um_per_frame": "no_anchor_history",
        "child_distance_ratio": "zero_parent_child_distance",
        "split_angle_deg": "zero_parent_child_vector",
        "split_axis_parent_step_alignment_deg": "zero_split_or_parent_step_vector",
        "parent_competing_anchor_margin_um": "fewer_than_two_anchor_claims",
        "child_1_competing_parent_margin_um": "no_competing_parent_peak",
        "child_2_competing_parent_margin_um": "no_competing_parent_peak",
        "immediate_separation_growth_um": "future_unet_frames_not_exported",
        "max_branch_axis_drift_deg": "future_unet_frames_not_exported",
        "volume_conservation_error": "unet_peak_has_no_component_volume",
        "intensity_conservation_error": "unet_peak_has_no_intensity_measurement",
    }
    available = sorted(name for name, value in values.items() if value is not None)
    missing = {
        name: reasons.get(name, "unavailable")
        for name, value in values.items()
        if value is None
    }
    return {
        "action_id": semantic_action_id(action),
        "sample_id": action.sample_id,
        "t": action.t,
        "action_type": "divide",
        "anchor_id": action.anchor_id,
        "parent_peak_id": parent.peak_id,
        "child_1_peak_id": child_1.peak_id,
        "child_2_peak_id": child_2.peak_id,
        **values,
        "available_features": json.dumps(available, separators=(",", ":")),
        "missing_features": json.dumps(missing, sort_keys=True, separators=(",", ":")),
    }


def _density_counts(
    peaks: list[UnetShadowPeak],
    radius_um: float,
) -> dict[str, int]:
    if not peaks:
        return {}
    tree = cKDTree(np.asarray([peak.position_um for peak in peaks], dtype=float))
    neighborhoods = tree.query_ball_tree(tree, r=float(radius_um))
    return {
        peak.peak_id: len(neighbors)
        for peak, neighbors in zip(peaks, neighborhoods, strict=True)
    }


def _predict_anchor_position(
    anchor: Detection,
    nodes: dict[str, Detection],
    incoming: dict[str, tuple[str, ...]],
) -> tuple[float, float, float]:
    predecessor = _nearest_predecessor(anchor, nodes, incoming)
    if predecessor is None:
        return anchor.position_um
    return tuple(
        2.0 * current - previous
        for current, previous in zip(
            anchor.position_um,
            predecessor.position_um,
            strict=True,
        )
    )


def _nearest_predecessor(
    anchor: Detection,
    nodes: dict[str, Detection],
    incoming: dict[str, tuple[str, ...]],
) -> Detection | None:
    predecessors = [
        nodes[node_id]
        for node_id in incoming.get(anchor.node_id, ())
        if node_id in nodes and int(nodes[node_id].t) == int(anchor.t) - 1
    ]
    return (
        min(
            predecessors,
            key=lambda node: (dist(node.position_um, anchor.position_um), node.node_id),
        )
        if predecessors
        else None
    )


def _angle(left: np.ndarray, right: np.ndarray) -> float | None:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-9 or right_norm <= 1e-9:
        return None
    cosine = float(np.dot(left, right) / (left_norm * right_norm))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def _undirected_angle(left: np.ndarray, right: np.ndarray) -> float | None:
    angle = _angle(left, right)
    return min(angle, 180.0 - angle) if angle is not None else None


def _mean_optional(*values: float | None) -> float | None:
    return (
        float(np.mean([float(value) for value in values]))
        if all(value is not None for value in values)
        else None
    )


def _min_optional(*values: float | None) -> float | None:
    return (
        min(float(value) for value in values)
        if all(value is not None for value in values)
        else None
    )
