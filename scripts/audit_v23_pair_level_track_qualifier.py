"""Audit pair-level qualification for the four frozen K=1 echo recoveries."""

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
    ROUTER_RADIUS_UM,
    assign_proposals,
    echo_peaks,
    prediction,
    remove_primary_duplicates,
)


SIGNALS = ("best_pair_score", "density_penalized_pair_score")
SEED_TOP_NS = (5, 10, 25, 50)
PAIR_TOP_NS = (1, 5, 10, 25)


def signature(graph):
    nodes = tuple((node.node_id, int(node.t), *node.position_um) for node in graph.detections)
    edges = tuple((edge.source_id, edge.target_id, edge.relation) for edge in graph.edges)
    return nodes, edges


def nearest_distance(points, target):
    if not len(points):
        return ROUTER_RADIUS_UM
    return float(np.linalg.norm(points - target[None, :], axis=1).min())


def valid_registered_pair(parent, left, right, gt_parent, gt_daughters):
    if np.linalg.norm(parent - gt_parent) > 7.0:
        return False
    direct = (
        np.linalg.norm(left - gt_daughters[0]) <= 7.0
        and np.linalg.norm(right - gt_daughters[1]) <= 7.0
    )
    swapped = (
        np.linalg.norm(left - gt_daughters[1]) <= 7.0
        and np.linalg.norm(right - gt_daughters[0]) <= 7.0
    )
    return bool(direct or swapped)


def score_seed_pairs(seed, positions, evidence, gt_parent, gt_daughters):
    local_indices = np.flatnonzero(
        np.linalg.norm(positions - seed["parent"][None, :], axis=1)
        <= ROUTER_RADIUS_UM
    )
    pair_scores = []
    pair_valid = []
    for offset, left_index in enumerate(local_indices):
        left = positions[left_index]
        left_radius = float(np.linalg.norm(left - seed["parent"]))
        for right_index in local_indices[offset + 1 :]:
            right = positions[right_index]
            separation = float(np.linalg.norm(left - right))
            if separation <= 1e-9:
                continue
            right_radius = float(np.linalg.norm(right - seed["parent"]))
            midpoint = 0.5 * (left + right)
            midpoint_error = float(np.linalg.norm(midpoint - seed["prediction"]))
            midpoint_closeness = max(0.0, 1.0 - midpoint_error / ROUTER_RADIUS_UM)
            radial_balance = 1.0 - abs(left_radius - right_radius) / max(
                left_radius, right_radius, 1e-6
            )
            separation_support = min(1.0, separation / 3.0)
            candidate_evidence = 0.5 * (
                float(evidence[left_index]) + float(evidence[right_index])
            )
            score = (
                0.45 * midpoint_closeness
                + 0.25 * radial_balance
                + 0.15 * separation_support
                + 0.15 * candidate_evidence
            )
            pair_scores.append(score)
            pair_valid.append(
                valid_registered_pair(
                    seed["parent"], left, right, gt_parent, gt_daughters
                )
            )
    if not pair_scores:
        return {
            "pair_count": 0,
            "best_pair_score": 0.0,
            "density_penalized_pair_score": 0.0,
            "best_valid_pair_rank": None,
        }
    scores = np.asarray(pair_scores, dtype=float)
    order = np.argsort(-scores, kind="stable")
    valid_rank = next(
        (rank for rank, index in enumerate(order, start=1) if pair_valid[int(index)]),
        None,
    )
    best = float(scores[order[0]])
    return {
        "pair_count": len(pair_scores),
        "best_pair_score": best,
        "density_penalized_pair_score": best / np.sqrt(len(pair_scores)),
        "best_valid_pair_rank": valid_rank,
    }


def seed_rank_map(seeds, signal):
    ordered = sorted(
        range(len(seeds)),
        key=lambda index: (-seeds[index][signal], seeds[index]["seed_id"]),
    )
    return {seed_index: rank for rank, seed_index in enumerate(ordered, start=1)}


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
    recovered_ids = {
        row["case_id"] for row in budget_rows if row["budgets"]["1"]["recovered"]
    }
    by_sample = defaultdict(list)
    for row in prior:
        if row["case_id"] not in recovered_ids:
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
            parent_echo, parent_margins = remove_primary_duplicates(
                *echo_cache[t], primary_parent
            )
            daughter_echo, daughter_margins = remove_primary_duplicates(
                *echo_cache[t + 1], primary_daughter
            )
            daughter_positions = np.concatenate(
                (primary_daughter, daughter_echo), axis=0
            )
            daughter_evidence = np.concatenate(
                (np.ones(len(primary_daughter), dtype=float), daughter_margins), axis=0
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
                broken.append({
                    "seed_id": node.node_id,
                    "anchor": predicted,
                    "prediction": predicted,
                    "next_prediction": predicted + velocity,
                    "mode": mode,
                    "capacity": 2,
                    "nearest_primary_prediction_error_um": nearest_distance(
                        primary_parent, predicted
                    ),
                })
            selected_parents, _ = assign_proposals(
                parent_echo, parent_margins, broken, 1
            )

            pair_seeds = []
            for node in frame_nodes[t]:
                next_ids = [
                    target for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t + 1
                ]
                if len(next_ids) >= 2:
                    continue
                predicted, _, mode = prediction(node, incoming, nodes)
                pair_seeds.append({
                    "seed_id": node.node_id,
                    "parent": np.asarray(node.position_um, dtype=float),
                    "prediction": predicted,
                    "mode": mode,
                    "source": "primary_parent",
                })
            for proposal in selected_parents:
                source = broken[proposal["seed_index"]]
                pair_seeds.append({
                    "seed_id": f"echo:{source['seed_id']}",
                    "parent": proposal["position"],
                    "prediction": source["next_prediction"],
                    "mode": source["mode"],
                    "source": "echo_parent",
                })

            gt_parent = np.asarray(
                gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float
            )
            gt_daughters = [
                np.asarray(gt_nodes[int(node_id)].position_um, dtype=float)
                for node_id in case["gt_child_ids"]
            ]
            for seed in pair_seeds:
                seed.update(
                    score_seed_pairs(
                        seed,
                        daughter_positions,
                        daughter_evidence,
                        gt_parent,
                        gt_daughters,
                    )
                )

            signal_results = {}
            for signal in SIGNALS:
                ranks = seed_rank_map(pair_seeds, signal)
                useful = [
                    index for index, seed in enumerate(pair_seeds)
                    if seed["best_valid_pair_rank"] is not None
                ]
                if useful:
                    best_seed_index = min(useful, key=lambda index: ranks[index])
                    signal_results[signal] = {
                        "best_useful_seed_rank": ranks[best_seed_index],
                        "valid_pair_rank_within_seed": pair_seeds[best_seed_index][
                            "best_valid_pair_rank"
                        ],
                        "seed_population": len(pair_seeds),
                        "pair_count_in_useful_seed": pair_seeds[best_seed_index]["pair_count"],
                        "useful_seed_source": pair_seeds[best_seed_index]["source"],
                    }
                else:
                    signal_results[signal] = {
                        "best_useful_seed_rank": None,
                        "valid_pair_rank_within_seed": None,
                        "seed_population": len(pair_seeds),
                        "pair_count_in_useful_seed": None,
                        "useful_seed_source": None,
                    }
            rows.append({
                "case_id": case["case_id"],
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "detector": detector,
                "link_strategy": link_strategy,
                "signals": signal_results,
                "zero_perturbation": before == signature(graph),
                "candidate_set_changed": False,
                "graph_mutated": False,
            })
            print(
                f"{sample_id} t{t}: "
                + " ".join(
                    f"{signal}=seed{signal_results[signal]['best_useful_seed_rank']}"
                    f"/pair{signal_results[signal]['valid_pair_rank_within_seed']}"
                    for signal in SIGNALS
                ),
                flush=True,
            )

    signal_summaries = {}
    for signal in SIGNALS:
        seed_capture = {
            str(top_n): sum(
                row["signals"][signal]["best_useful_seed_rank"] is not None
                and row["signals"][signal]["best_useful_seed_rank"] <= top_n
                for row in rows
            )
            for top_n in SEED_TOP_NS
        }
        pair_capture = {
            str(top_n): sum(
                row["signals"][signal]["valid_pair_rank_within_seed"] is not None
                and row["signals"][signal]["valid_pair_rank_within_seed"] <= top_n
                for row in rows
            )
            for top_n in PAIR_TOP_NS
        }
        joint_top25_top10 = sum(
            row["signals"][signal]["best_useful_seed_rank"] is not None
            and row["signals"][signal]["best_useful_seed_rank"] <= 25
            and row["signals"][signal]["valid_pair_rank_within_seed"] <= 10
            for row in rows
        )
        family_joint = {
            family: sum(
                row["family"] == family
                and row["signals"][signal]["best_useful_seed_rank"] is not None
                and row["signals"][signal]["best_useful_seed_rank"] <= 25
                and row["signals"][signal]["valid_pair_rank_within_seed"] <= 10
                for row in rows
            )
            for family in sorted({row["family"] for row in rows})
        }
        signal_summaries[signal] = {
            "seed_top_n_capture": seed_capture,
            "pair_top_n_capture": pair_capture,
            "joint_top25_seed_top10_pair": joint_top25_top10,
            "family_joint_capture": family_joint,
        }

    eligible = [
        signal for signal, result in signal_summaries.items()
        if result["joint_top25_seed_top10_pair"] >= 3
        and all(count > 0 for count in result["family_joint_capture"].values())
    ]
    best_joint = max(
        result["joint_top25_seed_top10_pair"] for result in signal_summaries.values()
    )
    decision = (
        "GO_TO_PAIR_ASSIGNMENT_SHADOW" if eligible
        else "HOLD" if best_joint >= 2
        else "NO_GO"
    )
    summary = {
        "status": "read_only_v23_pair_level_track_qualifier",
        "population": {"events": len(rows)},
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
        "# V23 Pair-Level Track Qualifier Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "The four frozen K=1 recoveries were ranked by complete local daughter-pair hypotheses. Scores were inference-only; GT was used only to locate registered-valid pair ranks after construction.",
        "",
        "| Signal | Seed top 25 | Pair top 10 | Joint seed<=25 and pair<=10 |",
        "|---|---:|---:|---:|",
    ]
    for signal in SIGNALS:
        result = signal_summaries[signal]
        lines.append(
            f"| `{signal}` | {result['seed_top_n_capture']['25']}/4 | "
            f"{result['pair_top_n_capture']['10']}/4 | "
            f"{result['joint_top25_seed_top10_pair']}/4 |"
        )
    lines += [
        "",
        "## Event Ranks",
        "",
        "| Event | Family | Raw pair seed/pair | Density pair seed/pair |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        raw = row["signals"]["best_pair_score"]
        density = row["signals"]["density_penalized_pair_score"]
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['family']} | "
            f"{raw['best_useful_seed_rank']} / {raw['valid_pair_rank_within_seed']} | "
            f"{density['best_useful_seed_rank']} / {density['valid_pair_rank_within_seed']} |"
        )
    lines += [
        "",
        "Guardrail: this is pair-ranking evidence only. It does not authorize proposal emission, fitting, graph mutation, or full-cohort execution.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
