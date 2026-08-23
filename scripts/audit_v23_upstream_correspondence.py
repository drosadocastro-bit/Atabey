"""Trace upstream CFAR candidate correspondence for four known losses."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


CASES = [
    ("44b6_706092f0", 49, 446000000015, [447000000015, 447000000016]),
    ("44b6_74d0c52e", 58, 296000000021, [297000000021, 297000000022]),
    ("44b6_aaf8b0ea", 61, 390000000000, [391000000000, 391000000001]),
    ("6bba_57b7cc1e", 23, 24000720, [25000750, 25000751]),
]


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def node_record(node, target) -> dict:
    return {
        "id": node.node_id,
        "t": int(node.t),
        "distance_to_gt_um": distance(node.position_um, target.position_um),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    results = []
    for sample_id, t, parent_id, child_ids in CASES:
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr", max_timepoints=t + 2
        )
        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        gt_parent = gt_nodes[parent_id]
        gt_children = [gt_nodes[child_id] for child_id in child_ids]
        nodes = {node.node_id: node for node in graph.detections}
        incoming = {}
        outgoing = {}
        for edge in graph.edges:
            incoming.setdefault(edge.target_id, []).append(edge.source_id)
            outgoing.setdefault(edge.source_id, []).append(edge.target_id)
        parent_candidates = sorted(
            [node for node in graph.detections if int(node.t) == t and distance(node.position_um, gt_parent.position_um) <= 14.0],
            key=lambda node: distance(node.position_um, gt_parent.position_um),
        )
        child_candidates = [
            sorted(
                [node for node in graph.detections if int(node.t) == t + 1 and distance(node.position_um, gt_child.position_um) <= 14.0],
                key=lambda node: distance(node.position_um, gt_child.position_um),
            )
            for gt_child in gt_children
        ]
        candidate_ids = {node.node_id for node in parent_candidates}
        candidate_ids.update(node.node_id for group in child_candidates for node in group)
        graph_claims = {
            node_id: {
                "incoming": incoming.get(node_id, []),
                "outgoing": outgoing.get(node_id, []),
            }
            for node_id in sorted(candidate_ids)
        }
        best_pairs = []
        for parent in parent_candidates:
            nearby_children = [
                node for node in graph.detections
                if int(node.t) == t + 1 and distance(node.position_um, parent.position_um) <= 14.0
            ]
            for child_1, child_2 in combinations(nearby_children, 2):
                direct = [distance(child_1.position_um, gt_children[0].position_um), distance(child_2.position_um, gt_children[1].position_um)]
                swapped = [distance(child_1.position_um, gt_children[1].position_um), distance(child_2.position_um, gt_children[0].position_um)]
                child_distances = direct if max(direct) <= max(swapped) else swapped
                best_pairs.append({
                    "parent_id": parent.node_id,
                    "child_1_id": child_1.node_id,
                    "child_2_id": child_2.node_id,
                    "parent_distance_um": distance(parent.position_um, gt_parent.position_um),
                    "daughter_distances_um": child_distances,
                    "max_daughter_distance_um": max(child_distances),
                    "sum_role_distance_um": distance(parent.position_um, gt_parent.position_um) + sum(child_distances),
                })
        best_pairs.sort(key=lambda item: (item["max_daughter_distance_um"], item["sum_role_distance_um"]))
        results.append({
            "sample_id": sample_id,
            "t": t,
            "detector": detector,
            "link_strategy": link_strategy,
            "gt_parent_id": parent_id,
            "gt_child_ids": child_ids,
            "parent_candidates_within_14um": [node_record(node, gt_parent) for node in parent_candidates[:10]],
            "daughter_1_candidates_within_14um": [node_record(node, gt_children[0]) for node in child_candidates[0][:10]],
            "daughter_2_candidates_within_14um": [node_record(node, gt_children[1]) for node in child_candidates[1][:10]],
            "candidate_graph_claims": graph_claims,
            "best_distinct_pairs": best_pairs[:10],
        })
        print(f"{sample_id}: parent14={len(parent_candidates)} d1_14={len(child_candidates[0])} d2_14={len(child_candidates[1])} pair_options={len(best_pairs)}", flush=True)

    summary = {
        "status": "read_only_v23_upstream_correspondence_audit",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "cases": results,
    }
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Upstream Correspondence Audit",
        "",
        "Read-only audit of the four known CFAR formation failures. Candidate distances are physical micrometers. Graph claims show existing upstream ownership; no graph or candidate was changed.",
        "",
    ]
    for item in results:
        lines += [
            f"## {item['sample_id']} t{item['t']}",
            f"Route: `{item['detector']}/{item['link_strategy']}`.",
            f"GT parent `{item['gt_parent_id']}`; daughters `{item['gt_child_ids']}`.",
            f"14 um candidates: parent `{len(item['parent_candidates_within_14um'])}` reported, daughter 1 `{len(item['daughter_1_candidates_within_14um'])}` reported, daughter 2 `{len(item['daughter_2_candidates_within_14um'])}` reported.",
        ]
        if item["best_distinct_pairs"]:
            best = item["best_distinct_pairs"][0]
            lines.append(f"Best distinct pair: `{best['parent_id']}` -> `{best['child_1_id']}`, `{best['child_2_id']}`; max daughter error `{best['max_daughter_distance_um']:.3f} um`.")
        else:
            lines.append("No distinct parent-plus-two-daughter pair was available within the 14 um formation neighborhood.")
        lines.append("")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
