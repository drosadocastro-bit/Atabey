"""Evaluate LSAP-constrained per-track budgets for low-confidence echoes."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.detection.baseline import _cfar_background_stats_box, robust_normalize
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


ECHO_FLOOR = 0.35
ECHO_K_SIGMA = 0.80
ECHO_FOOTPRINT = (1, 3, 3)
ROUTER_RADIUS_UM = 14.0
DEDUP_RADIUS_UM = 3.0
OFFICIAL_RADIUS_UM = 7.0
FORMATION_RADIUS_UM = 14.0
BUDGETS = (1, 2)
PREDICTION_WEIGHT = 0.70
CFAR_WEIGHT = 0.30
SCALE = np.asarray(
    (DEFAULT_VOXEL_SCALE_UM.z, DEFAULT_VOXEL_SCALE_UM.y, DEFAULT_VOXEL_SCALE_UM.x),
    dtype=float,
)


def graph_signature(graph):
    nodes = tuple((node.node_id, int(node.t), *node.position_um) for node in graph.detections)
    edges = tuple((edge.source_id, edge.target_id, edge.relation) for edge in graph.edges)
    return nodes, edges


def prediction(node, incoming, nodes):
    predecessors = [nodes[source] for source in incoming.get(node.node_id, []) if source in nodes]
    predecessors = [item for item in predecessors if int(item.t) == int(node.t) - 1]
    current = np.asarray(node.position_um, dtype=float)
    if len(predecessors) != 1:
        return current, np.zeros(3, dtype=float), "stationary_fallback"
    previous = np.asarray(predecessors[0].position_um, dtype=float)
    velocity = current - previous
    return current + velocity, velocity, "velocity"


def echo_peaks(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    source = volume.astype(np.float32)
    size = tuple(2 * radius + 1 for radius in ECHO_FOOTPRINT)
    maxima = ndimage.maximum_filter(source, size=size, mode="nearest")
    background_mean, background_std, _ = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
    )
    threshold = background_mean + ECHO_K_SIGMA * background_std
    mask = (source == maxima) & (normalized >= ECHO_FLOOR) & (normalized >= threshold)
    coords_um = np.argwhere(mask).astype(float) * SCALE
    values = normalized[mask]
    thresholds = threshold[mask]
    margins = np.maximum(0.0, (values - thresholds) / np.maximum(thresholds, 1e-6))
    margins = np.clip(margins, 0.0, 1.0).astype(float, copy=False)
    del normalized, source, maxima, background_mean, background_std, threshold, mask
    gc.collect()
    return coords_um, margins


def remove_primary_duplicates(points, margins, primary):
    if not len(points) or not len(primary):
        return points, margins
    from scipy.spatial import cKDTree

    distances, _ = cKDTree(primary).query(points, k=1)
    keep = distances > DEDUP_RADIUS_UM
    return points[keep], margins[keep]


def assign_proposals(points, margins, seeds, budget):
    """Assign each echo to at most one seed with optional abstention."""

    from scipy.optimize import linear_sum_assignment

    slots = []
    for seed_index, seed in enumerate(seeds):
        capacity = min(int(budget), int(seed["capacity"]))
        slots.extend((seed_index, slot) for slot in range(capacity))
    if not slots or not len(points):
        return [], {"slot_count": len(slots), "assigned": 0, "abstained": len(slots)}

    row_count = len(slots)
    candidate_count = len(points)
    costs = np.full((row_count, candidate_count + row_count), 1e6, dtype=np.float32)
    costs[:, candidate_count:] = 0.0
    for row_index, (seed_index, _) in enumerate(slots):
        seed = seeds[seed_index]
        anchor_distances = np.linalg.norm(points - seed["anchor"][None, :], axis=1)
        prediction_distances = np.linalg.norm(points - seed["prediction"][None, :], axis=1)
        valid = anchor_distances <= ROUTER_RADIUS_UM
        closeness = np.maximum(0.0, 1.0 - prediction_distances / ROUTER_RADIUS_UM)
        scores = PREDICTION_WEIGHT * closeness + CFAR_WEIGHT * margins
        costs[row_index, :candidate_count][valid] = -scores[valid]

    row_indices, column_indices = linear_sum_assignment(costs)
    assignments = []
    for row_index, column_index in zip(row_indices, column_indices, strict=True):
        if column_index >= candidate_count or costs[row_index, column_index] >= 0.0:
            continue
        seed_index, _ = slots[row_index]
        assignments.append(
            {
                "seed_index": seed_index,
                "candidate_index": int(column_index),
                "position": points[column_index],
                "score": float(-costs[row_index, column_index]),
            }
        )
    return assignments, {
        "slot_count": row_count,
        "assigned": len(assignments),
        "abstained": row_count - len(assignments),
    }


def combine(primary, selected):
    if not selected:
        return primary
    echo = np.asarray([item["position"] for item in selected], dtype=float).reshape((-1, 3))
    if not len(primary):
        return echo
    return np.concatenate((primary, echo), axis=0)


def within(points, target, radius):
    if not len(points):
        return np.empty((0, 3), dtype=float)
    return points[np.linalg.norm(points - target[None, :], axis=1) <= radius]


def geometry_available(parent_points, daughter_points, gt_parent, gt_daughters):
    parents = within(parent_points, gt_parent, OFFICIAL_RADIUS_UM)
    left = within(daughter_points, gt_daughters[0], OFFICIAL_RADIUS_UM)
    right = within(daughter_points, gt_daughters[1], OFFICIAL_RADIUS_UM)
    for parent in parents:
        for first in left:
            for second in right:
                if np.linalg.norm(first - second) <= 1e-9:
                    continue
                if (
                    np.linalg.norm(first - parent) <= FORMATION_RADIUS_UM
                    and np.linalg.norm(second - parent) <= FORMATION_RADIUS_UM
                ):
                    return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--pre-post", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    prior = json.loads(args.pre_post.read_text(encoding="utf-8"))
    baseline_available = {
        row["case_id"]: bool(row["post_official_geometry_available"]) for row in prior
    }
    by_sample = defaultdict(list)
    for row in prior:
        case = fixture[row["case_id"]]
        by_sample[case["sample_id"]].append(case)

    rows = []
    for sample_id, cases in by_sample.items():
        max_t = max(int(case["t"]) for case in cases)
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr",
            max_timepoints=max_t + 2,
        )
        before = graph_signature(graph)
        nodes = {node.node_id: node for node in graph.detections}
        frame_nodes = defaultdict(list)
        for node in graph.detections:
            frame_nodes[int(node.t)].append(node)
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for edge in graph.edges:
            incoming[edge.target_id].append(edge.source_id)
            outgoing[edge.source_id].append(edge.target_id)

        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        array = open_competition_array(args.train_dir / f"{sample_id}.zarr")
        echo_cache = {}

        for case in cases:
            t = int(case["t"])
            for frame in (t, t + 1):
                if frame not in echo_cache:
                    echo_cache[frame] = echo_peaks(read_timepoint(array, frame))

            primary_parent = np.asarray(
                [node.position_um for node in frame_nodes[t]], dtype=float
            ).reshape((-1, 3))
            primary_daughter = np.asarray(
                [node.position_um for node in frame_nodes[t + 1]], dtype=float
            ).reshape((-1, 3))
            parent_points, parent_margins = remove_primary_duplicates(
                *echo_cache[t], primary_parent
            )
            daughter_points, daughter_margins = remove_primary_duplicates(
                *echo_cache[t + 1], primary_daughter
            )

            broken_seeds = []
            for node in frame_nodes[t - 1]:
                next_ids = [
                    target
                    for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t
                ]
                if next_ids:
                    continue
                predicted, velocity, mode = prediction(node, incoming, nodes)
                broken_seeds.append(
                    {
                        "seed_id": node.node_id,
                        "anchor": predicted,
                        "prediction": predicted,
                        "next_prediction": predicted + velocity,
                        "mode": mode,
                        "capacity": 2,
                    }
                )

            primary_daughter_seeds = []
            for node in frame_nodes[t]:
                next_ids = [
                    target
                    for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t + 1
                ]
                if len(next_ids) >= 2:
                    continue
                predicted, _, mode = prediction(node, incoming, nodes)
                primary_daughter_seeds.append(
                    {
                        "seed_id": node.node_id,
                        "anchor": np.asarray(node.position_um, dtype=float),
                        "prediction": predicted,
                        "mode": mode,
                        "capacity": 2 - len(next_ids),
                    }
                )

            gt_parent = np.asarray(
                gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float
            )
            gt_daughters = [
                np.asarray(gt_nodes[int(node_id)].position_um, dtype=float)
                for node_id in case["gt_child_ids"]
            ]
            primary_geometry = geometry_available(
                primary_parent, primary_daughter, gt_parent, gt_daughters
            )
            budget_results = {}
            for budget in BUDGETS:
                selected_parents, parent_assignment = assign_proposals(
                    parent_points, parent_margins, broken_seeds, budget
                )
                virtual_seeds = []
                for proposal in selected_parents:
                    source_seed = broken_seeds[proposal["seed_index"]]
                    virtual_seeds.append(
                        {
                            "seed_id": f"echo:{source_seed['seed_id']}",
                            "anchor": proposal["position"],
                            "prediction": source_seed["next_prediction"],
                            "mode": source_seed["mode"],
                            "capacity": 2,
                        }
                    )
                daughter_seeds = primary_daughter_seeds + virtual_seeds
                selected_daughters, daughter_assignment = assign_proposals(
                    daughter_points, daughter_margins, daughter_seeds, budget
                )
                combined_parent = combine(primary_parent, selected_parents)
                combined_daughter = combine(primary_daughter, selected_daughters)
                available = geometry_available(
                    combined_parent, combined_daughter, gt_parent, gt_daughters
                )
                selected_parent_indices = [
                    item["candidate_index"] for item in selected_parents
                ]
                selected_daughter_indices = [
                    item["candidate_index"] for item in selected_daughters
                ]
                budget_results[str(budget)] = {
                    "available": available,
                    "recovered": bool(not primary_geometry and available),
                    "selected_parent_echoes": len(selected_parents),
                    "selected_daughter_echoes": len(selected_daughters),
                    "selected_total": len(selected_parents) + len(selected_daughters),
                    "full_new_echo_pool": len(parent_points) + len(daughter_points),
                    "proposal_retention_fraction": (
                        (len(selected_parents) + len(selected_daughters))
                        / max(1, len(parent_points) + len(daughter_points))
                    ),
                    "parent_assignment": parent_assignment,
                    "daughter_assignment": daughter_assignment,
                    "candidate_ownership_unique": (
                        len(selected_parent_indices) == len(set(selected_parent_indices))
                        and len(selected_daughter_indices)
                        == len(set(selected_daughter_indices))
                    ),
                }

            rows.append(
                {
                    "case_id": case["case_id"],
                    "sample_id": sample_id,
                    "family": sample_id.split("_", 1)[0],
                    "t": t,
                    "cohort": (
                        "control" if baseline_available[case["case_id"]] else "failure"
                    ),
                    "detector": detector,
                    "link_strategy": link_strategy,
                    "primary_geometry_available": primary_geometry,
                    "broken_seed_count": len(broken_seeds),
                    "under_resolved_seed_count": len(primary_daughter_seeds),
                    "budgets": budget_results,
                    "zero_perturbation": before == graph_signature(graph),
                    "candidate_set_changed": False,
                    "graph_mutated": False,
                }
            )
            print(
                f"{sample_id} t{t}: primary={primary_geometry} "
                + " ".join(
                    f"K{k}={budget_results[str(k)]['available']}/"
                    f"{budget_results[str(k)]['selected_total']}"
                    for k in BUDGETS
                ),
                flush=True,
            )

    failures = [row for row in rows if row["cohort"] == "failure"]
    controls = [row for row in rows if row["cohort"] == "control"]
    budget_summaries = {}
    for budget in BUDGETS:
        key = str(budget)
        per_frame = [
            row["budgets"][key][field]
            for row in rows
            for field in ("selected_parent_echoes", "selected_daughter_echoes")
        ]
        budget_summaries[key] = {
            "failure_recovered": sum(row["budgets"][key]["recovered"] for row in failures),
            "failure_total": len(failures),
            "controls_available": sum(row["budgets"][key]["available"] for row in controls),
            "control_total": len(controls),
            "selected_per_event_frame": {
                "median": float(np.median(per_frame)),
                "p90": float(np.percentile(per_frame, 90)),
                "max": int(max(per_frame)),
            },
            "ownership_unique_all": all(
                row["budgets"][key]["candidate_ownership_unique"] for row in rows
            ),
            "family_recovery": {
                family: sum(
                    row["cohort"] == "failure"
                    and row["family"] == family
                    and row["budgets"][key]["recovered"]
                    for row in rows
                )
                for family in sorted({row["family"] for row in rows})
            },
        }

    eligible = [
        key
        for key, result in budget_summaries.items()
        if result["failure_recovered"] >= 2
        and result["controls_available"] == result["control_total"]
        and result["selected_per_event_frame"]["median"] <= 2.0
    ]
    if eligible:
        decision = "GO_TO_SEMANTIC_SHADOW"
    elif max(result["failure_recovered"] for result in budget_summaries.values()) == 0:
        decision = "NO_GO"
    else:
        decision = "HOLD"
    summary = {
        "status": "read_only_v23_per_track_echo_budget",
        "population": {"cases": len(rows), "failures": len(failures), "controls": len(controls)},
        "decision": decision,
        "eligible_budgets": eligible,
        "budgets": budget_summaries,
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 Per-Track Echo Proposal Budget Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "Low-confidence echoes were assigned with candidate ownership 1, explicit abstention, and per-track budgets K=1/K=2. GT was used only after assignment to measure registered fork geometry. No graph or candidate set was mutated.",
        "",
        "| Budget | Failure recovery | Controls available | Selected/frame median | p90 | max | Ownership unique |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for budget in BUDGETS:
        result = budget_summaries[str(budget)]
        selected = result["selected_per_event_frame"]
        lines.append(
            f"| {budget} | {result['failure_recovered']}/{result['failure_total']} | "
            f"{result['controls_available']}/{result['control_total']} | "
            f"{selected['median']:.1f} | {selected['p90']:.1f} | {selected['max']} | "
            f"{result['ownership_unique_all']} |"
        )
    lines += [
        "",
        "## Event Breakdown",
        "",
        "| Event | Cohort | Primary | K=1 available / selected | K=2 available / selected |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['cohort']} | "
            f"{row['primary_geometry_available']} | "
            f"{row['budgets']['1']['available']} / {row['budgets']['1']['selected_total']} | "
            f"{row['budgets']['2']['available']} / {row['budgets']['2']['selected_total']} |"
        )
    lines += [
        "",
        "Guardrail: this is a proposal-availability shadow only. It does not authorize candidate emission, edge creation, graph mutation, or full-cohort execution.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()


