"""Inspect actual CFAR candidates for the bounded formation-loss cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.unet_action_availability import UnetShadowPeak, enumerate_anchored_division_actions
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


CASES = [
    ("44b6_706092f0", 49, 446000000015, [447000000015, 447000000016]),
    ("44b6_74d0c52e", 58, 296000000021, [297000000021, 297000000022]),
    ("44b6_aaf8b0ea", 61, 390000000000, [391000000000, 391000000001]),
    ("6bba_57b7cc1e", 23, 24000720, [25000750, 25000751]),
]


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
        gt_children = [gt_nodes[node_id] for node_id in child_ids]
        peaks = [
            UnetShadowPeak(
                peak_id=node.node_id,
                sample_id=node.sample_id,
                t=int(node.t),
                z_um=float(node.z_um),
                y_um=float(node.y_um),
                x_um=float(node.x_um),
                confidence=node.detection_confidence,
            )
            for node in graph.detections
        ]
        parent_candidates = [p for p in peaks if p.t == t and distance(p.position_um, gt_parent.position_um) <= 7.0]
        daughter_candidates = [
            [p for p in peaks if p.t == t + 1 and distance(p.position_um, child.position_um) <= 7.0]
            for child in gt_children
        ]
        enumeration = enumerate_anchored_division_actions(
            graph, peaks, parent_t=t, anchor_radius_um=14.0, formation_radius_um=14.0
        )
        actions = []
        for action in enumeration.actions:
            parent_dist = distance(action.parent.position_um, gt_parent.position_um)
            child_dists = [distance(action.child_1.position_um, child.position_um) for child in gt_children]
            reverse_child_dists = [distance(action.child_2.position_um, child.position_um) for child in gt_children]
            if parent_dist <= 7.0 and min(
                max(child_dists), max(reverse_child_dists)
            ) <= 14.0:
                actions.append({
                    "parent_id": action.parent.peak_id,
                    "child_1_id": action.child_1.peak_id,
                    "child_2_id": action.child_2.peak_id,
                    "anchor_id": action.anchor_id,
                    "anchor_prediction_distance_um": action.anchor_prediction_distance_um,
                    "parent_distance_um": parent_dist,
                    "child_distances_to_gt": child_dists,
                    "swapped_child_distances_to_gt": reverse_child_dists,
                    "matches_gt_pair_within_7um": min(max(child_dists), max(reverse_child_dists)) <= 7.0,
                })
        result = {
            "sample_id": sample_id,
            "t": t,
            "detector": detector,
            "link_strategy": link_strategy,
            "gt_parent_id": parent_id,
            "gt_child_ids": child_ids,
            "parent_candidates": [
                {"id": p.peak_id, "distance_um": distance(p.position_um, gt_parent.position_um)}
                for p in sorted(parent_candidates, key=lambda p: distance(p.position_um, gt_parent.position_um))
            ],
            "daughter_1_candidates": [
                {"id": p.peak_id, "distance_um": distance(p.position_um, gt_children[0].position_um)}
                for p in sorted(daughter_candidates[0], key=lambda p: distance(p.position_um, gt_children[0].position_um))
            ],
            "daughter_2_candidates": [
                {"id": p.peak_id, "distance_um": distance(p.position_um, gt_children[1].position_um)}
                for p in sorted(daughter_candidates[1], key=lambda p: distance(p.position_um, gt_children[1].position_um))
            ],
            "near_gt_parent_actions": actions,
            "enumeration": {
                "parent_peak_count": enumeration.parent_peak_count,
                "anchored_parent_count": enumeration.anchored_parent_count,
                "division_action_count": enumeration.division_action_count,
            },
        }
        results.append(result)
        print(f"{sample_id}: parent={len(parent_candidates)} daughter1={len(daughter_candidates[0])} daughter2={len(daughter_candidates[1])} actions_near_parent={len(actions)}", flush=True)

    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Formation-Failure Candidate Inspection",
        "",
        "Read-only inspection of the four CFAR-route formation failures. Distances are measured in physical micrometers. No candidate, edge, or graph was changed.",
        "",
    ]
    for item in results:
        lines += [
            f"## {item['sample_id']} t{item['t']}",
            f"Route: `{item['detector']}/{item['link_strategy']}`.",
            f"GT parent `{item['gt_parent_id']}`; daughters `{item['gt_child_ids']}`.",
            f"Candidates within 7 um: parent `{len(item['parent_candidates'])}`, daughter 1 `{len(item['daughter_1_candidates'])}`, daughter 2 `{len(item['daughter_2_candidates'])}`.",
            f"Anchored actions near GT parent: `{len(item['near_gt_parent_actions'])}` of `{item['enumeration']['division_action_count']}` total.",
            "",
        ]
        for role in ("parent_candidates", "daughter_1_candidates", "daughter_2_candidates"):
            lines.append(f"- {role}: " + ", ".join(f"{x['id']} ({x['distance_um']:.3f} um)" for x in item[role]) )
        matches = [x for x in item["near_gt_parent_actions"] if x["matches_gt_pair_within_7um"]]
        lines.append(f"- Correct registered pair formed: **{'yes' if matches else 'no'}**.")
        lines.append("")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
