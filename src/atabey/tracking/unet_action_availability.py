from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import dist
from typing import Iterable, Sequence

import numpy as np
from scipy.spatial import cKDTree

from atabey.io.geff_reader import SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class UnetShadowPeak:
    peak_id: str
    sample_id: str
    t: int
    z_um: float
    y_um: float
    x_um: float
    confidence: float | None = None

    @property
    def position_um(self) -> tuple[float, float, float]:
        return self.z_um, self.y_um, self.x_um


@dataclass(frozen=True)
class AnchoredDivisionAction:
    sample_id: str
    t: int
    anchor_id: str
    parent: UnetShadowPeak
    child_1: UnetShadowPeak
    child_2: UnetShadowPeak
    anchor_prediction_distance_um: float


@dataclass(frozen=True)
class ActionEnumeration:
    sample_id: str
    t: int
    anchor_count: int
    parent_peak_count: int
    anchored_parent_count: int
    division_action_count: int
    actions: tuple[AnchoredDivisionAction, ...]


def _incoming(graph: LineageGraph) -> dict[str, list[str]]:
    incoming: dict[str, list[str]] = {}
    for edge in graph.edges:
        incoming.setdefault(edge.target_id, []).append(edge.source_id)
    return incoming


def _predict_anchor_position(
    anchor: Detection,
    nodes: dict[str, Detection],
    incoming: dict[str, list[str]],
) -> tuple[float, float, float]:
    predecessors = [
        nodes[node_id]
        for node_id in incoming.get(anchor.node_id, ())
        if node_id in nodes and int(nodes[node_id].t) == int(anchor.t) - 1
    ]
    if not predecessors:
        return anchor.position_um
    predecessor = min(
        predecessors,
        key=lambda node: (dist(node.position_um, anchor.position_um), node.node_id),
    )
    return tuple(
        2.0 * current - previous
        for current, previous in zip(
            anchor.position_um,
            predecessor.position_um,
            strict=True,
        )
    )


def enumerate_anchored_division_actions(
    graph: LineageGraph,
    peaks: Iterable[UnetShadowPeak],
    *,
    parent_t: int,
    anchor_radius_um: float = 14.0,
    formation_radius_um: float = 14.0,
) -> ActionEnumeration:
    """Form U-Net forks around prior-frame track anchors without GT selection."""

    if anchor_radius_um <= 0.0 or formation_radius_um <= 0.0:
        raise ValueError("Action-formation radii must be positive")

    peak_list = [
        peak
        for peak in peaks
        if peak.sample_id == graph.sample_id
        and peak.t in {int(parent_t), int(parent_t) + 1}
    ]
    parent_peaks = sorted(
        (peak for peak in peak_list if peak.t == int(parent_t)),
        key=lambda peak: peak.peak_id,
    )
    daughter_peaks = sorted(
        (peak for peak in peak_list if peak.t == int(parent_t) + 1),
        key=lambda peak: peak.peak_id,
    )

    nodes = {node.node_id: node for node in graph.detections}
    incoming = _incoming(graph)
    anchors = sorted(
        (node for node in graph.detections if int(node.t) == int(parent_t) - 1),
        key=lambda node: node.node_id,
    )
    predictions = [
        _predict_anchor_position(anchor, nodes, incoming)
        for anchor in anchors
    ]
    prediction_tree = cKDTree(np.asarray(predictions, dtype=float)) if predictions else None
    daughter_tree = (
        cKDTree(np.asarray([peak.position_um for peak in daughter_peaks], dtype=float))
        if daughter_peaks
        else None
    )

    parent_claims: dict[str, tuple[float, str]] = {}
    if prediction_tree is not None:
        for parent in parent_peaks:
            claim_indices = prediction_tree.query_ball_point(
                np.asarray(parent.position_um, dtype=float),
                r=float(anchor_radius_um),
            )
            claims = sorted(
                (
                    dist(parent.position_um, predictions[index]),
                    anchors[index].node_id,
                )
                for index in claim_indices
            )
            if claims:
                parent_claims[parent.peak_id] = claims[0]

    actions: list[AnchoredDivisionAction] = []
    for parent in parent_peaks:
        claim = parent_claims.get(parent.peak_id)
        if claim is None or daughter_tree is None:
            continue
        daughter_indices = daughter_tree.query_ball_point(
            np.asarray(parent.position_um, dtype=float),
            r=float(formation_radius_um),
        )
        nearby_daughters = [daughter_peaks[index] for index in sorted(daughter_indices)]
        for child_1, child_2 in combinations(nearby_daughters, 2):
            actions.append(
                AnchoredDivisionAction(
                    sample_id=graph.sample_id,
                    t=int(parent_t),
                    anchor_id=claim[1],
                    parent=parent,
                    child_1=child_1,
                    child_2=child_2,
                    anchor_prediction_distance_um=float(claim[0]),
                )
            )

    actions.sort(
        key=lambda action: (
            action.parent.peak_id,
            action.child_1.peak_id,
            action.child_2.peak_id,
        )
    )
    return ActionEnumeration(
        sample_id=graph.sample_id,
        t=int(parent_t),
        anchor_count=len(anchors),
        parent_peak_count=len(parent_peaks),
        anchored_parent_count=len(parent_claims),
        division_action_count=len(actions),
        actions=tuple(actions),
    )


def action_matches_registered_division(
    action: AnchoredDivisionAction,
    *,
    parent_position_um: Sequence[float],
    daughter_positions_um: tuple[Sequence[float], Sequence[float]],
    match_radius_um: float = 7.0,
) -> bool:
    """Use GT only as an evaluation label after action formation is complete."""

    if dist(action.parent.position_um, parent_position_um) > match_radius_um:
        return False
    direct = (
        dist(action.child_1.position_um, daughter_positions_um[0])
        <= match_radius_um
        and dist(action.child_2.position_um, daughter_positions_um[1])
        <= match_radius_um
    )
    swapped = (
        dist(action.child_1.position_um, daughter_positions_um[1])
        <= match_radius_um
        and dist(action.child_2.position_um, daughter_positions_um[0])
        <= match_radius_um
    )
    return direct or swapped


def evaluate_action_as_official_fork(
    action: AnchoredDivisionAction,
    ground_truth: SparseGroundTruthGraph,
    *,
    gt_parent_id: int,
) -> bool:
    """Project one isolated fork through the patched official scorer."""

    from atabey.evaluation.official_division_metric import evaluate_official_divisions

    def detection(peak: UnetShadowPeak) -> Detection:
        return Detection(
            node_id=peak.peak_id,
            sample_id=peak.sample_id,
            t=peak.t,
            z=peak.z_um,
            y=peak.y_um,
            x=peak.x_um,
            z_um=peak.z_um,
            y_um=peak.y_um,
            x_um=peak.x_um,
            detection_confidence=peak.confidence,
        )

    projected = LineageGraph(
        sample_id=action.sample_id,
        detections=[
            detection(action.parent),
            detection(action.child_1),
            detection(action.child_2),
        ],
        edges=[
            LineageEdge(
                action.parent.peak_id,
                action.child_1.peak_id,
                relation="division",
            ),
            LineageEdge(
                action.parent.peak_id,
                action.child_2.peak_id,
                relation="division",
            ),
        ],
    )
    result = evaluate_official_divisions(projected, ground_truth)
    return (
        result.gt_scores.get(int(gt_parent_id), 0) == 1
        and action.parent.peak_id in result.tp_fork_ids
    )
