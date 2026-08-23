"""Rank useful echo-router seeds using inference-only evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v23_per_track_echo_budget_shadow import (
    BUDGETS,
    CFAR_WEIGHT,
    PREDICTION_WEIGHT,
    ROUTER_RADIUS_UM,
    assign_proposals,
    echo_peaks,
    geometry_available,
    prediction,
    remove_primary_duplicates,
)


SIGNALS = (
    "best_echo_score",
    "gap_score",
    "combined_score",
    "density_penalized_score",
)
TOP_NS = (5, 10, 25, 50)


def signature(graph):
    nodes = tuple((node.node_id, int(node.t), *node.position_um) for node in graph.detections)
    edges = tuple((edge.source_id, edge.target_id, edge.relation) for edge in graph.edges)
    return nodes, edges


def nearest_distance(points, target):
    if not len(points):
        return ROUTER_RADIUS_UM
    return float(np.linalg.norm(points - target[None, :], axis=1).min())


def seed_features(seed, points, margins):
    anchor_distances = (
        np.linalg.norm(points - seed["anchor"][None, :], axis=1)
        if len(points)
        else np.empty(0, dtype=float)
    )
    prediction_distances = (
        np.linalg.norm(points - seed["prediction"][None, :], axis=1)
        if len(points)
        else np.empty(0, dtype=float)
    )
    local = anchor_distances <= ROUTER_RADIUS_UM
    if np.any(local):
        closeness = np.maximum(0.0, 1.0 - prediction_distances[local] / ROUTER_RADIUS_UM)
        proposal_scores = PREDICTION_WEIGHT * closeness + CFAR_WEIGHT * margins[local]
        best_echo_score = float(proposal_scores.max())
        local_echo_count = int(np.sum(local))
    else:
        best_echo_score = 0.0
        local_echo_count = 0
    gap_score = float(np.clip(seed["nearest_primary_prediction_error_um"] / ROUTER_RADIUS_UM, 0, 1))
    capacity_score = float(np.clip(seed["capacity"] / 2.0, 0, 1))
    history_score = 1.0 if seed["mode"] == "velocity" else 0.0
    combined = (
        0.45 * best_echo_score
        + 0.30 * gap_score
        + 0.15 * capacity_score
        + 0.10 * history_score
    )
    return {
        "best_echo_score": best_echo_score,
        "gap_score": gap_score,
        "combined_score": combined,
        "density_penalized_score": combined / np.sqrt(max(1, local_echo_count)),
        "local_echo_count": local_echo_count,
        "capacity_score": capacity_score,
        "history_score": history_score,
    }


def rank_map(seeds, signal):
    ordered = sorted(
        range(len(seeds)),
        key=lambda index: (-seeds[index]["features"][signal], seeds[index]["seed_id"]),
    )
    return {seed_index: rank for rank, seed_index in enumerate(ordered, start=1)}


def within_7(position, target):
    return float(np.linalg.norm(np.asarray(position) - np.asarray(target))) <= 7.0


def participating_indices(parent_points, daughter_points, gt_parent, gt_daughters):
    parent_participants = set()
    daughter_participants = set()
    parent_indices = [index for index, point in enumerate(parent_points) if np.linalg.norm(point - gt_parent) <= 7.0]
    left_indices = [index for index, point in enumerate(daughter_points) if np.linalg.norm(point - gt_daughters[0]) <= 7.0]
    right_indices = [index for index, point in enumerate(daughter_points) if np.linalg.norm(point - gt_daughters[1]) <= 7.0]
    for parent_index in parent_indices:
        parent = parent_points[parent_index]
        for left_index in left_indices:
            for right_index in right_indices:
                if left_index == right_index:
                    continue
                if np.linalg.norm(daughter_points[left_index] - parent) <= 14.0 and np.linalg.norm(daughter_points[right_index] - parent) <= 14.0:
                    parent_participants.add(parent_index)
                    daughter_participants.update((left_index, right_index))
    return parent_participants, daughter_participants


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--pre-post", type=Path, required=True)
    parser.add_argument("--budget-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    prior = json.loads(args.pre_post.read_text(encoding="utf-8"))
    budget_rows = json.loads(args.budget_audit.read_text(encoding="utf-8"))
    recovered_case_ids = {row["case_id"] for row in budget_rows if row["budgets"]["1"]["recovered"]}
    baseline_available = {
        row["case_id"]: bool(row["post_official_geometry_available"]) for row in prior
    }
    by_sample = defaultdict(list)
    for row in prior:
        if row["case_id"] not in recovered_case_ids:
            continue
        case = fixture[row["case_id"]]
        by_sample[case["sample_id"]].append(case)

    rows = []
    for sample_id, cases in by_sample.items():
        max_t = max(int(case["t"]) for case in cases)
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr", max_timepoints=max_t + 2
        )
        before = signature(graph)
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

            broken = []
            for node in frame_nodes[t - 1]:
                next_ids = [
                    target for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t
                ]
                if next_ids:
                    continue
                predicted, velocity, mode = prediction(node, incoming, nodes)
                seed = {
                    "seed_id": node.node_id,
                    "anchor": predicted,
                    "prediction": predicted,
                    "next_prediction": predicted + velocity,
                    "mode": mode,
                    "capacity": 2,
                    "nearest_primary_prediction_error_um": nearest_distance(primary_parent, predicted),
                    "stage": "parent",
                }
                seed["features"] = seed_features(seed, parent_points, parent_margins)
                broken.append(seed)

            under_resolved = []
            for node in frame_nodes[t]:
                next_ids = [
                    target for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t + 1
                ]
                if len(next_ids) >= 2:
                    continue
                predicted, _, mode = prediction(node, incoming, nodes)
                seed = {
                    "seed_id": node.node_id,
                    "anchor": np.asarray(node.position_um, dtype=float),
                    "prediction": predicted,
                    "mode": mode,
                    "capacity": 2 - len(next_ids),
                    "nearest_primary_prediction_error_um": nearest_distance(primary_daughter, predicted),
                    "stage": "daughter",
                }
                seed["features"] = seed_features(seed, daughter_points, daughter_margins)
                under_resolved.append(seed)

            selected_parents, _ = assign_proposals(parent_points, parent_margins, broken, 1)
            virtual = []
            for proposal in selected_parents:
                source = broken[proposal["seed_index"]]
                seed = {
                    "seed_id": f"echo:{source['seed_id']}",
                    "anchor": proposal["position"],
                    "prediction": source["next_prediction"],
                    "mode": source["mode"],
                    "capacity": 2,
                    "nearest_primary_prediction_error_um": nearest_distance(
                        primary_daughter, source["next_prediction"]
                    ),
                    "stage": "daughter",
                    "source_parent_seed_index": proposal["seed_index"],
                }
                seed["features"] = seed_features(seed, daughter_points, daughter_margins)
                virtual.append(seed)
            daughter_seeds = under_resolved + virtual
            selected_daughters, _ = assign_proposals(
                daughter_points, daughter_margins, daughter_seeds, 1
            )

            gt_parent = np.asarray(
                gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float
            )
            gt_daughters = [
                np.asarray(gt_nodes[int(node_id)].position_um, dtype=float)
                for node_id in case["gt_child_ids"]
            ]
            combined_parent = np.concatenate(
                (primary_parent, np.asarray([item["position"] for item in selected_parents]).reshape((-1, 3))),
                axis=0,
            ) if selected_parents else primary_parent
            combined_daughter = np.concatenate(
                (primary_daughter, np.asarray([item["position"] for item in selected_daughters]).reshape((-1, 3))),
                axis=0,
            ) if selected_daughters else primary_daughter
            primary_available = geometry_available(
                primary_parent, primary_daughter, gt_parent, gt_daughters
            )
            recovered = (
                not primary_available
                and geometry_available(combined_parent, combined_daughter, gt_parent, gt_daughters)
            )

            parent_participants, daughter_participants = participating_indices(
                combined_parent, combined_daughter, gt_parent, gt_daughters
            )
            parent_offset = len(primary_parent)
            daughter_offset = len(primary_daughter)
            useful_parent = {
                item["seed_index"]
                for proposal_index, item in enumerate(selected_parents)
                if parent_offset + proposal_index in parent_participants
            }
            useful_daughter = {
                item["seed_index"]
                for proposal_index, item in enumerate(selected_daughters)
                if daughter_offset + proposal_index in daughter_participants
            }

            rank_results = {}
            for signal in SIGNALS:
                parent_ranks = rank_map(broken, signal)
                daughter_ranks = rank_map(daughter_seeds, signal)
                ranks = [parent_ranks[index] for index in useful_parent]
                ranks.extend(daughter_ranks[index] for index in useful_daughter)
                rank_results[signal] = {
                    "best_useful_rank": min(ranks) if ranks else None,
                    "useful_seed_count": len(ranks),
                    "parent_seed_population": len(broken),
                    "daughter_seed_population": len(daughter_seeds),
                }
            rows.append({
                "case_id": case["case_id"],
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "cohort": "control" if baseline_available[case["case_id"]] else "failure",
                "detector": detector,
                "link_strategy": link_strategy,
                "primary_available": primary_available,
                "k1_recovered": recovered,
                "useful_parent_seed_count": len(useful_parent),
                "useful_daughter_seed_count": len(useful_daughter),
                "ranks": rank_results,
                "zero_perturbation": before == signature(graph),
                "candidate_set_changed": False,
                "graph_mutated": False,
            })
            print(
                f"{sample_id} t{t}: recovered={recovered} "
                + " ".join(
                    f"{signal}={rank_results[signal]['best_useful_rank']}"
                    for signal in SIGNALS
                ),
                flush=True,
            )

    recovered_rows = [row for row in rows if row["k1_recovered"]]
    signal_summaries = {}
    for signal in SIGNALS:
        signal_summaries[signal] = {
            "top_n_capture": {
                str(top_n): sum(
                    row["ranks"][signal]["best_useful_rank"] is not None
                    and row["ranks"][signal]["best_useful_rank"] <= top_n
                    for row in recovered_rows
                )
                for top_n in TOP_NS
            },
            "family_top25": {
                family: sum(
                    row["family"] == family
                    and row["ranks"][signal]["best_useful_rank"] is not None
                    and row["ranks"][signal]["best_useful_rank"] <= 25
                    for row in recovered_rows
                )
                for family in sorted({row["family"] for row in recovered_rows})
            },
        }
    eligible = [
        signal for signal, result in signal_summaries.items()
        if result["top_n_capture"]["25"] >= 3
        and all(count > 0 for count in result["family_top25"].values())
    ]
    best_top50 = max(result["top_n_capture"]["50"] for result in signal_summaries.values())
    decision = (
        "GO_TO_TRACK_QUALIFIER_SHADOW" if eligible
        else "HOLD" if best_top50 >= 2
        else "NO_GO"
    )
    summary = {
        "status": "read_only_v23_track_seed_ranking",
        "population": {"events": len(rows), "k1_recoveries": len(recovered_rows)},
        "decision": decision,
        "eligible_signals": eligible,
        "signals": signal_summaries,
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 Track-Seed Ranking Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "The ranking population is the four recovery events frozen by the prior K=1 audit. Useful seeds were labeled only when their assigned proposal participated in a valid recovered fork. All ranking signals were computed before GT comparison and no model was fitted.",
        "",
        "| Signal | Top 5 | Top 10 | Top 25 | Top 50 |",
        "|---|---:|---:|---:|---:|",
    ]
    for signal in SIGNALS:
        capture = signal_summaries[signal]["top_n_capture"]
        lines.append(
            f"| `{signal}` | {capture['5']}/4 | {capture['10']}/4 | "
            f"{capture['25']}/4 | {capture['50']}/4 |"
        )
    lines += [
        "",
        "## Recovered Event Ranks",
        "",
        "| Event | Family | Best echo | Gap | Combined | Density-penalized |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in recovered_rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['family']} | "
            f"{row['ranks']['best_echo_score']['best_useful_rank']} | "
            f"{row['ranks']['gap_score']['best_useful_rank']} | "
            f"{row['ranks']['combined_score']['best_useful_rank']} | "
            f"{row['ranks']['density_penalized_score']['best_useful_rank']} |"
        )
    lines += [
        "",
        "Guardrail: this is seed-ranking evidence only. It does not authorize proposal emission, score fitting, graph mutation, or full-cohort execution.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()






