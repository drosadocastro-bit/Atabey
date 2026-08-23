"""Shadow-test local intensity-weighted CFAR coordinate refinement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.detection.baseline import robust_normalize
from atabey.constants import DEFAULT_VOXEL_SCALE_UM
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
RADIUS = (1, 3, 3)


def dist(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def refine_peak(peak, volume: np.ndarray):
    normalized = robust_normalize(volume)
    center = np.rint([peak.z_um / DEFAULT_VOXEL_SCALE_UM.z, peak.y_um / DEFAULT_VOXEL_SCALE_UM.y, peak.x_um / DEFAULT_VOXEL_SCALE_UM.x]).astype(int)
    slices = []
    for axis, radius in enumerate(RADIUS):
        lo = max(0, center[axis] - radius)
        hi = min(volume.shape[axis], center[axis] + radius + 1)
        slices.append(slice(lo, hi))
    patch = normalized[tuple(slices)].astype(np.float64)
    baseline = float(np.percentile(patch, 25.0))
    weights = np.clip(patch - baseline, 0.0, None)
    if float(weights.sum()) <= 0.0:
        return peak
    grids = np.indices(patch.shape, dtype=np.float64)
    coords = [float((weights * grid).sum() / weights.sum() + slices[axis].start) for axis, grid in enumerate(grids)]
    z, y, x = coords
    z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(z, y, x)
    return UnetShadowPeak(
        peak_id=peak.peak_id,
        sample_id=peak.sample_id,
        t=peak.t,
        z_um=z_um,
        y_um=y_um,
        x_um=x_um,
        confidence=peak.confidence,
    )


def role_counts(peaks, t, gt_parent, gt_children):
    return {
        "parent": sum(p.t == t and dist(p.position_um, gt_parent.position_um) <= 7.0 for p in peaks),
        "daughter_1": sum(p.t == t + 1 and dist(p.position_um, gt_children[0].position_um) <= 7.0 for p in peaks),
        "daughter_2": sum(p.t == t + 1 and dist(p.position_um, gt_children[1].position_um) <= 7.0 for p in peaks),
    }


def matched_actions(graph, peaks, t, gt_parent, gt_children):
    enumeration = enumerate_anchored_division_actions(graph, peaks, parent_t=t, anchor_radius_um=14.0, formation_radius_um=14.0)
    matches = [
        action for action in enumeration.actions
        if action_matches_registered_division(
            action,
            parent_position_um=gt_parent.position_um,
            daughter_positions_um=(gt_children[0].position_um, gt_children[1].position_um),
            match_radius_um=7.0,
        )
    ]
    return enumeration, matches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for sample_id, t, parent_id, child_ids in CASES:
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(args.train_dir / f"{sample_id}.zarr", max_timepoints=t + 2)
        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        gt_parent = gt_nodes[parent_id]
        gt_children = [gt_nodes[child_id] for child_id in child_ids]
        array = open_competition_array(args.train_dir / f"{sample_id}.zarr")
        volumes = {frame: read_timepoint(array, frame) for frame in (t, t + 1)}
        original = [
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
        refined = [refine_peak(peak, volumes[peak.t]) if peak.t in volumes else peak for peak in original]
        before_enum, before_matches = matched_actions(graph, original, t, gt_parent, gt_children)
        after_enum, after_matches = matched_actions(graph, refined, t, gt_parent, gt_children)
        rows.append({
            "sample_id": sample_id,
            "t": t,
            "detector": detector,
            "link_strategy": link_strategy,
            "baseline_role_counts_7um": role_counts(original, t, gt_parent, gt_children),
            "refined_role_counts_7um": role_counts(refined, t, gt_parent, gt_children),
            "baseline_action_count": before_enum.division_action_count,
            "refined_action_count": after_enum.division_action_count,
            "baseline_official_7um_geometric_matches": len(before_matches),
            "refined_official_7um_geometric_matches": len(after_matches),
            "candidate_set_changed": False,
            "graph_mutated": False,
            "refinement_radius_voxels": RADIUS,
            "matching_action_ids_after": [[a.parent.peak_id, a.child_1.peak_id, a.child_2.peak_id] for a in after_matches],
        })
        print(f"{sample_id}: before={len(before_matches)} after={len(after_matches)} actions={before_enum.division_action_count}->{after_enum.division_action_count}", flush=True)

    summary = {
        "status": "read_only_v23_cfar_coordinate_refinement_shadow",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "refinement": "local_intensity_weighted_centroid",
        "refinement_radius_voxels": RADIUS,
        "cases": rows,
        "decision": "SHADOW_DIAGNOSTIC_ONLY",
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Coordinate Refinement Shadow Results",
        "",
        "Decision: **SHADOW DIAGNOSTIC ONLY**.",
        "",
        "A fixed local intensity-weighted centroid was evaluated on existing CFAR detections. Distinct daughter IDs were preserved. No candidate, edge, or graph was changed.",
        "",
        "| Sample | Baseline roles | Refined roles | Actions before/after | Official geometric matches before/after |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['sample_id']} t{row['t']} | {row['baseline_role_counts_7um']} | {row['refined_role_counts_7um']} | {row['baseline_action_count']}/{row['refined_action_count']} | {row['baseline_official_7um_geometric_matches']}/{row['refined_official_7um_geometric_matches']} |")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()




