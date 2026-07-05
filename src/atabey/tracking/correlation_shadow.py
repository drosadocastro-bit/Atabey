"""Track-continuity correlation layer (shadow mode).

ISOLATED EXPERIMENTAL / SHADOW-ONLY. This module never mutates a lineage graph
and is never imported by the production path. It measures how many detections a
PSR/SSR-style track-continuity correlation layer *could* recover in weak/zero-CFAR
frames, by extrapolating stable tracks into detection gaps and scoring the
resulting synthetic candidates with a discounted link score.

Design mirrors the reinforcement/latent-recovery discipline already in the repo:

- Trigger only where CFAR detection is weak or zero (per-frame low-detection gate
  derived from the built graph — the graph-level manifestation of the collapse
  condition characterised in ``docs/OSS_DIAGNOSTICS.md``).
- Reuse the existing simple velocity extrapolation
  (``predicted = last + velocity * gap``) — no fancy motion model in v1.
- Every synthetic candidate is tagged ``beacon_derived=True`` /
  ``cfar_confirmed=False``; this provenance is never dropped.
- Anti-drift guardrails: minimum track age, a cap on consecutive synthetic frames,
  and a hard node-inflation ceiling.

Phase 1 (this module): compute and log synthetic candidates and their would-be
link scores. It does NOT inject them into any submission graph.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import median

import numpy as np

from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class SyntheticCandidate:
    """A would-be detection recovered from track continuity (never CFAR-confirmed)."""

    frame: int
    track_id: str
    parent_node_id: str | None
    predicted_z_um: float
    predicted_y_um: float
    predicted_x_um: float
    base_beacon_score: float
    discount_applied: float
    would_be_a_score: float
    consecutive_synthetic_count: int
    collides_with_real: bool = False
    beacon_derived: bool = True
    cfar_confirmed: bool = False


@dataclass(frozen=True)
class CorrelationShadowSummary:
    nodes: int
    edges: int
    last_frame: int
    low_detection_frames: int
    synthetic_candidate_count: int
    tracks_triggered: int
    frames_with_synthetics: int
    mean_would_be_a_score: float
    suppressed_young_tracks: int
    suppressed_by_consecutive_cap: int
    suppressed_by_node_ceiling: int
    node_inflation_ceiling: int
    node_inflation_ratio: float
    hit_node_ceiling: bool
    # Double-target / merge-gate diagnostics.
    synthetic_collision_count: int
    synthetic_gap_count: int
    suppressed_by_merge_gate: int
    merge_gate_radius_um: float
    merge_gate_frame_window: int
    merge_gate_applied: bool
    # Parameters echoed for auditability.
    min_track_age_frames: int
    max_consecutive_synthetic: int
    discount: float
    max_link_distance_um: float
    low_detection_floor_ratio: float
    candidates: list[SyntheticCandidate] = field(default_factory=list)


def _best_incoming_source_by_target(edges: list[LineageEdge]) -> dict[str, str]:
    best: dict[str, tuple[float, str]] = {}
    for edge in edges:
        confidence = float(edge.confidence if edge.confidence is not None else 0.0)
        existing = best.get(edge.target_id)
        if existing is None or confidence > existing[0]:
            best[edge.target_id] = (confidence, edge.source_id)
    return {target_id: source_id for target_id, (_c, source_id) in best.items()}


def _outgoing_target_ids_by_source(edges: list[LineageEdge]) -> dict[str, set[str]]:
    outgoing: dict[str, set[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source_id, set()).add(edge.target_id)
    return outgoing


def _track_depths(
    detections: list[Detection],
    incoming_source_by_target: dict[str, str],
) -> dict[str, int]:
    """Number of confirmed nodes from the track root up to and including each node."""

    depth_by_node_id: dict[str, int] = {}
    ordered = sorted(detections, key=lambda detection: (int(detection.t), detection.node_id))
    for detection in ordered:
        source_id = incoming_source_by_target.get(detection.node_id)
        if source_id is None:
            depth_by_node_id[detection.node_id] = 1
        else:
            depth_by_node_id[detection.node_id] = 1 + int(depth_by_node_id.get(source_id, 1))
    return depth_by_node_id


def _low_detection_frames(
    detections: list[Detection], *, last_frame: int, floor_ratio: float
) -> set[int]:
    counts_by_t: dict[int, int] = {}
    for detection in detections:
        counts_by_t[int(detection.t)] = counts_by_t.get(int(detection.t), 0) + 1
    observed_counts = [counts_by_t.get(t, 0) for t in range(last_frame + 1)]
    positive = [c for c in observed_counts if c > 0]
    if not positive:
        return set(range(last_frame + 1))
    median_count = float(median(positive))
    floor = max(1.0, floor_ratio * median_count)
    return {t for t in range(last_frame + 1) if counts_by_t.get(t, 0) < floor}


def _positions_by_frame(
    detections: list[Detection],
) -> dict[int, tuple[list[str], np.ndarray]]:
    """Real detection ids + positions (um) grouped by timepoint for neighbour lookups."""

    grouped_ids: dict[int, list[str]] = {}
    grouped_pos: dict[int, list[tuple[float, float, float]]] = {}
    for detection in detections:
        t = int(detection.t)
        grouped_ids.setdefault(t, []).append(detection.node_id)
        grouped_pos.setdefault(t, []).append(detection.position_um)
    return {
        t: (grouped_ids[t], np.array(grouped_pos[t], dtype=float)) for t in grouped_ids
    }


def _has_real_neighbor(
    positions_by_frame: dict[int, tuple[list[str], np.ndarray]],
    predicted: np.ndarray,
    gap_frame: int,
    *,
    radius_um: float,
    frame_window: int,
    exclude_ids: set[str],
) -> bool:
    """True when a real detection (other than the track's own nodes) is within the
    merge neighbourhood of the predicted synthetic position."""

    for frame in range(gap_frame - frame_window, gap_frame + frame_window + 1):
        entry = positions_by_frame.get(frame)
        if entry is None:
            continue
        node_ids, arr = entry
        if arr.size == 0:
            continue
        distances = np.linalg.norm(arr - predicted, axis=1)
        for node_id, distance in zip(node_ids, distances):
            if node_id in exclude_ids:
                continue
            if float(distance) <= radius_um:
                return True
    return False


def _ancestor_ids(leaf_id: str, incoming_source_by_target: dict[str, str]) -> set[str]:
    """All confirmed node ids on the track from ``leaf_id`` back to its root."""

    chain: set[str] = set()
    current: str | None = leaf_id
    while current is not None and current not in chain:
        chain.add(current)
        current = incoming_source_by_target.get(current)
    return chain



def compute_correlation_shadow(
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
) -> CorrelationShadowSummary:
    """Shadow-only measurement of recoverable detections via track continuity.

    Never mutates ``graph``. Returns synthetic candidates that a correlation layer
    *would* propose in weak/zero-CFAR regions, with discounted would-be link scores
    and anti-drift guardrails applied.

    Trigger (region-level, the graph manifestation of the collapse-risk condition):
    a **track gap** -- a stable track whose confirmed nodes end before the last
    observed frame, i.e. a local region where CFAR failed to produce a linkable
    detection even though continuity expects the cell to persist. The production
    ``sigma`` route does not whole-frame collapse, so a whole-frame low-detection
    gate would fire almost never; it is therefore an optional stricter filter
    (``require_low_detection_frame``) rather than the primary trigger.

    Merge gate (identity de-duplication): every would-be synthetic is checked for a
    real (CFAR-confirmed) detection within ``merge_gate_radius_um`` across a +/-
    ``merge_gate_frame_window`` window. Colliding candidates are flagged
    ``collides_with_real``; when ``apply_merge_gate`` is set they are suppressed so
    synthetics only fill genuine gaps and never compete with real detections.
    """

    detections = list(graph.detections)
    edges = list(graph.edges)
    empty = CorrelationShadowSummary(
        nodes=len(detections),
        edges=len(edges),
        last_frame=0,
        low_detection_frames=0,
        synthetic_candidate_count=0,
        tracks_triggered=0,
        frames_with_synthetics=0,
        mean_would_be_a_score=0.0,
        suppressed_young_tracks=0,
        suppressed_by_consecutive_cap=0,
        suppressed_by_node_ceiling=0,
        node_inflation_ceiling=0,
        node_inflation_ratio=float(node_inflation_ratio),
        hit_node_ceiling=False,
        synthetic_collision_count=0,
        synthetic_gap_count=0,
        suppressed_by_merge_gate=0,
        merge_gate_radius_um=float(merge_gate_radius_um),
        merge_gate_frame_window=int(merge_gate_frame_window),
        merge_gate_applied=bool(apply_merge_gate),
        min_track_age_frames=int(min_track_age_frames),
        max_consecutive_synthetic=int(max_consecutive_synthetic),
        discount=float(discount),
        max_link_distance_um=float(max_link_distance_um),
        low_detection_floor_ratio=float(low_detection_floor_ratio),
        candidates=[],
    )
    if not detections:
        return empty

    by_id: dict[str, Detection] = {d.node_id: d for d in detections}
    last_frame = max(int(d.t) for d in detections)
    incoming_source_by_target = _best_incoming_source_by_target(edges)
    outgoing_by_source = _outgoing_target_ids_by_source(edges)
    depth_by_node_id = _track_depths(detections, incoming_source_by_target)
    low_frames = _low_detection_frames(
        detections, last_frame=last_frame, floor_ratio=low_detection_floor_ratio
    )
    positions_by_frame = _positions_by_frame(detections)

    # Node-inflation ceiling: synthetics may add at most (ratio - 1) * nodes.
    max_synthetic_budget = int(np.floor(len(detections) * max(0.0, node_inflation_ratio - 1.0)))
    node_inflation_ceiling = len(detections) + max_synthetic_budget

    # Track leaves: confirmed nodes with no confirmed continuation, that end before
    # the last observed frame (so the cell should plausibly still exist).
    leaves = [
        detection
        for detection in detections
        if not outgoing_by_source.get(detection.node_id) and int(detection.t) < last_frame
    ]
    leaves.sort(key=lambda detection: (int(detection.t), detection.node_id))

    candidates: list[SyntheticCandidate] = []
    triggered_tracks: set[str] = set()
    triggered_frames: set[int] = set()
    suppressed_young = 0
    suppressed_consecutive = 0
    suppressed_ceiling = 0
    suppressed_merge = 0
    collision_count = 0
    gap_count = 0
    hit_ceiling = False

    for leaf in leaves:
        depth = int(depth_by_node_id.get(leaf.node_id, 1))
        if depth < int(min_track_age_frames):
            suppressed_young += 1
            continue

        predecessor_id = incoming_source_by_target.get(leaf.node_id)
        predecessor = by_id.get(predecessor_id) if predecessor_id else None
        leaf_pos = np.array(leaf.position_um, dtype=float)
        if predecessor is not None:
            velocity = leaf_pos - np.array(predecessor.position_um, dtype=float)
        else:
            velocity = np.zeros(3, dtype=float)

        # Persistence-based beacon score (same shape as the reinforcement layer's
        # persistence signal); discounted because there is no sensor confirmation.
        base_beacon_score = min(1.0, depth / float(int(min_track_age_frames) + 1))
        would_be_a = base_beacon_score * float(discount)

        # The track's own confirmed nodes must never count as a competing detection.
        own_track_ids = _ancestor_ids(leaf.node_id, incoming_source_by_target)

        consecutive = 0
        for gap_frame in range(int(leaf.t) + 1, last_frame + 1):
            if require_low_detection_frame and gap_frame not in low_frames:
                break  # stricter opt-in: only recover in whole-frame collapse frames
            if consecutive >= int(max_consecutive_synthetic):
                suppressed_consecutive += 1
                break
            if len(candidates) >= max_synthetic_budget:
                suppressed_ceiling += 1
                hit_ceiling = True
                break
            consecutive += 1
            predicted = leaf_pos + velocity * float(consecutive)
            # Reject physically implausible extrapolations (same bound as latent recovery).
            if float(np.linalg.norm(velocity) * consecutive) > max_link_distance_um * float(consecutive + 1):
                break
            collides = _has_real_neighbor(
                positions_by_frame,
                predicted,
                int(gap_frame),
                radius_um=merge_gate_radius_um,
                frame_window=merge_gate_frame_window,
                exclude_ids=own_track_ids,
            )
            if collides:
                collision_count += 1
                if apply_merge_gate:
                    # A real detection already covers this identity: suppress the
                    # synthetic and stop extrapolating this leaf (genuine gaps only).
                    suppressed_merge += 1
                    break
            else:
                gap_count += 1
            candidates.append(
                SyntheticCandidate(
                    frame=int(gap_frame),
                    track_id=leaf.node_id,
                    parent_node_id=predecessor_id,
                    predicted_z_um=float(predicted[0]),
                    predicted_y_um=float(predicted[1]),
                    predicted_x_um=float(predicted[2]),
                    base_beacon_score=round(base_beacon_score, 5),
                    discount_applied=float(discount),
                    would_be_a_score=round(would_be_a, 5),
                    consecutive_synthetic_count=consecutive,
                    collides_with_real=collides,
                )
            )
            triggered_tracks.add(leaf.node_id)
            triggered_frames.add(int(gap_frame))
        if hit_ceiling:
            break

    mean_a = (
        float(np.mean([c.would_be_a_score for c in candidates])) if candidates else 0.0
    )
    return CorrelationShadowSummary(
        nodes=len(detections),
        edges=len(edges),
        last_frame=last_frame,
        low_detection_frames=len(low_frames),
        synthetic_candidate_count=len(candidates),
        tracks_triggered=len(triggered_tracks),
        frames_with_synthetics=len(triggered_frames),
        mean_would_be_a_score=round(mean_a, 5),
        suppressed_young_tracks=suppressed_young,
        suppressed_by_consecutive_cap=suppressed_consecutive,
        suppressed_by_node_ceiling=suppressed_ceiling,
        node_inflation_ceiling=node_inflation_ceiling,
        node_inflation_ratio=float(node_inflation_ratio),
        hit_node_ceiling=hit_ceiling,
        synthetic_collision_count=collision_count,
        synthetic_gap_count=gap_count,
        suppressed_by_merge_gate=suppressed_merge,
        merge_gate_radius_um=float(merge_gate_radius_um),
        merge_gate_frame_window=int(merge_gate_frame_window),
        merge_gate_applied=bool(apply_merge_gate),
        min_track_age_frames=int(min_track_age_frames),
        max_consecutive_synthetic=int(max_consecutive_synthetic),
        discount=float(discount),
        max_link_distance_um=float(max_link_distance_um),
        low_detection_floor_ratio=float(low_detection_floor_ratio),
        candidates=candidates,
    )


def summary_as_dict(summary: CorrelationShadowSummary, *, include_candidates: bool = False) -> dict:
    """Serialize a summary, optionally omitting the (potentially large) candidate log."""

    payload = asdict(summary)
    if not include_candidates:
        payload.pop("candidates", None)
    return payload
