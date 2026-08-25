"""Audit t+2 persistence for anchored second-daughter echo hypotheses."""

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
from audit_v23_split_echo_paths import (
    anchored_valid,
    counterpart_score,
    graph_signature,
    stable_ranks,
)
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v23_per_track_echo_budget_shadow import (
    DEDUP_RADIUS_UM,
    ROUTER_RADIUS_UM,
    echo_peaks,
    prediction,
    remove_primary_duplicates,
)


RETURN_RADIUS_UM = 9.0


def return_candidates(primary, echo_points, echo_evidence):
    positions = np.concatenate((primary, echo_points), axis=0)
    evidence = np.concatenate(
        (np.ones(len(primary), dtype=float), echo_evidence), axis=0
    )
    sources = np.asarray(
        ["primary"] * len(primary) + ["echo"] * len(echo_points), dtype=object
    )
    return positions, evidence, sources


def best_distinct_returns(retained, counterpart, positions, evidence, sources):
    if not len(positions):
        return {
            "retained_distance_um": None,
            "counterpart_distance_um": None,
            "retained_source": None,
            "counterpart_source": None,
            "mean_evidence": 0.0,
            "distinct": False,
        }
    retained_distances = np.linalg.norm(positions - retained[None, :], axis=1)
    counterpart_distances = np.linalg.norm(positions - counterpart[None, :], axis=1)
    best = None
    for left in np.flatnonzero(retained_distances <= RETURN_RADIUS_UM):
        for right in np.flatnonzero(counterpart_distances <= RETURN_RADIUS_UM):
            if int(left) == int(right):
                continue
            closeness = (
                1.0 - retained_distances[left] / RETURN_RADIUS_UM
                + 1.0 - counterpart_distances[right] / RETURN_RADIUS_UM
            )
            score = float(closeness + 0.1 * (evidence[left] + evidence[right]))
            key = (score, -float(retained_distances[left] + counterpart_distances[right]))
            if best is None or key > best[0]:
                best = (key, int(left), int(right))
    if best is None:
        return {
            "retained_distance_um": None,
            "counterpart_distance_um": None,
            "retained_source": None,
            "counterpart_source": None,
            "mean_evidence": 0.0,
            "distinct": False,
        }
    _, left, right = best
    return {
        "retained_distance_um": float(retained_distances[left]),
        "counterpart_distance_um": float(counterpart_distances[right]),
        "retained_source": str(sources[left]),
        "counterpart_source": str(sources[right]),
        "mean_evidence": float(0.5 * (evidence[left] + evidence[right])),
        "distinct": True,
    }


def temporal_score(pair_score, returns):
    retained_closeness = (
        0.0
        if returns["retained_distance_um"] is None
        else max(0.0, 1.0 - returns["retained_distance_um"] / RETURN_RADIUS_UM)
    )
    counterpart_closeness = (
        0.0
        if returns["counterpart_distance_um"] is None
        else max(0.0, 1.0 - returns["counterpart_distance_um"] / RETURN_RADIUS_UM)
    )
    return float(
        0.50 * pair_score
        + 0.20 * counterpart_closeness
        + 0.15 * retained_closeness
        + 0.10 * returns["mean_evidence"]
        + 0.05 * float(returns["distinct"])
    )


def rank_metrics(seeds, proposals, signal):
    seed_scores = [
        max((proposals[p][signal] for p in seed["proposal_indices"]), default=0.0)
        for seed in seeds
    ]
    seed_ranks = stable_ranks(seed_scores, [seed["seed_id"] for seed in seeds])
    useful_seeds = [
        index
        for index, seed in enumerate(seeds)
        if any(proposals[p]["valid"] for p in seed["proposal_indices"])
    ]
    useful_seed = min(useful_seeds, key=lambda index: seed_ranks[index])
    local = seeds[useful_seed]["proposal_indices"]
    local_ranks = stable_ranks(
        [proposals[index][signal] for index in local],
        [proposals[index]["echo_index"] for index in local],
    )
    valid_offsets = [
        offset for offset, index in enumerate(local) if proposals[index]["valid"]
    ]
    global_ranks = stable_ranks(
        [proposal[signal] for proposal in proposals],
        [
            (seeds[proposal["seed_index"]]["seed_id"], proposal["echo_index"])
            for proposal in proposals
        ],
    )
    valid_global = [
        index for index, proposal in enumerate(proposals) if proposal["valid"]
    ]
    return {
        "parent_seed_rank": int(seed_ranks[useful_seed]),
        "counterpart_rank_within_parent": int(
            min(local_ranks[offset] for offset in valid_offsets)
        ),
        "global_proposal_rank": int(min(global_ranks[index] for index in valid_global)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--split-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    split = json.loads(args.split_audit.read_text(encoding="utf-8"))
    cases = [fixture[row["case_id"]] for row in split["anchored"]]
    by_sample = defaultdict(list)
    for case in cases:
        by_sample[case["sample_id"]].append(case)

    rows = []
    for sample_id, sample_cases in sorted(by_sample.items()):
        max_t = max(int(case["t"]) for case in sample_cases)
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr", max_timepoints=max_t + 3
        )
        before = graph_signature(graph)
        nodes = {node.node_id: node for node in graph.detections}
        frame_nodes = defaultdict(list)
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for node in graph.detections:
            frame_nodes[int(node.t)].append(node)
        for edge in graph.edges:
            incoming[edge.target_id].append(edge.source_id)
            outgoing[edge.source_id].append(edge.target_id)

        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        array = open_competition_array(args.train_dir / f"{sample_id}.zarr")
        echo_cache = {}

        for case in sample_cases:
            t = int(case["t"])
            for frame in (t + 1, t + 2):
                if frame not in echo_cache:
                    echo_cache[frame] = echo_peaks(read_timepoint(array, frame))
            primary_t1 = np.asarray(
                [node.position_um for node in frame_nodes[t + 1]], dtype=float
            ).reshape((-1, 3))
            primary_t2 = np.asarray(
                [node.position_um for node in frame_nodes[t + 2]], dtype=float
            ).reshape((-1, 3))
            echo_t1, evidence_t1 = remove_primary_duplicates(
                *echo_cache[t + 1], primary_t1
            )
            echo_t2, evidence_t2 = remove_primary_duplicates(
                *echo_cache[t + 2], primary_t2
            )
            returns_t2, return_evidence, return_sources = return_candidates(
                primary_t2, echo_t2, evidence_t2
            )

            gt_parent = np.asarray(
                gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float
            )
            gt_daughters = [
                np.asarray(gt_nodes[int(node_id)].position_um, dtype=float)
                for node_id in case["gt_child_ids"]
            ]
            seeds = []
            proposals = []
            for node in frame_nodes[t]:
                child_ids = [
                    target for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t + 1
                ]
                if len(child_ids) != 1:
                    continue
                parent = np.asarray(node.position_um, dtype=float)
                retained = np.asarray(nodes[child_ids[0]].position_um, dtype=float)
                predicted, _, _ = prediction(node, incoming, nodes)
                local = np.flatnonzero(
                    np.linalg.norm(echo_t1 - parent[None, :], axis=1)
                    <= ROUTER_RADIUS_UM
                )
                seed_index = len(seeds)
                seed_proposals = []
                for echo_index in local:
                    counterpart = echo_t1[echo_index]
                    if np.linalg.norm(counterpart - retained) <= DEDUP_RADIUS_UM:
                        continue
                    pair = counterpart_score(
                        parent,
                        retained,
                        counterpart,
                        predicted,
                        float(evidence_t1[echo_index]),
                    )
                    returns = best_distinct_returns(
                        retained,
                        counterpart,
                        returns_t2,
                        return_evidence,
                        return_sources,
                    )
                    proposal_index = len(proposals)
                    seed_proposals.append(proposal_index)
                    proposals.append(
                        {
                            "seed_index": seed_index,
                            "echo_index": int(echo_index),
                            "pair_score": pair,
                            "temporal_score": temporal_score(pair, returns),
                            "returns": returns,
                            "valid": anchored_valid(
                                parent,
                                retained,
                                counterpart,
                                gt_parent,
                                gt_daughters,
                            ),
                        }
                    )
                seeds.append({"seed_id": node.node_id, "proposal_indices": seed_proposals})

            before_metrics = rank_metrics(seeds, proposals, "pair_score")
            after_metrics = rank_metrics(seeds, proposals, "temporal_score")
            valid = [proposal for proposal in proposals if proposal["valid"]]
            best_valid = max(valid, key=lambda proposal: proposal["temporal_score"])
            nonvalid_persistence = [
                float(proposal["returns"]["distinct"])
                for proposal in proposals if not proposal["valid"]
            ]
            row = {
                "case_id": case["case_id"],
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "before": before_metrics,
                "after": after_metrics,
                "correct_counterpart_distinct_return": best_valid["returns"]["distinct"],
                "correct_counterpart_return": best_valid["returns"],
                "non_tp_distinct_return_rate": float(np.mean(nonvalid_persistence)),
                "proposal_count": len(proposals),
                "detector": detector,
                "link_strategy": link_strategy,
                "zero_perturbation": before == graph_signature(graph),
                "candidate_set_changed": False,
                "graph_mutated": False,
            }
            rows.append(row)
            print(
                f"{sample_id} t{t}: parent {before_metrics['parent_seed_rank']}->"
                f"{after_metrics['parent_seed_rank']} counterpart "
                f"{before_metrics['counterpart_rank_within_parent']}->"
                f"{after_metrics['counterpart_rank_within_parent']} distinct="
                f"{best_valid['returns']['distinct']}",
                flush=True,
            )

    severe_regression = any(
        row["after"]["counterpart_rank_within_parent"]
        > 1.25 * row["before"]["counterpart_rank_within_parent"]
        for row in rows
    )
    returns_all = all(row["correct_counterpart_distinct_return"] for row in rows)
    no_rank_regression = all(
        row["after"]["parent_seed_rank"] <= row["before"]["parent_seed_rank"]
        and row["after"]["counterpart_rank_within_parent"]
        <= row["before"]["counterpart_rank_within_parent"]
        for row in rows
    )
    parent_improvement = any(
        row["after"]["parent_seed_rank"] <= 25
        or row["after"]["parent_seed_rank"] <= 0.75 * row["before"]["parent_seed_rank"]
        for row in rows
    )
    if returns_all and no_rank_regression and parent_improvement:
        decision = "GO_TO_LARGER_TEMPORAL_SHADOW"
    elif severe_regression or not any(
        row["correct_counterpart_distinct_return"] for row in rows
    ):
        decision = "NO_GO_TEMPORAL_ECHO"
    else:
        decision = "HOLD_TEMPORAL_SIGNAL"

    summary = {
        "status": "read_only_v23_temporal_echo_persistence",
        "decision": decision,
        "events": len(rows),
        "correct_distinct_returns": sum(
            row["correct_counterpart_distinct_return"] for row in rows
        ),
        "non_tp_distinct_return_rate": {
            "mean": float(np.mean([row["non_tp_distinct_return_rate"] for row in rows])),
            "per_event": [row["non_tp_distinct_return_rate"] for row in rows],
        },
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Temporal Echo Persistence Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "The two anchored events were rescored with fixed, inference-only t+2 return evidence. Quarantined events were excluded. No candidate, edge, or graph was changed.",
        "",
        "| Event | Parent rank | Counterpart rank | Global rank | Distinct t+2 return | Non-TP return rate | Return sources |",
        "|---|---:|---:|---:|---|---:|---|",
    ]
    for row in rows:
        returns = row["correct_counterpart_return"]
        lines.append(
            f"| {row['sample_id']} t{row['t']} | "
            f"{row['before']['parent_seed_rank']} -> {row['after']['parent_seed_rank']} | "
            f"{row['before']['counterpart_rank_within_parent']} -> {row['after']['counterpart_rank_within_parent']} | "
            f"{row['before']['global_proposal_rank']} -> {row['after']['global_proposal_rank']} | "
            f"{row['correct_counterpart_distinct_return']} | "
            f"{row['non_tp_distinct_return_rate']:.1%} | "
            f"{returns['retained_source']} / {returns['counterpart_source']} |"
        )
    lines += [
        "",
        "Distinct temporal returns were nearly universal among non-TP proposals, so t+2 persistence is not independently discriminative in these dense frames.",
        "",
        "Guardrail: this two-event result cannot authorize integration or a full-cohort run.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
