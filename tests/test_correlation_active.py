"""Unit tests for the active correlation injection (Phase 2)."""

from __future__ import annotations

from atabey.tracking.correlation_active import (
    BEACON_RECOVERY_RELATION,
    build_active_graph,
    is_synthetic_node,
)
from atabey.types import Detection, LineageEdge, LineageGraph

SAMPLE_ID = "merged_6bba_test"


def _det(node_id: str, t: int, z: float, y: float, x: float) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id=SAMPLE_ID,
        t=t,
        z=z,
        y=y,
        x=x,
        z_um=z,
        y_um=y,
        x_um=x,
        detection_confidence=0.9,
    )


def _add_filler(graph: LineageGraph, t: int, count: int) -> None:
    for i in range(count):
        graph.add_detection(_det(f"fill_{t}_{i}", t, 0.0, 100.0 + i, 100.0 + i))


def _stable_track(graph: LineageGraph, prefix: str, frames: range) -> str:
    prev: str | None = None
    leaf = ""
    for t in frames:
        node_id = f"{prefix}_{t}"
        graph.add_detection(_det(node_id, t, 0.0, float(t), float(t)))
        if prev is not None:
            graph.add_edge(LineageEdge(source_id=prev, target_id=node_id, confidence=0.95))
        prev = node_id
        leaf = node_id
    return leaf


def test_injection_does_not_mutate_input_graph() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    _stable_track(graph, "trk", range(0, 3))

    nodes_before = len(graph.detections)
    edges_before = len(graph.edges)
    active, summary = build_active_graph(graph)

    assert len(graph.detections) == nodes_before
    assert len(graph.edges) == edges_before
    assert len(active.detections) == nodes_before + summary.synthetic_candidate_count
    assert len(active.edges) == edges_before + summary.synthetic_candidate_count


def test_injected_nodes_are_tagged_and_confidence_is_discounted() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    _stable_track(graph, "trk", range(0, 3))

    active, summary = build_active_graph(graph, discount=0.6)

    synthetic_nodes = [d for d in active.detections if is_synthetic_node(d.node_id)]
    assert len(synthetic_nodes) == summary.synthetic_candidate_count
    for node in synthetic_nodes:
        # base = min(1, depth/(min_age+1)) = 3/4 = 0.75; discounted = 0.45.
        assert node.detection_confidence == 0.45
    synthetic_edges = [e for e in active.edges if e.relation == BEACON_RECOVERY_RELATION]
    assert len(synthetic_edges) == summary.synthetic_candidate_count


def test_consecutive_synthetics_chain_from_leaf() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 5, 1)  # last_frame=5, frames 3,4 weak
    leaf = _stable_track(graph, "trk", range(0, 3))

    active, summary = build_active_graph(
        graph, min_track_age_frames=3, max_consecutive_synthetic=2
    )

    beacon_edges = {
        (e.source_id, e.target_id)
        for e in active.edges
        if e.relation == BEACON_RECOVERY_RELATION
    }
    # First synthetic links from the confirmed leaf; second chains from the first.
    synth_t3 = f"synth::{leaf}::t3"
    synth_t4 = f"synth::{leaf}::t4"
    assert (leaf, synth_t3) in beacon_edges
    assert (synth_t3, synth_t4) in beacon_edges


def test_young_track_produces_no_injection() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    _stable_track(graph, "young", range(1, 3))  # depth 2 < min age 3

    active, summary = build_active_graph(graph, min_track_age_frames=3)

    assert summary.synthetic_candidate_count == 0
    assert not any(is_synthetic_node(d.node_id) for d in active.detections)


def test_node_ceiling_blocks_injection() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    _stable_track(graph, "trk", range(0, 3))

    active, summary = build_active_graph(graph, node_inflation_ratio=1.0)

    assert summary.synthetic_candidate_count == 0
    assert len(active.detections) == len(graph.detections)
