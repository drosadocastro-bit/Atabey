"""Diagnose raw-CFAR losses without changing the production detector."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.detection.baseline import _cfar_background_stats_box, robust_normalize
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint


CONTROL_FOOTPRINT = (1, 5, 5)
DISTINCT_RETENTION_FOOTPRINT = (1, 3, 3)
OFFICIAL_RADIUS_UM = 7.0
FORMATION_RADIUS_UM = 14.0


def physical_distance(coords: np.ndarray, target_um: np.ndarray) -> np.ndarray:
    scale = np.asarray(
        (DEFAULT_VOXEL_SCALE_UM.z, DEFAULT_VOXEL_SCALE_UM.y, DEFAULT_VOXEL_SCALE_UM.x),
        dtype=float,
    )
    return np.linalg.norm(coords.astype(float) * scale - target_um[None, :], axis=1)


def nearest_um(coords: np.ndarray, target_um: np.ndarray) -> float | None:
    if len(coords) == 0:
        return None
    return float(physical_distance(coords, target_um).min())


def within_radius(coords: np.ndarray, target_um: np.ndarray, radius_um: float) -> np.ndarray:
    if len(coords) == 0:
        return np.empty((0, 3), dtype=np.int32)
    return coords[physical_distance(coords, target_um) <= radius_um]


def role_summary(stage_coords: dict[str, np.ndarray], target_um: np.ndarray) -> dict[str, object]:
    counts = {
        stage: int(len(within_radius(coords, target_um, OFFICIAL_RADIUS_UM)))
        for stage, coords in stage_coords.items()
    }
    nearest = {
        stage: nearest_um(coords, target_um)
        for stage, coords in stage_coords.items()
    }
    if counts["local_maxima"] == 0:
        first_blocker = "local_maximum_footprint"
    elif counts["global_floor"] == 0:
        first_blocker = "global_floor"
    elif counts["adaptive_eligible"] == 0:
        first_blocker = "adaptive_threshold"
    elif counts["retained"] == 0:
        first_blocker = "top_900_cap"
    else:
        first_blocker = "retained"
    return {
        "counts_within_7um": counts,
        "nearest_um": nearest,
        "first_blocker": first_blocker,
    }


def geometry_summary(
    parent_coords: np.ndarray,
    daughter_coords: np.ndarray,
    parent_um: np.ndarray,
    daughter_ums: list[np.ndarray],
) -> dict[str, object]:
    parents = within_radius(parent_coords, parent_um, OFFICIAL_RADIUS_UM)
    left = within_radius(daughter_coords, daughter_ums[0], OFFICIAL_RADIUS_UM)
    right = within_radius(daughter_coords, daughter_ums[1], OFFICIAL_RADIUS_UM)
    distinct_pairs = 0
    formed_pairs = 0
    scale = np.asarray(
        (DEFAULT_VOXEL_SCALE_UM.z, DEFAULT_VOXEL_SCALE_UM.y, DEFAULT_VOXEL_SCALE_UM.x),
        dtype=float,
    )
    for parent in parents:
        parent_position = parent.astype(float) * scale
        for first in left:
            for second in right:
                if np.array_equal(first, second):
                    continue
                distinct_pairs += 1
                if (
                    np.linalg.norm(first.astype(float) * scale - parent_position)
                    <= FORMATION_RADIUS_UM
                    and np.linalg.norm(second.astype(float) * scale - parent_position)
                    <= FORMATION_RADIUS_UM
                ):
                    formed_pairs += 1
    if len(parents) == 0:
        failure = "missing_parent"
    elif len(left) == 0:
        failure = "missing_daughter_1"
    elif len(right) == 0:
        failure = "missing_daughter_2"
    elif distinct_pairs == 0:
        failure = "no_distinct_daughter_pair"
    elif formed_pairs == 0:
        failure = "no_pair_inside_14um"
    else:
        failure = "available"
    return {
        "parent_candidates": int(len(parents)),
        "daughter_1_candidates": int(len(left)),
        "daughter_2_candidates": int(len(right)),
        "distinct_pairs": int(distinct_pairs),
        "formed_pairs": int(formed_pairs),
        "available": formed_pairs > 0,
        "failure": failure,
    }


def analyze_frame(volume: np.ndarray, footprint: tuple[int, int, int]) -> dict[str, np.ndarray]:
    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    peak_source = volume.astype(np.float32)
    peak_size = tuple(2 * radius + 1 for radius in footprint)
    local_maxima_mask = peak_source == ndimage.maximum_filter(
        peak_source,
        size=peak_size,
        mode="nearest",
    )
    global_floor_mask = local_maxima_mask & (normalized >= defaults.cfar_threshold)
    background_mean, background_std, _ = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
    )
    adaptive_threshold = background_mean + defaults.cfar_k_sigma * background_std
    eligible_mask = global_floor_mask & (normalized >= adaptive_threshold)
    eligible_coords = np.argwhere(eligible_mask).astype(np.int32, copy=False)
    if len(eligible_coords):
        values = normalized[eligible_mask]
        thresholds = adaptive_threshold[eligible_mask]
        margins = np.maximum(0.0, (values - thresholds) / np.maximum(thresholds, 1e-6))
        order = np.argsort(margins)[::-1]
        retained = eligible_coords[order[: defaults.max_detections_per_timepoint]]
    else:
        retained = np.empty((0, 3), dtype=np.int32)
    result = {
        "local_maxima": np.argwhere(local_maxima_mask).astype(np.int32, copy=False),
        "global_floor": np.argwhere(global_floor_mask).astype(np.int32, copy=False),
        "adaptive_eligible": eligible_coords,
        "retained": retained,
    }
    del normalized, peak_source, local_maxima_mask, global_floor_mask
    del background_mean, background_std, adaptive_threshold, eligible_mask
    gc.collect()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--stage-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    failed_ids = [
        row["case_id"]
        for row in json.loads(args.stage_audit.read_text(encoding="utf-8"))
        if row["first_loss_stage"] == "raw_cfar_peak_detection"
    ]

    rows = []
    arrays: dict[str, object] = {}
    graphs: dict[str, dict[int, object]] = {}
    for index, case_id in enumerate(failed_ids, start=1):
        case = fixture[case_id]
        sample_id = case["sample_id"]
        t = int(case["t"])
        if sample_id not in arrays:
            arrays[sample_id] = open_competition_array(args.train_dir / f"{sample_id}.zarr")
            graph = read_geff_graph(args.train_dir / f"{sample_id}.geff")
            graphs[sample_id] = {int(node.node_id): node for node in graph.nodes}
        nodes = graphs[sample_id]
        parent = nodes[int(case["gt_parent_id"])]
        daughters = [nodes[int(node_id)] for node_id in case["gt_child_ids"]]
        parent_um = np.asarray(parent.position_um, dtype=float)
        daughter_ums = [np.asarray(node.position_um, dtype=float) for node in daughters]

        variants = {}
        for name, footprint in (
            ("control_1_5_5", CONTROL_FOOTPRINT),
            ("distinct_retention_1_3_3", DISTINCT_RETENTION_FOOTPRINT),
        ):
            parent_stages = analyze_frame(read_timepoint(arrays[sample_id], t), footprint)
            daughter_stages = analyze_frame(read_timepoint(arrays[sample_id], t + 1), footprint)
            variants[name] = {
                "footprint": list(footprint),
                "frame_counts": {
                    "parent": {stage: int(len(coords)) for stage, coords in parent_stages.items()},
                    "daughter": {stage: int(len(coords)) for stage, coords in daughter_stages.items()},
                },
                "roles": {
                    "parent": role_summary(parent_stages, parent_um),
                    "daughter_1": role_summary(daughter_stages, daughter_ums[0]),
                    "daughter_2": role_summary(daughter_stages, daughter_ums[1]),
                },
                "eligible_geometry": geometry_summary(
                    parent_stages["adaptive_eligible"],
                    daughter_stages["adaptive_eligible"],
                    parent_um,
                    daughter_ums,
                ),
                "retained_geometry": geometry_summary(
                    parent_stages["retained"],
                    daughter_stages["retained"],
                    parent_um,
                    daughter_ums,
                ),
            }
            del parent_stages, daughter_stages
            gc.collect()

        control = variants["control_1_5_5"]["retained_geometry"]
        shadow = variants["distinct_retention_1_3_3"]["retained_geometry"]
        rows.append(
            {
                "case_id": case_id,
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "variants": variants,
                "control_failure": control["failure"],
                "narrow_shadow_recovered": bool(not control["available"] and shadow["available"]),
                "candidate_set_changed": False,
                "graph_mutated": False,
            }
        )
        print(
            f"[{index}/{len(failed_ids)}] {sample_id} t{t}: "
            f"control={control['failure']} narrow={shadow['failure']}",
            flush=True,
        )

    blocker_counts: dict[str, int] = {}
    for row in rows:
        for role in ("parent", "daughter_1", "daughter_2"):
            blocker = row["variants"]["control_1_5_5"]["roles"][role]["first_blocker"]
            if blocker != "retained":
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    summary = {
        "status": "read_only_v23_raw_cfar_upstream_bottleneck",
        "population": {"cases": len(rows)},
        "control_failure_counts": {
            reason: sum(row["control_failure"] == reason for row in rows)
            for reason in sorted({row["control_failure"] for row in rows})
        },
        "missing_role_first_blocker_counts": blocker_counts,
        "narrow_shadow_recovered_cases": sum(row["narrow_shadow_recovered"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 Raw CFAR Upstream Bottleneck Audit",
        "",
        "Decision: **READ-ONLY SHADOW DIAGNOSTIC**.",
        "",
        "The seven raw-CFAR failures were decomposed into local-maximum, global-floor, adaptive-threshold, and top-900-cap stages. A single narrower `(1,3,3)` peak footprint was evaluated as a frozen shadow for distinct-daughter retention. Production candidates and graphs were not changed.",
        "",
        "| Event | Control failure | Missing-role blockers | Narrow shadow |",
        "|---|---|---|---|",
    ]
    for row in rows:
        roles = row["variants"]["control_1_5_5"]["roles"]
        blockers = ", ".join(
            f"{role}={data['first_blocker']}"
            for role, data in roles.items()
            if data["first_blocker"] != "retained"
        ) or "none"
        narrow = row["variants"]["distinct_retention_1_3_3"]["retained_geometry"]["failure"]
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['control_failure']} | "
            f"{blockers} | {narrow} |"
        )
    lines += [
        "",
        "Aggregate:",
        "",
        f"- Control failures: `{summary['control_failure_counts']}`.",
        f"- Missing-role first blockers: `{summary['missing_role_first_blocker_counts']}`.",
        f"- Cases recovered by the narrower shadow: **{summary['narrow_shadow_recovered_cases']}/{len(rows)}**.",
        "- Zero perturbation: no candidate set or graph was changed.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
