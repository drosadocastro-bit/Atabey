"""V27A frame-local extension of association forensics; never builds a tracker.

Kept separate because the original association_forensics module is hash-pinned
by V25. Shared historical linking functions remain authoritative and unchanged.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
import hashlib
import json

import numpy as np
from scipy.spatial import cKDTree

from atabey.tracking.nearest_neighbor import _greedy_assign, _predicted_position, link_adjacent_timepoints
from atabey.tracking.v26_a_forward_ranking_shadow import link_step_ranked_motion_mutual
from atabey.types import Detection

RADIUS = 9.0
ARMS = {"M0": (False, "motion"), "M1": (True, "motion"),
        "S0": (False, "step"), "S1": (True, "step")}
CONTRASTS = {"order_motion": ("M0", "M1"), "order_step": ("S0", "S1"),
             "ranking_select_first": ("M0", "S0"), "ranking_filter_first": ("M1", "S1"),
             "historical_forward_ties": ("H", "M0")}


def scientific_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def input_digest(previous, current, predecessors) -> str:
    return scientific_digest({"previous": [asdict(n) for n in previous],
                              "current": [asdict(n) for n in current],
                              "predecessors": {k: asdict(v) for k, v in predecessors.items()}})


def audit_factorial_frame(
    previous: Sequence[Detection], current: Sequence[Detection],
    predecessors: Mapping[str, Detection],
) -> dict:
    """Measure five decisions on one immutable context, with explicit failures.

No alternate predecessor map is created. Failures are returned with telemetry
so the runner can persist the offending frame before marking execution invalid.
"""
    all_nodes = [*previous, *current, *predecessors.values()]
    if any(not np.isfinite(n.position_um).all() for n in all_nodes):
        raise ValueError("Non-finite physical input")
    before = input_digest(previous, current, predecessors)
    if len({n.node_id for n in [*previous, *current]}) != len(previous) + len(current):
        raise ValueError("Duplicate frame node identity")
    if previous and (len({n.t for n in previous}) != 1 or
                     any(n.t != previous[0].t + 1 for n in current)):
        raise ValueError("Frame inputs must be adjacent and time-homogeneous")
    sample_ids = {n.sample_id for n in all_nodes}
    if len(sample_ids) > 1:
        raise ValueError("Mixed sample identities")
    for source in previous:
        parent = predecessors.get(source.node_id)
        if parent is not None and parent.t != source.t - 1:
            raise ValueError("Predecessor must be in the preceding frame")

    source_positions = np.array([n.position_um for n in previous], dtype=float).reshape(-1, 3)
    targets = np.array([n.position_um for n in current], dtype=float).reshape(-1, 3)
    forward_tree = cKDTree(targets) if current else None
    reverse_tree = cKDTree(source_positions) if previous else None
    reverse_rows = []
    for target in current:
        if not previous:
            reverse_rows.append({"owner_id": None, "distance_um": None, "tie_indices": []})
            continue
        distance, index = reverse_tree.query(target.position_um, k=1)
        distances = np.linalg.norm(source_positions - target.position_um, axis=1)
        reverse_rows.append({
            "owner_id": previous[int(index)].node_id if distance <= RADIUS else None,
            "nearest_source_index": int(index), "distance_um": float(distance),
            "tie_indices": [int(i) for i in np.flatnonzero(distances == distances[int(index)])],
        })

    rows, failures = [], []
    candidates = {arm: [] for arm in ["H", *ARMS]}
    for source in previous:
        predicted = _predicted_position(source, predecessors.get(source.node_id))
        errors = np.linalg.norm(targets - predicted, axis=1)
        steps = np.linalg.norm(targets - np.array(source.position_um), axis=1)
        feasible = np.flatnonzero((errors <= RADIUS) & (steps <= RADIUS))
        decisions = {}
        selections = {}
        if current:
            historical_error, historical_index = forward_tree.query(predicted, k=1)
            historical_index = int(historical_index)
            selections["H"] = (historical_index, float(historical_error),
                               float(np.linalg.norm(targets[historical_index] - source.position_um)))
        else:
            selections["H"] = (None, None, None)
        for arm, (filter_first, rank) in ARMS.items():
            pool = feasible if filter_first else range(len(current))
            values = errors if rank == "motion" else steps
            index = min(pool, key=lambda i: (float(values[i]), int(i)), default=None)
            selections[arm] = ((int(index), float(errors[index]), float(steps[index]))
                               if index is not None else (None, None, None))
        for arm, (index, error, step) in selections.items():
            passes = index is not None and error <= RADIUS and step <= RADIUS
            reverse_owner = reverse_rows[index]["owner_id"] if index is not None else None
            accepted = passes and reverse_owner == source.node_id
            if index is None:
                reason = "no_targets" if not current else "no_feasible_targets"
            elif not passes:
                reason = "prediction_gate" if error > RADIUS else "physical_step_gate"
            elif not accepted:
                reason = "reverse_mutuality"
            else:
                reason = None
            rank_values = errors if arm in ("H", "M0", "M1") else steps
            pool = feasible if arm in ("M1", "S1") else np.arange(len(current))
            tied = ([int(i) for i in pool if rank_values[i] == rank_values[index]]
                    if index is not None else [])
            target_id = current[index].node_id if index is not None else None
            decisions[arm] = {
                "selected_index": index, "selected_target_id": target_id,
                "prediction_error_um": error, "physical_step_um": step,
                "gate_eligible_target_id": target_id if passes else None,
                "reverse_owner_id": reverse_owner,
                "accepted_target_id": target_id if accepted else None,
                "confidence": max(0., 1. - error / RADIUS) if accepted else None,
                "rejection_reason": reason, "rank_tie_indices": tied,
            }
            if accepted:
                candidates[arm].append((error, source, current[index]))

        h, m = decisions["H"], decisions["M0"]
        if h["selected_index"] != m["selected_index"]:
            hi, mi = h["selected_index"], m["selected_index"]
            if hi is None or mi is None or not (errors[hi] == errors[mi] == h["prediction_error_um"]):
                failures.append({"source_id": source.node_id, "check": "h_m0_non_tie_selection"})
        if bool(h["gate_eligible_target_id"]) != bool(m["gate_eligible_target_id"]):
            failures.append({"source_id": source.node_id, "check": "h_m0_gate_mismatch"})
        if (h["confidence"] is not None and m["confidence"] is not None
                and h["confidence"] != m["confidence"]):
            failures.append({"source_id": source.node_id, "check": "h_m0_confidence_mismatch"})
        rows.append({
            "source_id": source.node_id, "source_t": source.t,
            "predecessor_id": predecessors[source.node_id].node_id if source.node_id in predecessors else None,
            "predicted_position_um": predicted.tolist(), "prediction_errors_um": errors.tolist(),
            "physical_steps_um": steps.tolist(), "feasible_indices": feasible.tolist(),
            "gate_order_exposed": bool(current and not h["gate_eligible_target_id"] and len(feasible)),
            "decisions": decisions,
        })

    # Use the unchanged greedy layer for every arm, and exact executable anchors.
    arm_edges = {arm: _greedy_assign(pairs, RADIUS) for arm, pairs in candidates.items()}
    exact_h = link_adjacent_timepoints(list(previous), list(current), RADIUS,
                                      strategy="motion_mutual", predecessor_by_node_id=predecessors)
    exact_s1 = link_step_ranked_motion_mutual(list(previous), list(current), RADIUS, predecessors)
    for arm, expected in (("H", exact_h), ("S1", exact_s1)):
        if arm_edges[arm] != expected:
            failures.append({"check": f"{arm}_executable_anchor_mismatch",
                             "expected": [asdict(e) for e in expected],
                             "observed": [asdict(e) for e in arm_edges[arm]]})
    for arm, edges in arm_edges.items():
        accepted = {edge.source_id: edge for edge in edges}
        for row in rows:
            decision = row["decisions"][arm]
            edge = accepted.get(row["source_id"])
            if decision["accepted_target_id"] is not None and edge is None:
                decision.update(accepted_target_id=None, confidence=None, rejection_reason="greedy_uniqueness")

    for row in rows:
        decisions = row["decisions"]
        row["contrasts"] = {}
        for name, (before_arm, after_arm) in CONTRASTS.items():
            a, b = decisions[before_arm], decisions[after_arm]
            old, new = a["accepted_target_id"], b["accepted_target_id"]
            row["contrasts"][name] = {
                "selected_changed": a["selected_target_id"] != b["selected_target_id"],
                "accepted_changed": old != new,
                "removed_edge": [row["source_id"], old] if old is not None and old != new else None,
                "added_edge": [row["source_id"], new] if new is not None and old != new else None,
                "accepted_delta": int(new is not None) - int(old is not None),
            }
        y = {arm: int(decisions[arm]["accepted_target_id"] is not None) for arm in ARMS}
        row["acceptance_interaction"] = (y["S1"] - y["S0"]) - (y["M1"] - y["M0"])
        row["has_forward_tie"] = any(len(d["rank_tie_indices"]) > 1 for d in decisions.values())
        row["has_selected_reverse_tie"] = any(
            d["selected_index"] is not None and len(reverse_rows[d["selected_index"]]["tie_indices"]) > 1
            for d in decisions.values())
    after = input_digest(previous, current, predecessors)
    if before != after:
        failures.append({"check": "input_mutation"})
    return {"source_t": previous[0].t if previous else None,
            "source_ids": [n.node_id for n in previous],
            "target_ids": [n.node_id for n in current],
            "source_positions_um": source_positions.tolist(), "target_positions_um": targets.tolist(),
            "reverse_ownership": reverse_rows, "rows": rows,
            "input_sha256_before": before, "input_sha256_after": after,
            "validity_failures": failures}


def summarize_rows(rows: Sequence[dict]) -> dict:
    """Additive counts only; never select an arm or assign correctness."""
    counts = Counter()
    for row in rows:
        counts["sources"] += 1
        counts["feasible_targets"] += len(row["feasible_indices"])
        counts["available_targets"] += len(row["prediction_errors_um"])
        counts["gate_order_exposed"] += int(row["gate_order_exposed"])
        counts["exposed_s1_accepted"] += int(row["gate_order_exposed"] and row["decisions"]["S1"]["accepted_target_id"] is not None)
        for stratum, value in (("no_predecessor", row["predecessor_id"] is None),
                               ("forward_tie", row["has_forward_tie"]),
                               ("reverse_tie", row["has_selected_reverse_tie"])):
            counts[f"stratum::{stratum}"] += int(value)
        counts[f"interaction::{row['acceptance_interaction']}"] += 1
        counts["interaction_sum"] += row["acceptance_interaction"]
        for arm, d in row["decisions"].items():
            counts[f"accepted::{arm}"] += int(d["accepted_target_id"] is not None)
        for name, c in row["contrasts"].items():
            for key in ("selected_changed", "accepted_changed", "accepted_delta"):
                counts[f"contrast::{name}::{key}"] += int(c[key])
            counts[f"contrast::{name}::added"] += int(c["added_edge"] is not None)
            counts[f"contrast::{name}::removed"] += int(c["removed_edge"] is not None)
    return dict(sorted(counts.items()))
