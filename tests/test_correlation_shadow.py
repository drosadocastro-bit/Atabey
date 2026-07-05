"""Unit tests for the shadow-only track-continuity correlation layer."""

from __future__ import annotations

from atabey.tracking.correlation_shadow import compute_correlation_shadow
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
    """Isolated single-frame detections used to control per-frame density."""

    for i in range(count):
        graph.add_detection(_det(f"fill_{t}_{i}", t, 0.0, 100.0 + i, 100.0 + i))


def _stable_track(
    graph: LineageGraph,
    prefix: str,
    frames: range,
    *,
    base: tuple[float, float, float] = (0.0, 0.0, 0.0),
    step: tuple[float, float, float] = (0.0, 1.0, 1.0),
) -> str:
    """Build a linear-motion track across ``frames``; returns the leaf node id."""

    prev: str | None = None
    leaf = ""
    for t in frames:
        node_id = f"{prefix}_{t}"
        pos = tuple(base[k] + step[k] * t for k in range(3))
        graph.add_detection(_det(node_id, t, *pos))
        if prev is not None:
            graph.add_edge(LineageEdge(source_id=prev, target_id=node_id, confidence=0.95))
        prev = node_id
        leaf = node_id
    return leaf


def test_shadow_does_not_mutate_graph() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    _stable_track(graph, "trk", range(0, 3))

    detections_before = list(graph.detections)
    edges_before = list(graph.edges)
    compute_correlation_shadow(graph)

    assert graph.detections == detections_before
    assert graph.edges == edges_before


def test_generates_synthetic_candidate_in_weak_frame_with_correct_extrapolation() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)  # weak next frame
    leaf = _stable_track(graph, "trk", range(0, 3), base=(0.0, 0.0, 0.0), step=(0.0, 2.0, 3.0))

    summary = compute_correlation_shadow(graph)

    track_candidates = [c for c in summary.candidates if c.track_id == leaf]
    assert len(track_candidates) == 1
    candidate = track_candidates[0]
    assert candidate.frame == 3
    # Linear extrapolation: leaf(t=2) + velocity(step) * 1 = t=3 position.
    assert candidate.predicted_y_um == 6.0
    assert candidate.predicted_x_um == 9.0
    assert candidate.beacon_derived is True
    assert candidate.cfar_confirmed is False


def test_discount_applied_to_would_be_score() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    leaf = _stable_track(graph, "trk", range(0, 3))

    summary = compute_correlation_shadow(
        graph, min_track_age_frames=3, discount=0.6
    )

    candidate = next(c for c in summary.candidates if c.track_id == leaf)
    # base = min(1, depth/(min_age+1)) = min(1, 3/4) = 0.75; 0.75 * 0.6 = 0.45.
    assert candidate.base_beacon_score == 0.75
    assert candidate.discount_applied == 0.6
    assert candidate.would_be_a_score == 0.45


def test_young_tracks_are_suppressed() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    # Track only 2 frames long -> depth 2 < min_track_age_frames=3.
    leaf = _stable_track(graph, "young", range(1, 3))

    summary = compute_correlation_shadow(graph, min_track_age_frames=3)

    assert all(c.track_id != leaf for c in summary.candidates)
    assert summary.suppressed_young_tracks >= 1


def test_consecutive_synthetic_cap_stops_generation() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 5, 1)  # sets last_frame=5; frames 3,4 are empty/weak
    leaf = _stable_track(graph, "trk", range(0, 3))

    summary = compute_correlation_shadow(
        graph, min_track_age_frames=3, max_consecutive_synthetic=2
    )

    track_candidates = [c for c in summary.candidates if c.track_id == leaf]
    assert len(track_candidates) == 2
    assert max(c.consecutive_synthetic_count for c in track_candidates) == 2
    assert summary.suppressed_by_consecutive_cap >= 1


def test_dense_frame_suppressed_under_optional_low_detection_gate() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 10)  # dense next frame -> not a low-detection frame
    leaf = _stable_track(graph, "trk", range(0, 3))

    # The optional stricter gate restricts recovery to whole-frame collapse frames.
    summary = compute_correlation_shadow(graph, require_low_detection_frame=True)

    assert all(c.track_id != leaf for c in summary.candidates)


def test_track_gap_triggers_by_default_even_in_dense_frame() -> None:
    # Region-level trigger: a stable track ending before the last frame is a local
    # weak-detection region, independent of whole-frame density.
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 10)  # dense next frame
    leaf = _stable_track(graph, "trk", range(0, 3))

    summary = compute_correlation_shadow(graph)  # require_low_detection_frame=False

    assert any(c.track_id == leaf for c in summary.candidates)


def test_node_inflation_ceiling_hard_stops() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)
    _stable_track(graph, "trk", range(0, 3))

    # ratio 1.0 -> budget 0 synthetic nodes allowed.
    summary = compute_correlation_shadow(graph, node_inflation_ratio=1.0)

    assert summary.synthetic_candidate_count == 0
    assert summary.hit_node_ceiling is True
    assert summary.suppressed_by_node_ceiling >= 1


def _collision_graph() -> tuple[LineageGraph, str]:
    """A track whose t=3 extrapolation (0,3,3) sits next to a real detection."""

    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    # Real (CFAR-confirmed) detection ~0.7um from the predicted synthetic at t=3.
    graph.add_detection(_det("real_double", 3, 0.0, 3.5, 3.5))
    leaf = _stable_track(graph, "trk", range(0, 3), base=(0.0, 0.0, 0.0), step=(0.0, 1.0, 1.0))
    return graph, leaf


def test_collision_flag_set_when_real_detection_is_near_but_not_suppressed_by_default() -> None:
    graph, leaf = _collision_graph()

    # Diagnostic mode: gate off -> candidate emitted, but flagged as colliding.
    summary = compute_correlation_shadow(graph, merge_gate_radius_um=3.0, apply_merge_gate=False)

    candidate = next(c for c in summary.candidates if c.track_id == leaf)
    assert candidate.collides_with_real is True
    assert summary.synthetic_collision_count == 1
    assert summary.synthetic_gap_count == 0
    assert summary.suppressed_by_merge_gate == 0
    assert summary.merge_gate_applied is False


def test_merge_gate_suppresses_synthetic_that_collides_with_real_detection() -> None:
    graph, leaf = _collision_graph()

    summary = compute_correlation_shadow(graph, merge_gate_radius_um=3.0, apply_merge_gate=True)

    assert all(c.track_id != leaf for c in summary.candidates)
    assert summary.suppressed_by_merge_gate >= 1
    assert summary.synthetic_collision_count == 1
    assert summary.merge_gate_applied is True


def test_merge_gate_allows_synthetic_in_genuine_gap() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    _add_filler(graph, 3, 1)  # weak next frame, filler is far away at (0,100,100)
    leaf = _stable_track(graph, "trk", range(0, 3), base=(0.0, 0.0, 0.0), step=(0.0, 1.0, 1.0))

    summary = compute_correlation_shadow(graph, merge_gate_radius_um=3.0, apply_merge_gate=True)

    candidate = next(c for c in summary.candidates if c.track_id == leaf)
    assert candidate.collides_with_real is False
    assert summary.synthetic_gap_count >= 1
    assert summary.suppressed_by_merge_gate == 0


def test_merge_gate_radius_is_tunable() -> None:
    graph = LineageGraph(sample_id=SAMPLE_ID)
    for t in range(3):
        _add_filler(graph, t, 10)
    # Real detection ~5um from the predicted synthetic at t=3 (0,3,3) -> (0,3,8).
    graph.add_detection(_det("real_far", 3, 0.0, 3.0, 8.0))
    leaf = _stable_track(graph, "trk", range(0, 3), base=(0.0, 0.0, 0.0), step=(0.0, 1.0, 1.0))

    # Tight radius: 5um neighbour is outside 3um -> genuine gap, injected.
    tight = compute_correlation_shadow(graph, merge_gate_radius_um=3.0, apply_merge_gate=True)
    assert any(c.track_id == leaf for c in tight.candidates)
    assert tight.suppressed_by_merge_gate == 0

    # Generous radius: 5um neighbour is inside 6um -> collision, suppressed.
    loose = compute_correlation_shadow(graph, merge_gate_radius_um=6.0, apply_merge_gate=True)
    assert all(c.track_id != leaf for c in loose.candidates)
    assert loose.suppressed_by_merge_gate >= 1
