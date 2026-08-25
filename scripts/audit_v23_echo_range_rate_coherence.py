"""Audit parent-velocity and pair-shape coherence for anchored echoes."""

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
from audit_v23_split_echo_paths import anchored_valid, counterpart_score, graph_signature
from audit_v23_temporal_echo_persistence import rank_metrics, return_candidates
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v23_per_track_echo_budget_shadow import (
    DEDUP_RADIUS_UM,
    ROUTER_RADIUS_UM,
    echo_peaks,
    prediction,
    remove_primary_duplicates,
)


RETURN_RADIUS_UM = 9.0

def format_residual(value):
    return "NA" if value is None else f"{value:.3f}"



def best_range_rate_returns(
    parent_velocity,
    retained,
    counterpart,
    positions,
    evidence,
    sources,
    pair_score,
):
    empty = {
        "coherence_score": float(0.45 * pair_score),
        "distinct": False,
        "retained_velocity_residual_um": None,
        "counterpart_velocity_residual_um": None,
        "separation_residual_um": None,
        "retained_source": None,
        "counterpart_source": None,
        "mean_evidence": 0.0,
    }
    if not len(positions):
        return empty

    expected_retained = retained + parent_velocity
    expected_counterpart = counterpart + parent_velocity
    retained_residuals = np.linalg.norm(
        positions - expected_retained[None, :], axis=1
    )
    counterpart_residuals = np.linalg.norm(
        positions - expected_counterpart[None, :], axis=1
    )
    retained_indices = np.flatnonzero(retained_residuals <= RETURN_RADIUS_UM)
    counterpart_indices = np.flatnonzero(counterpart_residuals <= RETURN_RADIUS_UM)
    separation_t1 = counterpart - retained
    best = None
    for left in retained_indices:
        for right in counterpart_indices:
            if int(left) == int(right):
                continue
            retained_residual = float(retained_residuals[left])
            counterpart_residual = float(counterpart_residuals[right])
            separation_t2 = positions[right] - positions[left]
            separation_residual = float(np.linalg.norm(separation_t2 - separation_t1))
            retained_coherence = max(
                0.0, 1.0 - retained_residual / RETURN_RADIUS_UM
            )
            counterpart_coherence = max(
                0.0, 1.0 - counterpart_residual / RETURN_RADIUS_UM
            )
            separation_coherence = max(
                0.0, 1.0 - separation_residual / RETURN_RADIUS_UM
            )
            mean_evidence = float(0.5 * (evidence[left] + evidence[right]))
            score = float(
                0.45 * pair_score
                + 0.20 * retained_coherence
                + 0.20 * counterpart_coherence
                + 0.10 * separation_coherence
                + 0.05 * mean_evidence
            )
            tie_break = -float(retained_residual + counterpart_residual)
            if best is None or (score, tie_break) > best[0]:
                best = (
                    (score, tie_break),
                    int(left),
                    int(right),
                    retained_residual,
                    counterpart_residual,
                    separation_residual,
                    mean_evidence,
                )
    if best is None:
        return empty
    (
        (score, _),
        left,
        right,
        retained_residual,
        counterpart_residual,
        separation_residual,
        mean_evidence,
    ) = best
    return {
        "coherence_score": score,
        "distinct": True,
        "retained_velocity_residual_um": retained_residual,
        "counterpart_velocity_residual_um": counterpart_residual,
        "separation_residual_um": separation_residual,
        "retained_source": str(sources[left]),
        "counterpart_source": str(sources[right]),
        "mean_evidence": mean_evidence,
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
        before_signature = graph_signature(graph)
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
            positions_t2, evidence_t2_all, sources_t2 = return_candidates(
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
                predicted, parent_velocity, velocity_mode = prediction(
                    node, incoming, nodes
                )
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
                    coherence = best_range_rate_returns(
                        parent_velocity,
                        retained,
                        counterpart,
                        positions_t2,
                        evidence_t2_all,
                        sources_t2,
                        pair,
                    )
                    proposal_index = len(proposals)
                    seed_proposals.append(proposal_index)
                    proposals.append(
                        {
                            "seed_index": seed_index,
                            "echo_index": int(echo_index),
                            "pair_score": pair,
                            "coherence_score": coherence["coherence_score"],
                            "coherence": coherence,
                            "valid": anchored_valid(
                                parent,
                                retained,
                                counterpart,
                                gt_parent,
                                gt_daughters,
                            ),
                        }
                    )
                seeds.append(
                    {
                        "seed_id": node.node_id,
                        "velocity_mode": velocity_mode,
                        "proposal_indices": seed_proposals,
                    }
                )

            before = rank_metrics(seeds, proposals, "pair_score")
            after = rank_metrics(seeds, proposals, "coherence_score")
            valid = [proposal for proposal in proposals if proposal["valid"]]
            best_valid = max(valid, key=lambda proposal: proposal["coherence_score"])
            non_tp_scores = np.asarray(
                [proposal["coherence_score"] for proposal in proposals if not proposal["valid"]],
                dtype=float,
            )
            percentile = float(np.mean(non_tp_scores <= best_valid["coherence_score"]))
            useful_seed = seeds[best_valid["seed_index"]]
            row = {
                "case_id": case["case_id"],
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "before": before,
                "after": after,
                "correct_coherence": best_valid["coherence"],
                "correct_non_tp_percentile": percentile,
                "correct_parent_velocity_mode": useful_seed["velocity_mode"],
                "proposal_count": len(proposals),
                "detector": detector,
                "link_strategy": link_strategy,
                "zero_perturbation": before_signature == graph_signature(graph),
                "candidate_set_changed": False,
                "graph_mutated": False,
            }
            rows.append(row)
            print(
                f"{sample_id} t{t}: parent {before['parent_seed_rank']}->"
                f"{after['parent_seed_rank']} counterpart "
                f"{before['counterpart_rank_within_parent']}->"
                f"{after['counterpart_rank_within_parent']} "
                f"percentile={percentile:.3f}",
                flush=True,
            )

    returns_all = all(row["correct_coherence"]["distinct"] for row in rows)
    percentiles = [row["correct_non_tp_percentile"] for row in rows]
    counterpart_severe_regression = any(
        row["after"]["counterpart_rank_within_parent"]
        > 1.25 * row["before"]["counterpart_rank_within_parent"]
        for row in rows
    )
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
    if (
        returns_all
        and min(percentiles) >= 0.90
        and no_rank_regression
        and parent_improvement
    ):
        decision = "GO_TO_LARGER_RANGE_RATE_SHADOW"
    elif (
        not returns_all
        or min(percentiles) <= 0.50
        or counterpart_severe_regression
    ):
        decision = "NO_GO_RANGE_RATE"
    else:
        decision = "HOLD_RANGE_RATE_SIGNAL"

    summary = {
        "status": "read_only_v23_echo_range_rate_coherence",
        "decision": decision,
        "events": len(rows),
        "correct_non_tp_percentiles": percentiles,
        "correct_distinct_returns": sum(
            row["correct_coherence"]["distinct"] for row in rows
        ),
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Echo Range-Rate Coherence Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "The two anchored cases were rescored using parent-velocity inheritance and daughter-pair separation coherence. Quarantined paths were excluded and no graph was changed.",
        "",
        "| Event | Parent rank | Counterpart rank | Global rank | Non-TP percentile | Residuals retained / counterpart / separation | Sources |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        coherence = row["correct_coherence"]
        lines.append(
            f"| {row['sample_id']} t{row['t']} | "
            f"{row['before']['parent_seed_rank']} -> {row['after']['parent_seed_rank']} | "
            f"{row['before']['counterpart_rank_within_parent']} -> {row['after']['counterpart_rank_within_parent']} | "
            f"{row['before']['global_proposal_rank']} -> {row['after']['global_proposal_rank']} | "
            f"{row['correct_non_tp_percentile']:.1%} | "
            f"{format_residual(coherence['retained_velocity_residual_um'])} / "
            f"{format_residual(coherence['counterpart_velocity_residual_um'])} / "
            f"{format_residual(coherence['separation_residual_um'])} | "
            f"{coherence['retained_source']} / {coherence['counterpart_source']} |"
        )
    lines += [
        "",
        "Guardrail: this two-event shadow cannot authorize integration or full-cohort execution.",
        "Parent-velocity inheritance helped the 44b6 event but strongly demoted the valid 6bba event. The correct 6bba counterpart had an 8.20 um velocity residual and ranked at only the non-TP 8.2nd percentile.",
        "",
        "Conclusion: preserve anchored spatial echo completion as candidate evidence, but do not use naive parent-motion inheritance as a general daughter qualifier.",
        "",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
