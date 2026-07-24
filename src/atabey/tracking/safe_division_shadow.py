from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class SafeDivisionShadowConfig:
    """Frozen geometry and budget from the public 0.902 notebook."""

    candidate_parent_max_um: float = 4.66
    existing_child_max_um: float = 7.65
    sister_max_um: float = 8.5
    sister_score_weight: float = 0.15
    frame_fraction_cap: float = 0.0076
    global_fraction_cap: float = 0.00375


@dataclass(frozen=True)
class SafeDivisionShadowCandidate:
    sample_id: str
    t: int
    parent_id: str
    existing_child_id: str
    candidate_child_id: str
    parent_candidate_distance_um: float
    existing_child_distance_um: float
    sister_distance_um: float
    score: float
    frame_cap: int
    global_cap: int
    selected: bool = False
    selection_reason: str = "not_selected"


@dataclass(frozen=True)
class SafeDivisionShadowResult:
    sample_id: str
    source_node_count: int
    source_edge_count: int
    source_parent_count: int
    unowned_candidate_count: int
    proposal_count: int
    selected_count: int
    global_cap: int
    config: SafeDivisionShadowConfig
    candidates: tuple[SafeDivisionShadowCandidate, ...]


def _distance(left: Detection, right: Detection) -> float:
    return float(
        np.linalg.norm(
            np.asarray(left.position_um, dtype=float)
            - np.asarray(right.position_um, dtype=float)
        )
    )


def compute_safe_division_shadow(
    graph: LineageGraph,
    *,
    config: SafeDivisionShadowConfig | None = None,
) -> SafeDivisionShadowResult:
    """Evaluate the published post-link rule without mutating the graph."""
    config = config or SafeDivisionShadowConfig()
    if min(
        config.candidate_parent_max_um,
        config.existing_child_max_um,
        config.sister_max_um,
    ) <= 0.0:
        raise ValueError("safe-division distance bounds must be positive")
    if min(config.frame_fraction_cap, config.global_fraction_cap) < 0.0:
        raise ValueError("safe-division fraction caps must be non-negative")

    nodes = {node.node_id: node for node in graph.detections}
    by_t: dict[int, list[str]] = {}
    for node in graph.detections:
        by_t.setdefault(int(node.t), []).append(node.node_id)
    for node_ids in by_t.values():
        node_ids.sort()

    outgoing: dict[str, list[str]] = {}
    incoming: set[str] = set()
    for edge in graph.edges:
        if edge.source_id not in nodes or edge.target_id not in nodes:
            continue
        outgoing.setdefault(edge.source_id, []).append(edge.target_id)
        incoming.add(edge.target_id)
    for target_ids in outgoing.values():
        target_ids.sort()

    global_cap = max(
        1,
        int(round(max(1, len(graph.edges)) * config.global_fraction_cap)),
    )
    used_targets: set[str] = set()
    selected_total = 0
    all_candidates: list[SafeDivisionShadowCandidate] = []
    source_parents: set[str] = set()
    unowned_candidates: set[str] = set()

    for t in sorted(by_t):
        child_ids = by_t.get(t + 1, [])
        if not child_ids:
            continue
        source_ids = [
            node_id
            for node_id in by_t[t]
            if len(outgoing.get(node_id, ())) == 1
        ]
        candidate_ids = [
            node_id
            for node_id in child_ids
            if node_id not in incoming and node_id not in used_targets
        ]
        source_parents.update(source_ids)
        unowned_candidates.update(candidate_ids)
        if not source_ids or not candidate_ids:
            continue

        frame_cap = max(1, int(round(len(source_ids) * config.frame_fraction_cap)))
        proposals: list[SafeDivisionShadowCandidate] = []
        for parent_id in source_ids:
            parent = nodes[parent_id]
            existing_child_id = outgoing[parent_id][0]
            existing_child = nodes.get(existing_child_id)
            if existing_child is None or int(existing_child.t) != t + 1:
                continue
            existing_distance = _distance(parent, existing_child)
            if existing_distance > config.existing_child_max_um:
                continue
            for candidate_id in candidate_ids:
                candidate = nodes[candidate_id]
                parent_distance = _distance(parent, candidate)
                if parent_distance > config.candidate_parent_max_um:
                    continue
                sister_distance = _distance(existing_child, candidate)
                if sister_distance > config.sister_max_um:
                    continue
                proposals.append(
                    SafeDivisionShadowCandidate(
                        sample_id=graph.sample_id,
                        t=t,
                        parent_id=parent_id,
                        existing_child_id=existing_child_id,
                        candidate_child_id=candidate_id,
                        parent_candidate_distance_um=parent_distance,
                        existing_child_distance_um=existing_distance,
                        sister_distance_um=sister_distance,
                        score=parent_distance
                        + config.sister_score_weight * sister_distance,
                        frame_cap=frame_cap,
                        global_cap=global_cap,
                    )
                )

        proposals.sort(
            key=lambda row: (
                row.score,
                row.parent_id,
                row.candidate_child_id,
                row.existing_child_id,
            )
        )
        selected_this_frame = 0
        for proposal in proposals:
            if selected_total >= global_cap:
                candidate = replace(
                    proposal,
                    selection_reason="global_cap_reached",
                )
            elif selected_this_frame >= frame_cap:
                candidate = replace(
                    proposal,
                    selection_reason="frame_cap_reached",
                )
            elif proposal.candidate_child_id in incoming:
                candidate = replace(
                    proposal,
                    selection_reason="candidate_already_owned",
                )
            elif proposal.candidate_child_id in used_targets:
                candidate = replace(
                    proposal,
                    selection_reason="candidate_claimed_by_better_proposal",
                )
            else:
                candidate = replace(
                    proposal,
                    selected=True,
                    selection_reason="selected",
                )
                used_targets.add(proposal.candidate_child_id)
                selected_total += 1
                selected_this_frame += 1
            all_candidates.append(candidate)

    return SafeDivisionShadowResult(
        sample_id=graph.sample_id,
        source_node_count=len(graph.detections),
        source_edge_count=len(graph.edges),
        source_parent_count=len(source_parents),
        unowned_candidate_count=len(unowned_candidates),
        proposal_count=len(all_candidates),
        selected_count=selected_total,
        global_cap=global_cap,
        config=config,
        candidates=tuple(all_candidates),
    )


def project_safe_division_shadow(
    graph: LineageGraph,
    shadow: SafeDivisionShadowResult,
) -> LineageGraph:
    """Return a graph copy with selected second-child edges added."""
    if graph.sample_id != shadow.sample_id:
        raise ValueError("graph and shadow sample IDs do not match")
    existing = {(edge.source_id, edge.target_id) for edge in graph.edges}
    added = [
        LineageEdge(
            candidate.parent_id,
            candidate.candidate_child_id,
            relation="division",
        )
        for candidate in shadow.candidates
        if candidate.selected
        and (candidate.parent_id, candidate.candidate_child_id) not in existing
    ]
    return LineageGraph(
        sample_id=graph.sample_id,
        detections=list(graph.detections),
        edges=[*graph.edges, *added],
    )
