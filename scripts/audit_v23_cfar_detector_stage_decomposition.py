"""Locate the first CFAR detector stage that loses official fork geometry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atabey.detection.baseline import threshold_local_maxima_cfar
from atabey.detection.cfar_watershed import (
    threshold_local_maxima_cfar_sidelobe_watershed,
    threshold_local_maxima_cfar_watershed,
)
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def nearest_distance(detections, target):
    if not detections:
        return None
    return min(distance(item.position_um, target.position_um) for item in detections)


def official_geometry_available(parent_detections, daughter_detections, gt_parent, gt_children) -> bool:
    parents = [item for item in parent_detections if distance(item.position_um, gt_parent.position_um) <= 7.0]
    child_1 = [item for item in daughter_detections if distance(item.position_um, gt_children[0].position_um) <= 7.0]
    child_2 = [item for item in daughter_detections if distance(item.position_um, gt_children[1].position_um) <= 7.0]
    for parent in parents:
        for left in child_1:
            for right in child_2:
                if left.node_id == right.node_id:
                    continue
                if distance(left.position_um, parent.position_um) <= 14.0 and distance(right.position_um, parent.position_um) <= 14.0:
                    return True
    return False


def detect_stages(volume, sample_id: str, t: int):
    common = dict(
        threshold=defaults.cfar_threshold,
        min_distance_voxels=(1, 5, 5),
        max_detections=defaults.max_detections_per_timepoint,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
        cfar_threshold_mode=defaults.cfar_threshold_mode,
        cfar_k_sigma=defaults.cfar_k_sigma,
        cfar_pfa=defaults.cfar_pfa,
    )
    raw = threshold_local_maxima_cfar(sample_id, t, volume, **common)
    watershed = threshold_local_maxima_cfar_watershed(sample_id, t, volume, **common)
    post = threshold_local_maxima_cfar_sidelobe_watershed(
        sample_id,
        t,
        volume,
        **common,
        sidelobe_mode=defaults.sidelobe_mode,
        sidelobe_radius_voxels=defaults.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=defaults.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=defaults.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=defaults.sidelobe_floor_ratio,
    )
    return {"raw_cfar": raw, "watershed": watershed, "post_sidelobe": post}


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
    failures = [row for row in json.loads(args.pre_post.read_text(encoding="utf-8")) if not row["post_official_geometry_available"]]
    cache = {}
    arrays = {}
    gt_cache = {}
    rows = []
    for detector_row in failures:
        case = fixture[detector_row["case_id"]]
        sample_id = case["sample_id"]
        t = int(case["t"])
        if sample_id not in arrays:
            arrays[sample_id] = open_competition_array(args.train_dir / f"{sample_id}.zarr")
            gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
            gt_cache[sample_id] = {int(node.node_id): node for node in gt.nodes}
        for frame in (t, t + 1):
            key = sample_id, frame
            if key not in cache:
                cache[key] = detect_stages(read_timepoint(arrays[sample_id], frame), sample_id, frame)
        nodes = gt_cache[sample_id]
        gt_parent = nodes[int(case["gt_parent_id"])]
        gt_children = [nodes[int(child_id)] for child_id in case["gt_child_ids"]]
        stages = {}
        for stage in ("raw_cfar", "watershed", "post_sidelobe"):
            parent = cache[(sample_id, t)][stage]
            daughters = cache[(sample_id, t + 1)][stage]
            stages[stage] = {
                "parent_frame_count": len(parent),
                "daughter_frame_count": len(daughters),
                "parent_nearest_um": nearest_distance(parent, gt_parent),
                "daughter_1_nearest_um": nearest_distance(daughters, gt_children[0]),
                "daughter_2_nearest_um": nearest_distance(daughters, gt_children[1]),
                "official_geometry_available": official_geometry_available(parent, daughters, gt_parent, gt_children),
            }
        if not stages["raw_cfar"]["official_geometry_available"]:
            first_loss = "raw_cfar_peak_detection"
        elif not stages["watershed"]["official_geometry_available"]:
            first_loss = "watershed_coordinate_refinement"
        elif not stages["post_sidelobe"]["official_geometry_available"]:
            first_loss = "sidelobe_suppression"
        else:
            first_loss = "no_detector_stage_loss"
        rows.append({
            "case_id": case["case_id"],
            "sample_id": sample_id,
            "family": sample_id.split("_", 1)[0],
            "t": t,
            "stages": stages,
            "first_loss_stage": first_loss,
            "candidate_set_changed": False,
            "graph_mutated": False,
        })
        print(f"{sample_id} t{t}: raw={stages['raw_cfar']['official_geometry_available']} watershed={stages['watershed']['official_geometry_available']} post={stages['post_sidelobe']['official_geometry_available']} first={first_loss}", flush=True)

    counts = {stage: sum(row["first_loss_stage"] == stage for row in rows) for stage in sorted({row["first_loss_stage"] for row in rows})}
    summary = {
        "status": "read_only_v23_cfar_detector_stage_decomposition",
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {"cases": len(rows), "unique_frames": len(cache)},
        "first_loss_stage_counts": counts,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Detector-Stage Decomposition",
        "",
        "Decision: **READ-ONLY DIAGNOSTIC**.",
        "",
        "Seven events without post-sidelobe official geometry were traced through raw CFAR peaks, watershed coordinate refinement, and sidelobe suppression. No candidate, edge, or graph was changed.",
        "",
        "| Sample | Raw geometry | Watershed geometry | Post-sidelobe geometry | First loss stage |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        stages = row["stages"]
        lines.append(f"| {row['sample_id']} t{row['t']} | {stages['raw_cfar']['official_geometry_available']} | {stages['watershed']['official_geometry_available']} | {stages['post_sidelobe']['official_geometry_available']} | {row['first_loss_stage']} |")
    lines += ["", "First-loss counts: " + ", ".join(f"`{name}`={count}" for name, count in counts.items()) + "."]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
