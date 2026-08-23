"""Audit parent-to-daughter candidate-axis image topology without fitting a model."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from audit_v23_local_ownership_feasibility_shadow import complete_registered_fork, distance
from audit_v23_split_echo_paths import graph_signature, is_registered, stable_ranks
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


FORMATION_RADIUS_UM = 14.0
VOXEL_SCALE_UM = np.asarray((1.625, 0.40625, 0.40625), dtype=float)
PROFILE_POINTS = 9


def local_normalization(volume: np.ndarray, center_um: np.ndarray) -> tuple[float, float]:
    center = center_um / VOXEL_SCALE_UM
    radius = np.ceil(FORMATION_RADIUS_UM / VOXEL_SCALE_UM).astype(int)
    lo = np.maximum(np.floor(center).astype(int) - radius, 0)
    hi = np.minimum(np.floor(center).astype(int) + radius + 1, np.asarray(volume.shape))
    patch = volume[tuple(slice(int(lo[i]), int(hi[i])) for i in range(3))].astype(float, copy=False)
    low, high = np.percentile(patch, (10.0, 99.5))
    return float(low), float(max(high - low, 1.0))


def normalized_profile(
    volume: np.ndarray,
    points_um: np.ndarray,
    normalization: tuple[float, float],
) -> np.ndarray:
    coordinates = (points_um / VOXEL_SCALE_UM).T
    values = map_coordinates(volume.astype(float, copy=False), coordinates, order=1, mode="nearest")
    low, scale = normalization
    return np.clip((values - low) / scale, 0.0, 2.0)


def topology_features(
    parent_um: np.ndarray,
    child_1_um: np.ndarray,
    child_2_um: np.ndarray,
    parent_volume: np.ndarray,
    daughter_volume: np.ndarray,
    parent_normalization: tuple[float, float],
    daughter_normalization: tuple[float, float],
) -> dict[str, float]:
    fractions = np.linspace(-0.5, 0.5, PROFILE_POINTS)
    axis = child_2_um - child_1_um
    parent_points = parent_um[None, :] + fractions[:, None] * axis[None, :]
    daughter_midpoint = 0.5 * (child_1_um + child_2_um)
    daughter_points = daughter_midpoint[None, :] + fractions[:, None] * axis[None, :]
    before = normalized_profile(parent_volume, parent_points, parent_normalization)
    after = normalized_profile(daughter_volume, daughter_points, daughter_normalization)
    before_center = float(np.mean(before[3:6]))
    before_ends = float(0.5 * (np.mean(before[:2]) + np.mean(before[-2:])))
    after_center = float(np.mean(after[3:6]))
    after_left = float(np.mean(after[:2]))
    after_right = float(np.mean(after[-2:]))
    parent_center_dominance = before_center - before_ends
    daughter_valley_depth = min(after_left, after_right) - after_center
    return {
        "parent_center_dominance": parent_center_dominance,
        "daughter_valley_depth": daughter_valley_depth,
        "candidate_axis_topology_change": parent_center_dominance + daughter_valley_depth,
        "static_endpoint_support": 0.5 * (after_left + after_right),
        "daughter_endpoint_balance": min(after_left, after_right) / max(after_left, after_right, 1e-12),
    }


def evaluate_case(train_dir: str, case: dict) -> dict:
    sample_id = case["sample_id"]
    t = int(case["t"])
    graph, detector, link_strategy = _build_v19_prefirewall_with_route(
        Path(train_dir) / f"{sample_id}.zarr", max_timepoints=t + 2
    )
    before_signature = graph_signature(graph)
    frame_nodes = defaultdict(list)
    for node in graph.detections:
        frame_nodes[int(node.t)].append(node)

    ground_truth = read_geff_graph(Path(train_dir) / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
    gt_parent = np.asarray(gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float)
    gt_daughters = [
        np.asarray(gt_nodes[int(child_id)].position_um, dtype=float)
        for child_id in case["gt_child_ids"]
    ]
    parent_candidates = [
        node for node in frame_nodes[t]
        if is_registered(np.asarray(node.position_um, dtype=float), gt_parent)
    ]
    focal = min(
        parent_candidates,
        key=lambda node: (distance(node.position_um, gt_parent), node.node_id),
    )
    correct = []
    for daughter in gt_daughters:
        candidates = [
            node for node in frame_nodes[t + 1]
            if is_registered(np.asarray(node.position_um, dtype=float), daughter)
        ]
        correct.append(min(candidates, key=lambda node: (distance(node.position_um, daughter), node.node_id)))
    correct_key = tuple(sorted(node.node_id for node in correct))

    parent_position = np.asarray(focal.position_um, dtype=float)
    local_children = [
        node for node in frame_nodes[t + 1]
        if distance(node.position_um, parent_position) <= FORMATION_RADIUS_UM
    ]
    pairs = list(itertools.combinations(sorted(local_children, key=lambda node: node.node_id), 2))
    array = open_competition_array(Path(train_dir) / f"{sample_id}.zarr")
    parent_volume = np.asarray(read_timepoint(array, t))
    daughter_volume = np.asarray(read_timepoint(array, t + 1))
    parent_norm = local_normalization(parent_volume, parent_position)
    daughter_norm = local_normalization(daughter_volume, parent_position)

    feature_rows = []
    for left, right in pairs:
        features = topology_features(
            parent_position,
            np.asarray(left.position_um, dtype=float),
            np.asarray(right.position_um, dtype=float),
            parent_volume,
            daughter_volume,
            parent_norm,
            daughter_norm,
        )
        feature_rows.append({
            "pair_key": tuple(sorted((left.node_id, right.node_id))),
            **features,
        })
    keys = [row["pair_key"] for row in feature_rows]
    topology_ranks = stable_ranks(
        [row["candidate_axis_topology_change"] for row in feature_rows], keys
    )
    static_ranks = stable_ranks([row["static_endpoint_support"] for row in feature_rows], keys)
    correct_index = next(index for index, row in enumerate(feature_rows) if row["pair_key"] == correct_key)
    topology_rank = int(topology_ranks[correct_index])
    static_rank = int(static_ranks[correct_index])
    count = len(feature_rows)
    return {
        "sample_id": sample_id,
        "family": case["family"],
        "t": t,
        "case_role": case["case_role"],
        "detector": detector,
        "link_strategy": link_strategy,
        "focal_parent_id": focal.node_id,
        "correct_daughter_ids": list(correct_key),
        "pair_count": count,
        "topology_rank": topology_rank,
        "topology_percentile": float(1.0 - (topology_rank - 1) / max(1, count)),
        "static_endpoint_rank": static_rank,
        "static_endpoint_percentile": float(1.0 - (static_rank - 1) / max(1, count)),
        "rank_delta_vs_static": static_rank - topology_rank,
        "correct_pair_features": {
            key: value for key, value in feature_rows[correct_index].items() if key != "pair_key"
        },
        "zero_perturbation": before_signature == graph_signature(graph),
        "candidate_set_changed": False,
        "graph_mutated": False,
    }


def summarize(rows: list[dict]) -> dict:
    family = {}
    for name in ("44b6", "6bba"):
        subset = [row for row in rows if row["family"] == name]
        family[name] = {
            "events": len(subset),
            "median_topology_percentile": (
                float(np.median([row["topology_percentile"] for row in subset]))
                if subset else 0.0
            ),
            "top10_capture": sum(row["topology_rank"] <= 10 for row in subset),
        }
    improved = sum(row["rank_delta_vs_static"] > 0 for row in rows)
    flat = sum(row["rank_delta_vs_static"] == 0 for row in rows)
    regressed = sum(row["rank_delta_vs_static"] < 0 for row in rows)
    pooled_median = float(np.median([row["topology_percentile"] for row in rows]))
    top10 = sum(row["topology_rank"] <= 10 for row in rows)
    go = (
        len(rows) == 6
        and pooled_median >= 0.75
        and all(item["median_topology_percentile"] >= 0.65 for item in family.values())
        and top10 >= 4
        and improved >= 4
        and regressed <= 1
    )
    hold = pooled_median >= 0.60 and top10 >= 2 and improved > regressed
    decision = "GO_TO_INDEPENDENT_TOPOLOGY_VALIDATION" if go else "HOLD_CANDIDATE_AXIS_TOPOLOGY" if hold else "NO_GO_CANDIDATE_AXIS_TOPOLOGY"
    return {
        "status": "read_only_v23_candidate_axis_topology",
        "decision": decision,
        "population": {"events": len(rows), "families": {name: family[name]["events"] for name in family}},
        "pooled_median_topology_percentile": pooled_median,
        "top10_capture": top10,
        "rank_vs_static": {"improved": improved, "flat": flat, "regressed": regressed},
        "family": family,
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
        "model_fitted": False,
    }


def write_outputs(rows: list[dict], output: Path, summary_path: Path, report: Path) -> dict:
    rows = sorted(rows, key=lambda row: (row["family"], row["sample_id"], int(row["t"])))
    summary = summarize(rows)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Candidate-Axis Topology Audit Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "This fixed six-event audit tests a raw-image one-lobe to two-lobe transition along each proposed daughter axis. Unknown alternatives remain unknown. No model was fitted and no graph was changed.",
        "",
        "| Event | Role | Family | Pairs | Topology rank | Percentile | Static rank | Delta |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['case_role']} | {row['family']} | "
            f"{row['pair_count']} | {row['topology_rank']} | {row['topology_percentile']:.1%} | "
            f"{row['static_endpoint_rank']} | {row['rank_delta_vs_static']:+d} |"
        )
    lines += [
        "",
        f"Pooled median percentile: {summary['pooled_median_topology_percentile']:.1%}. Top-10 capture: {summary['top10_capture']}/6. Rank improved/flat/regressed versus static endpoint support: {summary['rank_vs_static']['improved']}/{summary['rank_vs_static']['flat']}/{summary['rank_vs_static']['regressed']}.",
        "",
        "This differs from the rejected Hough precursor: Hough tested parent-frame bimodality alone, while this feature is candidate-conditioned and measures the temporal transition from one centered lobe to two endpoint lobes.",
        "",
        "Guardrail: even a GO would authorize only an independent sample-blocked validation of this raw feature source, not a scorer, assignment integration, graph mutation, or full-cohort run.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--ownership-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    source = json.loads(args.ownership_audit.read_text(encoding="utf-8"))
    protected = [{**row, "case_role": "protected_complete"} for row in source if complete_registered_fork(row)]
    repairable = [
        {**row, "case_role": "repairable"}
        for row in source
        if not complete_registered_fork(row)
        and row["diagnosis"] != "registered_parent_childless_missing_daughter_detection"
        and "missing_detection" not in row["nearest_daughter_ownership"]
    ]
    cases = protected + repairable
    if len(protected) != 3 or len(repairable) != 3 or {row["family"] for row in cases} != {"44b6", "6bba"}:
        raise RuntimeError(f"Frozen six-case partition mismatch: protected={len(protected)} repairable={len(repairable)}")
    if any(sum(row["family"] == family for row in cases) != 3 for family in ("44b6", "6bba")):
        raise RuntimeError("Frozen family balance mismatch")

    completed = []
    if args.resume and args.output.exists():
        completed = json.loads(args.output.read_text(encoding="utf-8"))
    completed_keys = {(row["sample_id"], int(row["t"])) for row in completed}
    pending = [row for row in cases if (row["sample_id"], int(row["t"])) not in completed_keys]
    print(f"completed={len(completed)} pending={len(pending)} total={len(cases)}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(evaluate_case, str(args.train_dir), row): row for row in pending}
        for future in as_completed(futures):
            row = future.result()
            completed.append(row)
            write_outputs(completed, args.output, args.summary, args.report)
            print(
                f"[{len(completed)}/{len(cases)}] {row['sample_id']} t{row['t']} "
                f"topology={row['topology_rank']}/{row['pair_count']} static={row['static_endpoint_rank']}",
                flush=True,
            )
    print(json.dumps(write_outputs(completed, args.output, args.summary, args.report), indent=2), flush=True)


if __name__ == "__main__":
    main()
