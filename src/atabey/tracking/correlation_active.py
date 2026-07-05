"""Track-continuity correlation layer — active injection (Phase 2).

ISOLATED EXPERIMENTAL. This module mutates a *copy* of a lineage graph by
inserting the ``beacon_derived`` synthetic candidates proposed by the shadow layer
so they can be scored against ground truth. It is never imported by the production
path and never touches the input graph in place.

Every synthetic node carries an identifiable id prefix (:data:`SYNTHETIC_NODE_PREFIX`)
and its edges carry ``relation="beacon_recovery"`` so real vs. recovered detections
can always be separated downstream — including in the final output.

Guardrails are inherited verbatim from ``compute_correlation_shadow`` (minimum track
age, consecutive-synthetic cap, node-inflation ceiling, discount factor); this module
adds no new detection logic, only the injection wiring.
"""

from __future__ import annotations

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.tracking.correlation_shadow import (
    CorrelationShadowSummary,
    compute_correlation_shadow,
)
from atabey.types import Detection, LineageEdge, LineageGraph

SYNTHETIC_NODE_PREFIX = "synth::"
BEACON_RECOVERY_RELATION = "beacon_recovery"


def is_synthetic_node(node_id: str) -> bool:
    """True when a node id was created by active correlation injection."""

    return node_id.startswith(SYNTHETIC_NODE_PREFIX)


def _synthetic_node_id(track_id: str, frame: int) -> str:
    return f"{SYNTHETIC_NODE_PREFIX}{track_id}::t{frame}"


def build_active_graph(
    graph: LineageGraph,
    *,
    min_track_age_frames: int = 3,
    max_consecutive_synthetic: int = 2,
    discount: float = 0.6,
    max_link_distance_um: float = 9.0,
    low_detection_floor_ratio: float = 0.5,
    require_low_detection_frame: bool = False,
    node_inflation_ratio: float = 1.25,
    merge_gate_radius_um: float = 3.0,
    merge_gate_frame_window: int = 1,
    apply_merge_gate: bool = False,
) -> tuple[LineageGraph, CorrelationShadowSummary]:
    """Return a NEW graph = ``graph`` + injected synthetic candidates, and the summary.

    The input ``graph`` is never modified. Synthetic detections are tagged via node-id
    prefix and ``detection_confidence`` is set to the discounted ``would_be_a_score``.
    When ``apply_merge_gate`` is set, synthetics that collide with a real detection in
    the merge neighbourhood are suppressed by the shadow layer, so only genuine-gap
    candidates are injected.
    """

    summary = compute_correlation_shadow(
        graph,
        min_track_age_frames=min_track_age_frames,
        max_consecutive_synthetic=max_consecutive_synthetic,
        discount=discount,
        max_link_distance_um=max_link_distance_um,
        low_detection_floor_ratio=low_detection_floor_ratio,
        require_low_detection_frame=require_low_detection_frame,
        node_inflation_ratio=node_inflation_ratio,
        merge_gate_radius_um=merge_gate_radius_um,
        merge_gate_frame_window=merge_gate_frame_window,
        apply_merge_gate=apply_merge_gate,
    )

    active = LineageGraph(
        sample_id=graph.sample_id,
        detections=list(graph.detections),
        edges=list(graph.edges),
    )

    scale = DEFAULT_VOXEL_SCALE_UM
    # Map (track_id, frame) -> synthetic node id so consecutive synthetics chain.
    synthetic_ids: dict[tuple[str, int], str] = {}
    for candidate in summary.candidates:
        synthetic_ids[(candidate.track_id, candidate.frame)] = _synthetic_node_id(
            candidate.track_id, candidate.frame
        )

    for candidate in summary.candidates:
        node_id = synthetic_ids[(candidate.track_id, candidate.frame)]
        z_um, y_um, x_um = (
            candidate.predicted_z_um,
            candidate.predicted_y_um,
            candidate.predicted_x_um,
        )
        active.add_detection(
            Detection(
                node_id=node_id,
                sample_id=graph.sample_id,
                t=candidate.frame,
                z=z_um / scale.z if scale.z else 0.0,
                y=y_um / scale.y if scale.y else 0.0,
                x=x_um / scale.x if scale.x else 0.0,
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
                detection_confidence=candidate.would_be_a_score,
            )
        )
        # Source is the previous synthetic frame if present, else the confirmed leaf.
        previous_synthetic = synthetic_ids.get((candidate.track_id, candidate.frame - 1))
        source_id = previous_synthetic if previous_synthetic is not None else candidate.track_id
        active.add_edge(
            LineageEdge(
                source_id=source_id,
                target_id=node_id,
                confidence=candidate.would_be_a_score,
                relation=BEACON_RECOVERY_RELATION,
            )
        )

    return active, summary
