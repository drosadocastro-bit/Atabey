"""Bounded, read-only CFAR formation shadow for four known losses."""

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
from atabey.tracking.unet_action_availability import (
    UnetShadowPeak,
    action_matches_registered_division,
    enumerate_anchored_division_actions,
)
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


CASES = [
    ("44b6_706092f0", 49, 446000000015, [447000000015, 447000000016]),
    ("44b6_74d0c52e", 58, 296000000021, [297000000021, 297000000022]),
    ("44b6_aaf8b0ea", 61, 390000000000, [391000000000, 391000000001]),
    ("6bba_57b7cc1e", 23, 24000720, [25000750, 25000751]),
]


def dist(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for sample_id, t, parent_id, child_ids in CASES:
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr", max_timepoints=t + 2
        )
        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        nodes = {int(node.node_id): node for node in gt.nodes}
        gt_parent = nodes[parent_id]
        gt_children = (nodes[child_ids[0]], nodes[child_ids[1]])
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
        role_candidates = {}
        for radius in (7.0, 14.0):
            role_candidates[radius] = {
                "parent": [p for p in peaks if p.t == t and dist(p.position_um, gt_parent.position_um) <= radius],
                "daughter_1": [p for p in peaks if p.t == t + 1 and dist(p.position_um, gt_children[0].position_um) <= radius],
                "daughter_2": [p for p in peaks if p.t == t + 1 and dist(p.position_um, gt_children[1].position_um) <= radius],
            }
        enumeration = enumerate_anchored_division_actions(
            graph, peaks, parent_t=t, anchor_radius_um=14.0, formation_radius_um=14.0
        )
        matching_actions = [
            action for action in enumeration.actions
            if action_matches_registered_division(
                action,
                parent_position_um=gt_parent.position_um,
                daughter_positions_um=(gt_children[0].position_um, gt_children[1].position_um),
                match_radius_um=7.0,
            )
        ]
        rows.append({
            "sample_id": sample_id,
            "t": t,
            "detector": detector,
            "link_strategy": link_strategy,
            "baseline_7um_counts": {role: len(values) for role, values in role_candidates[7.0].items()},
            "shadow_14um_counts": {role: len(values) for role, values in role_candidates[14.0].items()},
            "baseline_7um_distinct_roles": all(role_candidates[7.0][role] for role in ("parent", "daughter_1", "daughter_2")),
            "shadow_14um_distinct_roles": all(role_candidates[14.0][role] for role in ("parent", "daughter_1", "daughter_2")),
            "formed_action_count": int(enumeration.division_action_count),
            "official_7um_geometric_shadow_actions": int(len(matching_actions)),
            "candidate_set_changed": False,
            "graph_mutated": False,
            "matching_action_ids": [
                [action.parent.peak_id, action.child_1.peak_id, action.child_2.peak_id]
                for action in matching_actions
            ],
        })
        print(f"{sample_id}: 7um={rows[-1]['baseline_7um_counts']} 14um={rows[-1]['shadow_14um_counts']} formed={enumeration.division_action_count} matched={len(matching_actions)}", flush=True)

    summary = {
        "status": "read_only_cfar_formation_shadow",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "cases": rows,
        "decision": "SHADOW_DIAGNOSTIC_ONLY",
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Formation Shadow Results",
        "",
        "Decision: **SHADOW DIAGNOSTIC ONLY**.",
        "",
        "The 14 um role window was measured diagnostically; no candidate, edge, or graph was changed. A matched action is retained only as an input to later official evaluation.",
        "",
        "| Sample | 7 um role counts | 14 um role counts | Formed actions | Geometric matches |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['sample_id']} t{row['t']} | {row['baseline_7um_counts']} | {row['shadow_14um_counts']} | {row['formed_action_count']} | {row['official_7um_geometric_shadow_actions']} |")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
