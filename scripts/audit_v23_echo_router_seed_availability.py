"""Audit inference-available seeds for a track-conditioned echo router."""

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
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def graph_signature(graph):
    nodes = tuple((n.node_id, int(n.t), *n.position_um) for n in graph.detections)
    edges = tuple((e.source_id, e.target_id, e.relation) for e in graph.edges)
    return nodes, edges


def predicted_position(node, incoming, nodes):
    predecessors = [nodes[source] for source in incoming.get(node.node_id, []) if source in nodes]
    predecessors = [item for item in predecessors if int(item.t) == int(node.t) - 1]
    if len(predecessors) != 1:
        return np.asarray(node.position_um, dtype=float), "stationary_fallback"
    current = np.asarray(node.position_um, dtype=float)
    previous = np.asarray(predecessors[0].position_um, dtype=float)
    return current + (current - previous), "velocity"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--pre-post", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {case["case_id"]: case for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]}
    prior = json.loads(args.pre_post.read_text(encoding="utf-8"))
    selected = [fixture[row["case_id"]] for row in prior]
    by_sample = defaultdict(list)
    for case in selected:
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
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for edge in graph.edges:
            incoming[edge.target_id].append(edge.source_id)
            outgoing[edge.source_id].append(edge.target_id)
        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}

        for case in cases:
            t = int(case["t"])
            gt_parent = gt_nodes[int(case["gt_parent_id"])]
            gt_children = [gt_nodes[int(node_id)] for node_id in case["gt_child_ids"]]
            gt_midpoint = np.mean([np.asarray(node.position_um, dtype=float) for node in gt_children], axis=0)

            broken = []
            for node in nodes.values():
                if int(node.t) != t - 1:
                    continue
                next_ids = [target for target in outgoing.get(node.node_id, []) if target in nodes and int(nodes[target].t) == t]
                if next_ids:
                    continue
                predicted, mode = predicted_position(node, incoming, nodes)
                broken.append({"node_id": node.node_id, "prediction": predicted, "mode": mode})

            under_resolved = []
            for node in nodes.values():
                if int(node.t) != t:
                    continue
                next_ids = [target for target in outgoing.get(node.node_id, []) if target in nodes and int(nodes[target].t) == t + 1]
                if len(next_ids) > 1:
                    continue
                predicted, mode = predicted_position(node, incoming, nodes)
                under_resolved.append({
                    "node_id": node.node_id,
                    "position": np.asarray(node.position_um, dtype=float),
                    "prediction": predicted,
                    "mode": mode,
                    "outgoing_count": len(next_ids),
                })

            broken_matches = [item for item in broken if distance(item["prediction"], gt_parent.position_um) <= 14.0]
            branch_matches = [item for item in under_resolved if distance(item["position"], gt_parent.position_um) <= 7.0]
            midpoint_matches = [item for item in branch_matches if distance(item["prediction"], gt_midpoint) <= 14.0]
            rows.append({
                "case_id": case["case_id"],
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "detector": detector,
                "link_strategy": link_strategy,
                "broken_endpoint_seed_count": len(broken),
                "broken_seed_matches_gt_parent_14um": len(broken_matches),
                "under_resolved_parent_seed_count": len(under_resolved),
                "under_resolved_seed_matches_gt_parent_7um": len(branch_matches),
                "matching_branch_seed_predicts_gt_midpoint_14um": len(midpoint_matches),
                "router_seed_available": bool(broken_matches or branch_matches),
                "matching_seed_modes": sorted({item["mode"] for item in broken_matches + branch_matches}),
                "zero_perturbation": before == graph_signature(graph),
                "candidate_set_changed": False,
                "graph_mutated": False,
            })
            print(
                f"{sample_id} t{t}: broken={len(broken)}/{len(broken_matches)} "
                f"under_resolved={len(under_resolved)}/{len(branch_matches)} "
                f"seed={bool(broken_matches or branch_matches)}",
                flush=True,
            )

    summary = {
        "status": "read_only_v23_echo_router_seed_availability",
        "population": {"cases": len(rows)},
        "router_seed_available": sum(row["router_seed_available"] for row in rows),
        "router_seed_missing": sum(not row["router_seed_available"] for row in rows),
        "broken_endpoint_path_available": sum(row["broken_seed_matches_gt_parent_14um"] > 0 for row in rows),
        "under_resolved_parent_path_available": sum(row["under_resolved_seed_matches_gt_parent_7um"] > 0 for row in rows),
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True, default=lambda value: value.tolist()) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Echo Router Seed Availability",
        "",
        "Decision: **READ-ONLY PREREQUISITE AUDIT**.",
        "",
        "Router seeds were generated only from the V19 graph: broken endpoints at t-1 and parents at t with at most one outgoing continuation. GT coordinates were used only after seed generation to score coverage.",
        "",
        "| Event | Broken seeds / matching | Under-resolved seeds / matching | Router seed |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['broken_endpoint_seed_count']} / {row['broken_seed_matches_gt_parent_14um']} | "
            f"{row['under_resolved_parent_seed_count']} / {row['under_resolved_seed_matches_gt_parent_7um']} | {row['router_seed_available']} |"
        )
    lines += ["", f"Seed coverage: **{summary['router_seed_available']}/{len(rows)}**. Zero perturbation: **{summary['zero_perturbation_all']}**."]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
