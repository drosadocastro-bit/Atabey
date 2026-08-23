"""Separate anchored second-daughter echoes from broken-parent recovery."""

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
    DEDUP_RADIUS_UM,
    FORMATION_RADIUS_UM,
    OFFICIAL_RADIUS_UM,
    ROUTER_RADIUS_UM,
    echo_peaks,
    prediction,
    remove_primary_duplicates,
)


def graph_signature(graph):
    nodes = tuple(
        (node.node_id, int(node.t), *node.position_um) for node in graph.detections
    )
    edges = tuple(
        (edge.source_id, edge.target_id, edge.relation) for edge in graph.edges
    )
    return nodes, edges


def is_registered(point, target):
    return bool(np.linalg.norm(point - target) <= OFFICIAL_RADIUS_UM)


def anchored_valid(parent, retained, echo, gt_parent, gt_daughters):
    if not is_registered(parent, gt_parent):
        return False
    if np.linalg.norm(retained - echo) <= DEDUP_RADIUS_UM:
        return False
    if (
        np.linalg.norm(retained - parent) > FORMATION_RADIUS_UM
        or np.linalg.norm(echo - parent) > FORMATION_RADIUS_UM
    ):
        return False
    return bool(
        (is_registered(retained, gt_daughters[0]) and is_registered(echo, gt_daughters[1]))
        or (is_registered(retained, gt_daughters[1]) and is_registered(echo, gt_daughters[0]))
    )


def counterpart_score(parent, retained, echo, predicted_midpoint, evidence):
    left_radius = float(np.linalg.norm(retained - parent))
    right_radius = float(np.linalg.norm(echo - parent))
    midpoint = 0.5 * (retained + echo)
    midpoint_error = float(np.linalg.norm(midpoint - predicted_midpoint))
    midpoint_closeness = max(0.0, 1.0 - midpoint_error / ROUTER_RADIUS_UM)
    radial_balance = 1.0 - abs(left_radius - right_radius) / max(
        left_radius, right_radius, 1e-6
    )
    separation = float(np.linalg.norm(retained - echo))
    separation_support = min(1.0, separation / DEDUP_RADIUS_UM)
    return float(
        0.45 * midpoint_closeness
        + 0.25 * radial_balance
        + 0.15 * separation_support
        + 0.15 * evidence
    )


def stable_ranks(values, keys):
    order = sorted(range(len(values)), key=lambda i: (-values[i], keys[i]))
    return {index: rank for rank, index in enumerate(order, start=1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--budget-audit", type=Path, required=True)
    parser.add_argument("--pair-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    budget = json.loads(args.budget_audit.read_text(encoding="utf-8"))
    recovered_ids = {
        row["case_id"] for row in budget if row["budgets"]["1"]["recovered"]
    }
    prior_pair = {
        row["case_id"]: row
        for row in json.loads(args.pair_audit.read_text(encoding="utf-8"))
        if row["case_id"] in recovered_ids
    }
    by_sample = defaultdict(list)
    for case_id in recovered_ids:
        by_sample[fixture[case_id]["sample_id"]].append(fixture[case_id])

    anchored_rows = []
    quarantined_rows = []
    for sample_id, cases in sorted(by_sample.items()):
        max_t = max(int(case["t"]) for case in cases)
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr", max_timepoints=max_t + 2
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

        for case in sorted(cases, key=lambda item: int(item["t"])):
            t = int(case["t"])
            if t + 1 not in echo_cache:
                echo_cache[t + 1] = echo_peaks(read_timepoint(array, t + 1))
            primary_daughters = np.asarray(
                [node.position_um for node in frame_nodes[t + 1]], dtype=float
            ).reshape((-1, 3))
            echo_points, echo_evidence = remove_primary_duplicates(
                *echo_cache[t + 1], primary_daughters
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
                    target
                    for target in outgoing.get(node.node_id, [])
                    if target in nodes and int(nodes[target].t) == t + 1
                ]
                if len(child_ids) != 1:
                    continue
                parent = np.asarray(node.position_um, dtype=float)
                retained = np.asarray(nodes[child_ids[0]].position_um, dtype=float)
                predicted, _, mode = prediction(node, incoming, nodes)
                local = np.flatnonzero(
                    np.linalg.norm(echo_points - parent[None, :], axis=1)
                    <= ROUTER_RADIUS_UM
                )
                seed_index = len(seeds)
                seed_proposal_indices = []
                for echo_index in local:
                    echo = echo_points[echo_index]
                    if np.linalg.norm(echo - retained) <= DEDUP_RADIUS_UM:
                        continue
                    score = counterpart_score(
                        parent,
                        retained,
                        echo,
                        predicted,
                        float(echo_evidence[echo_index]),
                    )
                    proposal_index = len(proposals)
                    seed_proposal_indices.append(proposal_index)
                    proposals.append(
                        {
                            "seed_index": seed_index,
                            "echo_index": int(echo_index),
                            "score": score,
                            "valid": anchored_valid(
                                parent,
                                retained,
                                echo,
                                gt_parent,
                                gt_daughters,
                            ),
                        }
                    )
                seeds.append(
                    {
                        "seed_id": node.node_id,
                        "mode": mode,
                        "parent_registered": is_registered(parent, gt_parent),
                        "retained_child_registered": any(
                            is_registered(retained, daughter) for daughter in gt_daughters
                        ),
                        "proposal_indices": seed_proposal_indices,
                    }
                )

            useful = [
                index
                for index, seed in enumerate(seeds)
                if any(proposals[p]["valid"] for p in seed["proposal_indices"])
            ]
            if useful:
                seed_scores = [
                    max((proposals[p]["score"] for p in seed["proposal_indices"]), default=0.0)
                    for seed in seeds
                ]
                seed_keys = [seed["seed_id"] for seed in seeds]
                seed_ranks = stable_ranks(seed_scores, seed_keys)
                useful_seed = min(useful, key=lambda index: seed_ranks[index])
                local_indices = seeds[useful_seed]["proposal_indices"]
                local_scores = [proposals[index]["score"] for index in local_indices]
                local_keys = [proposals[index]["echo_index"] for index in local_indices]
                local_ranks = stable_ranks(local_scores, local_keys)
                valid_local = [
                    offset
                    for offset, proposal_index in enumerate(local_indices)
                    if proposals[proposal_index]["valid"]
                ]
                counterpart_rank = min(local_ranks[offset] for offset in valid_local)
                global_scores = [proposal["score"] for proposal in proposals]
                global_keys = [
                    (seeds[proposal["seed_index"]]["seed_id"], proposal["echo_index"])
                    for proposal in proposals
                ]
                global_ranks = stable_ranks(global_scores, global_keys)
                global_rank = min(
                    global_ranks[index]
                    for index, proposal in enumerate(proposals)
                    if proposal["valid"]
                )
                anchored_rows.append(
                    {
                        "case_id": case["case_id"],
                        "sample_id": sample_id,
                        "family": sample_id.split("_", 1)[0],
                        "t": t,
                        "path": "parent_present_anchored_completion",
                        "parent_seed_rank": seed_ranks[useful_seed],
                        "counterpart_rank_within_parent": counterpart_rank,
                        "global_proposal_rank": global_rank,
                        "parent_seed_count": len(seeds),
                        "proposal_count": len(proposals),
                        "useful_parent_proposal_count": len(local_indices),
                        "detector": detector,
                        "link_strategy": link_strategy,
                        "zero_perturbation": before == graph_signature(graph),
                        "candidate_set_changed": False,
                        "graph_mutated": False,
                    }
                )
                print(
                    f"{sample_id} t{t}: anchored seed={seed_ranks[useful_seed]} "
                    f"counterpart={counterpart_rank} global={global_rank}",
                    flush=True,
                )
            else:
                prior = prior_pair[case["case_id"]]["signals"]["best_pair_score"]
                detected_registered_parents = [
                    node for node in frame_nodes[t]
                    if is_registered(np.asarray(node.position_um, dtype=float), gt_parent)
                ]
                registered_parents = [seed for seed in seeds if seed["parent_registered"]]
                registered_anchors = [
                    seed
                    for seed in registered_parents
                    if seed["retained_child_registered"]
                ]
                if not detected_registered_parents:
                    path = "parent_missing_quarantine"
                    reason = "no_detected_parent_within_official_radius"
                elif not registered_anchors:
                    path = "parent_present_link_identity_quarantine"
                    reason = "detected_parent_has_no_registered_existing_child_anchor"
                else:
                    path = "parent_present_echo_unavailable_quarantine"
                    reason = "registered_parent_child_anchor_has_no_valid_echo_counterpart"
                quarantined_rows.append(
                    {
                        "case_id": case["case_id"],
                        "sample_id": sample_id,
                        "family": sample_id.split("_", 1)[0],
                        "t": t,
                        "path": path,
                        "reason": reason,
                        "registered_parent_detection_count": len(detected_registered_parents),
                        "registered_parent_child_anchor_count": len(registered_anchors),
                        "prior_pooled_seed_source": prior["useful_seed_source"],
                        "prior_pooled_seed_rank": prior["best_useful_seed_rank"],
                        "prior_pooled_pair_rank": prior["valid_pair_rank_within_seed"],
                        "detector": detector,
                        "link_strategy": link_strategy,
                        "zero_perturbation": before == graph_signature(graph),
                        "candidate_set_changed": False,
                        "graph_mutated": False,
                    }
                )
                print(f"{sample_id} t{t}: QUARANTINED {path}", flush=True)

    qualifying = [
        row
        for row in anchored_rows
        if row["parent_seed_rank"] <= 25
        and row["counterpart_rank_within_parent"] <= 10
    ]
    families = {row["family"] for row in qualifying}
    if len(anchored_rows) == 3 and len(qualifying) == 3 and len(families) == 2:
        anchored_decision = "GO_TO_ANCHORED_ASSIGNMENT_SHADOW"
    elif len(qualifying) >= 2:
        anchored_decision = "HOLD_ANCHORED_PATH"
    else:
        anchored_decision = "NO_GO_ANCHORED_PATH"

    summary = {
        "status": "read_only_v23_split_echo_paths",
        "population": {
            "anchored_events": len(anchored_rows),
            "quarantined_events": len(quarantined_rows),
        },
        "anchored": {
            "decision": anchored_decision,
            "joint_seed25_counterpart10": len(qualifying),
            "family_coverage": sorted(families),
        },
        "quarantine": {
            "decision": "QUARANTINED",
            "events": len(quarantined_rows),
            "path_counts": {
                path: sum(row["path"] == path for row in quarantined_rows)
                for path in sorted({row["path"] for row in quarantined_rows})
            },
        },
        "zero_perturbation_all": all(
            row["zero_perturbation"] for row in anchored_rows + quarantined_rows
        ),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    payload = {"anchored": anchored_rows, "quarantine": quarantined_rows}
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 Split Echo Paths Results",
        "",
        f"Anchored decision: **{anchored_decision}**.",
        "",
        "Upstream-quarantine decision: **QUARANTINED**.",
        "",
        "The anchored path retained the graph's existing child and ranked only one distinct echo counterpart. The broken-parent path was excluded from all anchored metrics. GT was used only to identify registered-valid ranks after proposal construction.",
        "",
        f"The preregistered assumption of three anchored events was falsified: only {len(anchored_rows)} had a registered-valid parent, existing-child, and echo-counterpart hypothesis.",
        "",
        "## Parent-Present Anchored Completion",
        "",
        "| Event | Family | Parent rank | Counterpart rank | Global proposal rank | Proposals |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in anchored_rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['family']} | "
            f"{row['parent_seed_rank']} | {row['counterpart_rank_within_parent']} | "
            f"{row['global_proposal_rank']} | {row['proposal_count']} |"
        )
    lines += [
        "",
        "## Upstream Quarantine",
        "",
        "| Event | Quarantine reason | Prior pooled source/rank | Status |",
        "|---|---|---:|---|",
    ]
    for row in quarantined_rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | "
            f"{row['reason']} | {row['prior_pooled_seed_source']} "
            f"{row['prior_pooled_seed_rank']} / {row['prior_pooled_pair_rank']} | "
            "QUARANTINED |"
        )
    lines += [
        "",
        "Guardrail: both paths remained read-only. No candidate, edge, or graph was changed.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
