"""Compare frozen CFAR peaks immediately before and after sidelobe suppression."""

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

from atabey.detection.cfar_watershed import (
    threshold_local_maxima_cfar_sidelobe_watershed,
    threshold_local_maxima_cfar_watershed,
)
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint


def distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def nearest(detections, target):
    if not detections:
        return None
    detection = min(detections, key=lambda item: distance(item.position_um, target.position_um))
    return {
        "id": detection.node_id,
        "distance_um": distance(detection.position_um, target.position_um),
    }


def official_geometry_available(parent_detections, daughter_detections, gt_parent, gt_children) -> bool:
    parents = [item for item in parent_detections if distance(item.position_um, gt_parent.position_um) <= 7.0]
    child_1 = [item for item in daughter_detections if distance(item.position_um, gt_children[0].position_um) <= 7.0]
    child_2 = [item for item in daughter_detections if distance(item.position_um, gt_children[1].position_um) <= 7.0]
    for parent in parents:
        nearby = [item for item in daughter_detections if distance(item.position_um, parent.position_um) <= 14.0]
        nearby_ids = {item.node_id for item in nearby}
        for left in child_1:
            for right in child_2:
                if left.node_id != right.node_id and left.node_id in nearby_ids and right.node_id in nearby_ids:
                    return True
    return False


def detect(volume, sample_id: str, t: int):
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
    pre = threshold_local_maxima_cfar_watershed(sample_id, t, volume, **common)
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
    return pre, post


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = pd.DataFrame(json.loads(args.fixture.read_text(encoding="utf-8"))["cases"])
    availability = pd.read_csv(args.availability)
    route = availability[availability.source_detector.eq("cfar_sidelobe")][["case_id", "sample_id", "t"]]
    cases = fixture.merge(route, on=["case_id", "sample_id", "t"], how="inner", validate="one_to_one")
    cache = {}
    gt_cache = {}
    array_cache = {}
    rows = []
    for case in cases.sort_values(["sample_id", "t"]).itertuples(index=False):
        sample_id = case.sample_id
        if sample_id not in gt_cache:
            gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
            gt_cache[sample_id] = {int(node.node_id): node for node in gt.nodes}
            array_cache[sample_id] = open_competition_array(args.train_dir / f"{sample_id}.zarr")
        gt_nodes = gt_cache[sample_id]
        gt_parent = gt_nodes[int(case.gt_parent_id)]
        gt_children = [gt_nodes[int(child_id)] for child_id in case.gt_child_ids]
        for frame in (int(case.t), int(case.t) + 1):
            key = (sample_id, frame)
            if key not in cache:
                cache[key] = detect(read_timepoint(array_cache[sample_id], frame), sample_id, frame)
        pre_parent, post_parent = cache[(sample_id, int(case.t))]
        pre_daughters, post_daughters = cache[(sample_id, int(case.t) + 1)]
        role_targets = [("parent", gt_parent, pre_parent, post_parent), ("daughter_1", gt_children[0], pre_daughters, post_daughters), ("daughter_2", gt_children[1], pre_daughters, post_daughters)]
        role_rows = []
        for role, target, pre, post in role_targets:
            pre_nearest = nearest(pre, target)
            post_nearest = nearest(post, target)
            role_rows.append({
                "role": role,
                "pre_nearest_id": pre_nearest["id"] if pre_nearest else None,
                "pre_nearest_distance_um": pre_nearest["distance_um"] if pre_nearest else None,
                "post_nearest_id": post_nearest["id"] if post_nearest else None,
                "post_nearest_distance_um": post_nearest["distance_um"] if post_nearest else None,
                "pre_within_7um": bool(pre_nearest and pre_nearest["distance_um"] <= 7.0),
                "post_within_7um": bool(post_nearest and post_nearest["distance_um"] <= 7.0),
            })
        pre_available = official_geometry_available(pre_parent, pre_daughters, gt_parent, gt_children)
        post_available = official_geometry_available(post_parent, post_daughters, gt_parent, gt_children)
        rows.append({
            "case_id": case.case_id,
            "sample_id": sample_id,
            "family": sample_id.split("_", 1)[0],
            "t": int(case.t),
            "pre_parent_count": len(pre_parent),
            "post_parent_count": len(post_parent),
            "pre_daughter_frame_count": len(pre_daughters),
            "post_daughter_frame_count": len(post_daughters),
            "role_comparison": role_rows,
            "pre_official_geometry_available": pre_available,
            "post_official_geometry_available": post_available,
            "sidelobe_caused_official_loss": bool(pre_available and not post_available),
            "sidelobe_recovered_official_geometry": bool(post_available and not pre_available),
            "candidate_set_changed": False,
            "graph_mutated": False,
        })
        print(f"{sample_id} t{case.t}: counts={len(pre_parent)}/{len(post_parent)}->{len(pre_daughters)}/{len(post_daughters)} official={pre_available}->{post_available}", flush=True)

    role_flat = [dict(case_id=row["case_id"], sample_id=row["sample_id"], t=row["t"], **role) for row in rows for role in row["role_comparison"]]
    summary = {
        "status": "read_only_v23_cfar_pre_post_sidelobe_11",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {"cases": len(rows), "unique_frames": len(cache)},
        "pre_official_geometry_available": sum(row["pre_official_geometry_available"] for row in rows),
        "post_official_geometry_available": sum(row["post_official_geometry_available"] for row in rows),
        "sidelobe_caused_official_loss": sum(row["sidelobe_caused_official_loss"] for row in rows),
        "roles_lost_from_7um": sum(role["pre_within_7um"] and not role["post_within_7um"] for role in role_flat),
        "roles_preserved_within_7um": sum(role["pre_within_7um"] and role["post_within_7um"] for role in role_flat),
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Pre/Post Sidelobe Audit: 11 Events",
        "",
        "Decision: **READ-ONLY DETECTOR-STAGE SHADOW**.",
        "",
        "The frozen watershed CFAR detector was compared immediately before and after sidelobe suppression. No candidate, edge, or graph was changed.",
        "",
        "| Sample | Parent peaks pre/post | Daughter-frame peaks pre/post | Official geometry pre/post | Sidelobe-caused loss |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(f"| {row['sample_id']} t{row['t']} | {row['pre_parent_count']}/{row['post_parent_count']} | {row['pre_daughter_frame_count']}/{row['post_daughter_frame_count']} | {row['pre_official_geometry_available']}/{row['post_official_geometry_available']} | {row['sidelobe_caused_official_loss']} |")
    lines += [
        "",
        f"Pre-sidelobe official geometric availability: `{summary['pre_official_geometry_available']}/{len(rows)}`; post-sidelobe: `{summary['post_official_geometry_available']}/{len(rows)}`.",
        f"Sidelobe-caused official losses: `{summary['sidelobe_caused_official_loss']}`; individual registered roles lost from 7 um: `{summary['roles_lost_from_7um']}`.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
