"""Route-stratified CFAR correspondence audit across all 11 development events."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def best_pair(graph, t, parent_candidates, gt_children):
    pairs = []
    for parent in parent_candidates:
        nearby = [node for node in graph.detections if int(node.t) == t + 1 and distance(node.position_um, parent.position_um) <= 14.0]
        for child_1, child_2 in combinations(nearby, 2):
            direct = [distance(child_1.position_um, gt_children[0].position_um), distance(child_2.position_um, gt_children[1].position_um)]
            swapped = [distance(child_1.position_um, gt_children[1].position_um), distance(child_2.position_um, gt_children[0].position_um)]
            daughter_distances = direct if max(direct) <= max(swapped) else swapped
            pairs.append({
                "parent_id": parent.node_id,
                "child_1_id": child_1.node_id,
                "child_2_id": child_2.node_id,
                "parent_distance_um": None,
                "max_daughter_distance_um": max(daughter_distances),
                "sum_role_distance_um": sum(daughter_distances),
            })
    pairs.sort(key=lambda item: (item["max_daughter_distance_um"], item["sum_role_distance_um"]))
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    cases = pd.DataFrame(fixture["cases"])
    availability = pd.read_csv(args.availability)
    route_cases = availability[availability.source_detector.eq("cfar_sidelobe")][["case_id", "sample_id", "t", "source_link_strategy"]]
    cases = cases.merge(route_cases, on=["case_id", "sample_id", "t"], how="inner", validate="one_to_one")
    rows = []
    for case in cases.sort_values(["sample_id", "t"]).itertuples(index=False):
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(args.train_dir / f"{case.sample_id}.zarr", max_timepoints=int(case.t) + 2)
        gt = read_geff_graph(args.train_dir / f"{case.sample_id}.geff")
        nodes = {int(node.node_id): node for node in gt.nodes}
        gt_parent = nodes[int(case.gt_parent_id)]
        gt_children = [nodes[int(child_id)] for child_id in case.gt_child_ids]
        parents_7 = [node for node in graph.detections if int(node.t) == int(case.t) and distance(node.position_um, gt_parent.position_um) <= 7.0]
        parents_14 = [node for node in graph.detections if int(node.t) == int(case.t) and distance(node.position_um, gt_parent.position_um) <= 14.0]
        daughters_7 = [[node for node in graph.detections if int(node.t) == int(case.t) + 1 and distance(node.position_um, child.position_um) <= 7.0] for child in gt_children]
        daughters_14 = [[node for node in graph.detections if int(node.t) == int(case.t) + 1 and distance(node.position_um, child.position_um) <= 14.0] for child in gt_children]
        pairs = best_pair(graph, int(case.t), parents_14, gt_children)
        for pair in pairs:
            parent = next(node for node in parents_14 if node.node_id == pair["parent_id"])
            pair["parent_distance_um"] = distance(parent.position_um, gt_parent.position_um)
        best = pairs[0] if pairs else None
        official_pairs = [
            pair
            for pair in pairs
            if pair["parent_distance_um"] <= 7.0
            and pair["max_daughter_distance_um"] <= 7.0
        ]
        incoming = {}
        for edge in graph.edges:
            incoming.setdefault(edge.target_id, []).append(edge.source_id)
        collision = bool(daughters_7[0] and daughters_7[1] and daughters_7[0][0].node_id == daughters_7[1][0].node_id)
        if not parents_14:
            outcome = "no_parent_within_14um"
        elif not daughters_14[0] or not daughters_14[1]:
            outcome = "missing_daughter_within_14um"
        elif not pairs:
            outcome = "no_distinct_pair_within_14um"
        elif official_pairs:
            outcome = "official_geometric_candidate"
        else:
            outcome = "pair_exists_outside_official_7um"
        rows.append({
            "case_id": case.case_id,
            "sample_id": case.sample_id,
            "family": str(case.sample_id).split("_", 1)[0],
            "t": int(case.t),
            "detector": detector,
            "link_strategy": link_strategy,
            "parent_count_7um": len(parents_7),
            "parent_count_14um": len(parents_14),
            "daughter_1_count_7um": len(daughters_7[0]),
            "daughter_2_count_7um": len(daughters_7[1]),
            "daughter_1_count_14um": len(daughters_14[0]),
            "daughter_2_count_14um": len(daughters_14[1]),
            "nearest_daughter_collision_7um": collision,
            "pair_options_14um": len(pairs),
            "best_parent_distance_um": best["parent_distance_um"] if best else None,
            "best_max_daughter_distance_um": best["max_daughter_distance_um"] if best else None,
            "best_parent_id": best["parent_id"] if best else None,
            "best_child_1_id": best["child_1_id"] if best else None,
            "best_child_2_id": best["child_2_id"] if best else None,
            "best_child_1_incoming": incoming.get(best["child_1_id"], []) if best else [],
            "best_child_2_incoming": incoming.get(best["child_2_id"], []) if best else [],
            "best_pair_ownership_conflict": bool(best and any(parent_id != best["parent_id"] for parent_id in incoming.get(best["child_1_id"], []) + incoming.get(best["child_2_id"], []))),
            "outcome": outcome,
            "candidate_set_changed": False,
            "graph_mutated": False,
        })
        print(f"{case.sample_id}: outcome={outcome} parent14={len(parents_14)} d1_14={len(daughters_14[0])} d2_14={len(daughters_14[1])} pairs={len(pairs)}", flush=True)

    frame = pd.DataFrame(rows)
    summary = {
        "status": "read_only_v23_cfar_correspondence_audit_11",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {"cases": len(frame), "families": frame.family.value_counts().to_dict()},
        "outcome_counts": frame.outcome.value_counts().to_dict(),
        "ownership_conflict_best_pair_count": int(frame.best_pair_ownership_conflict.sum()),
        "nearest_daughter_collision_count": int(frame.nearest_daughter_collision_7um.sum()),
    }
    frame.to_csv(args.output, index=False)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Correspondence Audit: 11 Events",
        "",
        "Decision: **READ-ONLY DIAGNOSTIC; NO CFAR OR LINKER CHANGE**.",
        "",
        f"Population: `{len(frame)}` CFAR-sidelobe/bipartite development events. No candidates, edges, or graphs were changed.",
        "",
        "| Outcome | Cases | Percent |",
        "|---|---:|---:|",
    ]
    for outcome, count in frame.outcome.value_counts().items():
        lines.append(f"| {outcome} | {count} | {100.0 * count / len(frame):.1f}% |")
    lines += [
        "",
        "| Sample | Parent 7/14 | Daughter 1 7/14 | Daughter 2 7/14 | Best daughter residual | Ownership conflict | Outcome |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        residual = "NA" if row["best_max_daughter_distance_um"] is None else f"{row['best_max_daughter_distance_um']:.3f} um"
        lines.append(f"| {row['sample_id']} t{row['t']} | {row['parent_count_7um']}/{row['parent_count_14um']} | {row['daughter_1_count_7um']}/{row['daughter_1_count_14um']} | {row['daughter_2_count_7um']}/{row['daughter_2_count_14um']} | {residual} | {row['best_pair_ownership_conflict']} | {row['outcome']} |")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()


