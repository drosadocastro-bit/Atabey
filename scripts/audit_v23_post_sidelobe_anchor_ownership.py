"""Trace anchor and ownership losses after valid post-sidelobe geometry exists."""

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
    enumerate_anchored_division_actions,
    evaluate_action_as_official_fork,
)
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def signature(graph):
    detections = tuple((node.node_id, node.t, node.z_um, node.y_um, node.x_um) for node in graph.detections)
    edges = tuple((edge.source_id, edge.target_id, edge.relation) for edge in graph.edges)
    return detections, edges


def action_key(parent_id, child_1_id, child_2_id):
    return parent_id, tuple(sorted((child_1_id, child_2_id)))


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
    detector_rows = [row for row in json.loads(args.pre_post.read_text(encoding="utf-8")) if row["post_official_geometry_available"]]
    rows = []
    for detector_row in detector_rows:
        case = fixture[detector_row["case_id"]]
        sample_id = case["sample_id"]
        t = int(case["t"])
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(args.train_dir / f"{sample_id}.zarr", max_timepoints=t + 2)
        before = signature(graph)
        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        gt_parent = gt_nodes[int(case["gt_parent_id"])]
        gt_children = [gt_nodes[int(child_id)] for child_id in case["gt_child_ids"]]
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
        parent_candidates = [peak for peak in peaks if peak.t == t and distance(peak.position_um, gt_parent.position_um) <= 7.0]
        daughter_1 = [peak for peak in peaks if peak.t == t + 1 and distance(peak.position_um, gt_children[0].position_um) <= 7.0]
        daughter_2 = [peak for peak in peaks if peak.t == t + 1 and distance(peak.position_um, gt_children[1].position_um) <= 7.0]
        valid_keys = set()
        for parent in parent_candidates:
            for left in daughter_1:
                for right in daughter_2:
                    if left.peak_id == right.peak_id:
                        continue
                    if distance(left.position_um, parent.position_um) <= 14.0 and distance(right.position_um, parent.position_um) <= 14.0:
                        valid_keys.add(action_key(parent.peak_id, left.peak_id, right.peak_id))
        enumeration = enumerate_anchored_division_actions(graph, peaks, parent_t=t, anchor_radius_um=14.0, formation_radius_um=14.0)
        action_by_key = {action_key(action.parent.peak_id, action.child_1.peak_id, action.child_2.peak_id): action for action in enumeration.actions}
        retained_keys = valid_keys.intersection(action_by_key)
        official_keys = {
            key for key in retained_keys
            if evaluate_action_as_official_fork(action_by_key[key], gt, gt_parent_id=int(case["gt_parent_id"]))
        }
        parent_ids_in_actions = {action.parent.peak_id for action in enumeration.actions}
        incoming = {}
        outgoing = {}
        for edge in graph.edges:
            incoming.setdefault(edge.target_id, []).append(edge.source_id)
            outgoing.setdefault(edge.source_id, []).append(edge.target_id)
        conflicts = []
        for key in valid_keys:
            parent_id, child_ids = key
            conflicts.append({
                "parent_id": parent_id,
                "child_ids": list(child_ids),
                "parent_anchor_retained": parent_id in parent_ids_in_actions,
                "child_ownership_conflict": any(source_id != parent_id for child_id in child_ids for source_id in incoming.get(child_id, [])),
                "parent_existing_outgoing": outgoing.get(parent_id, []),
                "child_existing_incoming": {child_id: incoming.get(child_id, []) for child_id in child_ids},
            })
        if not valid_keys:
            outcome = "detector_geometry_not_reproduced_in_graph"
        elif not retained_keys:
            outcome = "parent_anchor_or_formation_loss"
        elif not official_keys:
            outcome = "formed_but_official_metric_rejects"
        else:
            outcome = "official_action_available"
        rows.append({
            "case_id": case["case_id"],
            "sample_id": sample_id,
            "t": t,
            "detector": detector,
            "link_strategy": link_strategy,
            "valid_detector_geometry_triples": len(valid_keys),
            "retained_anchored_actions": len(retained_keys),
            "official_tp_actions": len(official_keys),
            "candidate_details": conflicts,
            "outcome": outcome,
            "zero_perturbation": before == signature(graph),
            "candidate_set_changed": False,
            "graph_mutated": False,
        })
        print(f"{sample_id} t{t}: geometry={len(valid_keys)} anchored={len(retained_keys)} official={len(official_keys)} outcome={outcome}", flush=True)

    summary = {
        "status": "read_only_v23_post_sidelobe_anchor_ownership_audit",
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {"cases": len(rows)},
        "outcome_counts": {outcome: sum(row["outcome"] == outcome for row in rows) for outcome in sorted({row["outcome"] for row in rows})},
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Post-Sidelobe Anchor and Ownership Audit",
        "",
        "Decision: **READ-ONLY DOWNSTREAM DIAGNOSTIC**.",
        "",
        "Only events with valid post-sidelobe 7 um detector geometry were evaluated. No candidate, edge, or graph was changed.",
        "",
        "| Sample | Detector triples | Anchored actions | Official TP actions | Outcome |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(f"| {row['sample_id']} t{row['t']} | {row['valid_detector_geometry_triples']} | {row['retained_anchored_actions']} | {row['official_tp_actions']} | {row['outcome']} |")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
