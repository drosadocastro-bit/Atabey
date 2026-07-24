from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from atabey.io.geff_reader import (
    GroundTruthNode,
    SparseGroundTruthGraph,
)
from atabey.tracking.joint_semantic_shadow import (
    JointSemanticEvidence,
    extract_joint_semantic_evidence,
    label_division_action_official,
)
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class DivisionPositiveAvailability:
    sample_id: str
    gt_parent_id: int
    gt_child_ids: tuple[int, ...]
    t: int
    parent_candidate_count: int
    daughter_1_candidate_count: int
    daughter_2_candidate_count: int
    candidate_action_count: int
    official_attempt_count: int
    status: str
    canonical_parent_id: str | None
    canonical_child_1_id: str | None
    canonical_child_2_id: str | None
    canonical_role_distance_um: float | None
    canonical_evidence: JointSemanticEvidence | None

    @property
    def official_positive(self) -> bool:
        return self.status == "official_positive"


def _distance_positions(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return float(
        np.linalg.norm(
            np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
        )
    )


def _indices(
    ground_truth: SparseGroundTruthGraph,
) -> tuple[
    dict[int, GroundTruthNode],
    dict[int, list[int]],
    dict[int, list[int]],
]:
    nodes = {int(node.node_id): node for node in ground_truth.nodes}
    outgoing: dict[int, list[int]] = {}
    incoming: dict[int, list[int]] = {}
    for source, target in ground_truth.edges:
        outgoing.setdefault(int(source), []).append(int(target))
        incoming.setdefault(int(target), []).append(int(source))
    for adjacency in (outgoing, incoming):
        for node_ids in adjacency.values():
            node_ids.sort()
    return nodes, outgoing, incoming


def gt_division_parent_ids(
    ground_truth: SparseGroundTruthGraph,
) -> tuple[int, ...]:
    _nodes, outgoing, _incoming = _indices(ground_truth)
    return tuple(
        sorted(
            parent_id
            for parent_id, child_ids in outgoing.items()
            if len(child_ids) >= 2
        )
    )


def gt_division_window(
    ground_truth: SparseGroundTruthGraph,
    gt_parent_id: int,
) -> SparseGroundTruthGraph:
    """Return the patched host's parent/divider/children/grandchildren window."""
    nodes, outgoing, incoming = _indices(ground_truth)
    if gt_parent_id not in nodes:
        raise KeyError(f"Unknown GT parent ID: {gt_parent_id}")
    children = outgoing.get(gt_parent_id, [])
    if len(children) < 2:
        raise ValueError(f"GT node {gt_parent_id} is not a division")
    keep = {
        gt_parent_id,
        *incoming.get(gt_parent_id, []),
        *children,
        *(
            grandchild
            for child in children
            for grandchild in outgoing.get(child, [])
        ),
    }
    return SparseGroundTruthGraph(
        sample_id=ground_truth.sample_id,
        nodes=[node for node in ground_truth.nodes if int(node.node_id) in keep],
        edges=[
            (int(source), int(target))
            for source, target in ground_truth.edges
            if int(source) in keep and int(target) in keep
        ],
        estimated_number_of_nodes=None,
    )


def _detections_by_t(graph: LineageGraph) -> dict[int, list[Detection]]:
    by_t: dict[int, list[Detection]] = {}
    for detection in graph.detections:
        by_t.setdefault(int(detection.t), []).append(detection)
    for detections in by_t.values():
        detections.sort(key=lambda detection: detection.node_id)
    return by_t


def _nearby(
    detections: list[Detection],
    target: GroundTruthNode,
    radius_um: float,
) -> list[tuple[Detection, float]]:
    nearby = [
        (
            detection,
            _distance_positions(detection.position_um, target.position_um),
        )
        for detection in detections
    ]
    return sorted(
        (
            (detection, distance)
            for detection, distance in nearby
            if distance <= float(radius_um)
        ),
        key=lambda item: (item[1], item[0].node_id),
    )


def audit_gt_division_positive_availability(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    gt_parent_id: int,
    *,
    match_radius_um: float = 7.0,
    formation_radius_um: float = 14.0,
    continuity_horizon: int = 2,
) -> DivisionPositiveAvailability:
    """Find one canonical action that is a patched-official TP for one GT division."""
    if match_radius_um <= 0.0:
        raise ValueError("match_radius_um must be positive")
    nodes, outgoing, _incoming = _indices(ground_truth)
    parent = nodes.get(int(gt_parent_id))
    if parent is None:
        raise KeyError(f"Unknown GT parent ID: {gt_parent_id}")
    gt_child_ids = tuple(outgoing.get(int(gt_parent_id), ()))
    if len(gt_child_ids) < 2:
        raise ValueError(f"GT node {gt_parent_id} is not a division")

    by_t = _detections_by_t(graph)
    parent_candidates = _nearby(
        by_t.get(int(parent.t), []),
        parent,
        match_radius_um,
    )
    child_role_candidates = [
        _nearby(
            by_t.get(int(nodes[child_id].t), []),
            nodes[child_id],
            match_radius_um,
        )
        for child_id in gt_child_ids
    ]
    first_count = len(child_role_candidates[0])
    second_count = len(child_role_candidates[1])
    if not parent_candidates:
        return DivisionPositiveAvailability(
            graph.sample_id,
            int(gt_parent_id),
            gt_child_ids,
            int(parent.t),
            0,
            first_count,
            second_count,
            0,
            0,
            "no_parent_detection_within_7um",
            None,
            None,
            None,
            None,
            None,
        )
    if sum(bool(candidates) for candidates in child_role_candidates) < 2:
        return DivisionPositiveAvailability(
            graph.sample_id,
            int(gt_parent_id),
            gt_child_ids,
            int(parent.t),
            len(parent_candidates),
            first_count,
            second_count,
            0,
            0,
            "fewer_than_two_daughter_lineages_within_7um",
            None,
            None,
            None,
            None,
            None,
        )

    candidate_specs: dict[
        tuple[str, str, str],
        tuple[float, Detection, Detection, Detection],
    ] = {}
    for left_role, right_role in combinations(range(len(gt_child_ids)), 2):
        for parent_detection, parent_distance in parent_candidates:
            for child_1, child_1_distance in child_role_candidates[left_role]:
                for child_2, child_2_distance in child_role_candidates[right_role]:
                    if child_1.node_id == child_2.node_id:
                        continue
                    if (
                        _distance_positions(
                            parent_detection.position_um,
                            child_1.position_um,
                        )
                        > formation_radius_um
                        or _distance_positions(
                            parent_detection.position_um,
                            child_2.position_um,
                        )
                        > formation_radius_um
                    ):
                        continue
                    ordered_children = sorted(
                        (child_1, child_2),
                        key=lambda detection: detection.node_id,
                    )
                    key = (
                        parent_detection.node_id,
                        ordered_children[0].node_id,
                        ordered_children[1].node_id,
                    )
                    role_distance = (
                        parent_distance
                        + child_1_distance
                        + child_2_distance
                    )
                    previous = candidate_specs.get(key)
                    if previous is None or role_distance < previous[0]:
                        candidate_specs[key] = (
                            role_distance,
                            parent_detection,
                            ordered_children[0],
                            ordered_children[1],
                        )

    if not candidate_specs:
        return DivisionPositiveAvailability(
            graph.sample_id,
            int(gt_parent_id),
            gt_child_ids,
            int(parent.t),
            len(parent_candidates),
            first_count,
            second_count,
            0,
            0,
            "no_pair_inside_14um_formation_radius",
            None,
            None,
            None,
            None,
            None,
        )

    evidence_by_parent: dict[
        str,
        dict[frozenset[str], JointSemanticEvidence],
    ] = {}
    attempts = 0
    window = gt_division_window(ground_truth, gt_parent_id)
    ordered_specs = sorted(
        candidate_specs.values(),
        key=lambda item: (
            item[0],
            item[1].node_id,
            item[2].node_id,
            item[3].node_id,
        ),
    )
    for role_distance, parent_detection, child_1, child_2 in ordered_specs:
        if parent_detection.node_id not in evidence_by_parent:
            shadow = extract_joint_semantic_evidence(
                graph,
                parent_ids=[parent_detection.node_id],
                formation_radius_um=formation_radius_um,
                continuity_horizon=continuity_horizon,
            )
            evidence_by_parent[parent_detection.node_id] = {
                frozenset((row.child_1_id, row.child_2_id)): row
                for row in shadow.evidence
                if row.action_type == "divide"
                and row.child_1_id is not None
                and row.child_2_id is not None
            }
        evidence = evidence_by_parent[parent_detection.node_id].get(
            frozenset((child_1.node_id, child_2.node_id))
        )
        if evidence is None:
            continue
        attempts += 1
        labeled = label_division_action_official(
            evidence,
            graph,
            window,
        )
        if labeled.official_label == "official_tp":
            return DivisionPositiveAvailability(
                graph.sample_id,
                int(gt_parent_id),
                gt_child_ids,
                int(parent.t),
                len(parent_candidates),
                first_count,
                second_count,
                len(candidate_specs),
                attempts,
                "official_positive",
                parent_detection.node_id,
                child_1.node_id,
                child_2.node_id,
                float(role_distance),
                labeled,
            )

    return DivisionPositiveAvailability(
        graph.sample_id,
        int(gt_parent_id),
        gt_child_ids,
        int(parent.t),
        len(parent_candidates),
        first_count,
        second_count,
        len(candidate_specs),
        attempts,
        "projected_actions_not_official_tp",
        None,
        None,
        None,
        None,
        None,
    )
