"""Measure a non-mutating low-confidence peak channel response surface."""

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


PRIMARY_FOOTPRINT = (1, 5, 5)
ECHO_FOOTPRINT = (1, 3, 3)
ECHO_FLOORS = (0.45, 0.40, 0.35, 0.30, 0.25)
ECHO_K_SIGMAS = (1.10, 0.80, 0.50)
OFFICIAL_RADIUS_UM = 7.0
FORMATION_RADIUS_UM = 14.0
SCALE = np.asarray(
    (DEFAULT_VOXEL_SCALE_UM.z, DEFAULT_VOXEL_SCALE_UM.y, DEFAULT_VOXEL_SCALE_UM.x),
    dtype=float,
)


def profile_name(floor: float, k_sigma: float) -> str:
    return f"floor_{floor:.2f}_k_{k_sigma:.2f}"


def unique_coords(*arrays: np.ndarray) -> np.ndarray:
    available = [array for array in arrays if len(array)]
    if not available:
        return np.empty((0, 3), dtype=np.int32)
    return np.unique(np.concatenate(available, axis=0), axis=0).astype(np.int32, copy=False)


def count_new_coords(primary: np.ndarray, echo: np.ndarray) -> int:
    if not len(echo):
        return 0
    primary_set = {tuple(int(v) for v in coord) for coord in primary}
    return sum(tuple(int(v) for v in coord) not in primary_set for coord in echo)


def within_radius(coords: np.ndarray, target_um: np.ndarray, radius_um: float) -> np.ndarray:
    if not len(coords):
        return np.empty((0, 3), dtype=np.int32)
    distances = np.linalg.norm(coords.astype(float) * SCALE - target_um[None, :], axis=1)
    return coords[distances <= radius_um]


def geometry_available(
    parent_coords: np.ndarray,
    daughter_coords: np.ndarray,
    parent_um: np.ndarray,
    daughter_ums: list[np.ndarray],
) -> bool:
    parents = within_radius(parent_coords, parent_um, OFFICIAL_RADIUS_UM)
    left = within_radius(daughter_coords, daughter_ums[0], OFFICIAL_RADIUS_UM)
    right = within_radius(daughter_coords, daughter_ums[1], OFFICIAL_RADIUS_UM)
    for parent in parents:
        parent_position = parent.astype(float) * SCALE
        for first in left:
            for second in right:
                if np.array_equal(first, second):
                    continue
                if (
                    np.linalg.norm(first.astype(float) * SCALE - parent_position)
                    <= FORMATION_RADIUS_UM
                    and np.linalg.norm(second.astype(float) * SCALE - parent_position)
                    <= FORMATION_RADIUS_UM
                ):
                    return True
    return False


def analyze_frame(volume: np.ndarray) -> dict[str, object]:
    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    peak_source = volume.astype(np.float32)
    background_mean, background_std, _ = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
    )

    primary_size = tuple(2 * radius + 1 for radius in PRIMARY_FOOTPRINT)
    primary_max = ndimage.maximum_filter(peak_source, size=primary_size, mode="nearest")
    primary_mask = (
        (peak_source == primary_max)
        & (normalized >= defaults.cfar_threshold)
        & (normalized >= background_mean + defaults.cfar_k_sigma * background_std)
    )
    primary_coords = np.argwhere(primary_mask).astype(np.int32, copy=False)
    if len(primary_coords):
        values = normalized[primary_mask]
        thresholds = (background_mean + defaults.cfar_k_sigma * background_std)[primary_mask]
        margins = np.maximum(0.0, (values - thresholds) / np.maximum(thresholds, 1e-6))
        order = np.argsort(margins)[::-1]
        primary_coords = primary_coords[order[: defaults.max_detections_per_timepoint]]

    echo_size = tuple(2 * radius + 1 for radius in ECHO_FOOTPRINT)
    echo_max = ndimage.maximum_filter(peak_source, size=echo_size, mode="nearest")
    echo_peak_mask = peak_source == echo_max
    profiles: dict[str, np.ndarray] = {}
    for floor in ECHO_FLOORS:
        for k_sigma in ECHO_K_SIGMAS:
            mask = (
                echo_peak_mask
                & (normalized >= floor)
                & (normalized >= background_mean + k_sigma * background_std)
            )
            profiles[profile_name(floor, k_sigma)] = np.argwhere(mask).astype(
                np.int32,
                copy=False,
            )

    result: dict[str, object] = {
        "primary": primary_coords,
        "echo_profiles": profiles,
    }
    del normalized, peak_source, background_mean, background_std
    del primary_max, primary_mask, echo_max, echo_peak_mask
    gc.collect()
    return result


def quantiles(values: list[int]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=float)
    return {
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "max": int(array.max()),
        "sum": int(array.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--pre-post", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    prior_rows = json.loads(args.pre_post.read_text(encoding="utf-8"))
    case_ids = [row["case_id"] for row in prior_rows]
    baseline_available = {
        row["case_id"]: bool(row["post_official_geometry_available"])
        for row in prior_rows
    }

    arrays: dict[str, object] = {}
    graphs: dict[str, dict[int, object]] = {}
    frame_cache: dict[tuple[str, int], dict[str, object]] = {}
    rows = []
    for index, case_id in enumerate(case_ids, start=1):
        case = fixture[case_id]
        sample_id = case["sample_id"]
        t = int(case["t"])
        if sample_id not in arrays:
            arrays[sample_id] = open_competition_array(args.train_dir / f"{sample_id}.zarr")
            graph = read_geff_graph(args.train_dir / f"{sample_id}.geff")
            graphs[sample_id] = {int(node.node_id): node for node in graph.nodes}
        for frame in (t, t + 1):
            key = sample_id, frame
            if key not in frame_cache:
                frame_cache[key] = analyze_frame(read_timepoint(arrays[sample_id], frame))

        nodes = graphs[sample_id]
        parent_um = np.asarray(nodes[int(case["gt_parent_id"])].position_um, dtype=float)
        daughter_ums = [
            np.asarray(nodes[int(node_id)].position_um, dtype=float)
            for node_id in case["gt_child_ids"]
        ]
        parent_frame = frame_cache[(sample_id, t)]
        daughter_frame = frame_cache[(sample_id, t + 1)]
        primary_parent = parent_frame["primary"]
        primary_daughter = daughter_frame["primary"]
        primary_available = geometry_available(
            primary_parent,
            primary_daughter,
            parent_um,
            daughter_ums,
        )
        profile_results = {}
        for floor in ECHO_FLOORS:
            for k_sigma in ECHO_K_SIGMAS:
                name = profile_name(floor, k_sigma)
                echo_parent = parent_frame["echo_profiles"][name]
                echo_daughter = daughter_frame["echo_profiles"][name]
                union_parent = unique_coords(primary_parent, echo_parent)
                union_daughter = unique_coords(primary_daughter, echo_daughter)
                profile_results[name] = {
                    "floor": floor,
                    "k_sigma": k_sigma,
                    "available": geometry_available(
                        union_parent,
                        union_daughter,
                        parent_um,
                        daughter_ums,
                    ),
                    "added_parent_candidates": count_new_coords(primary_parent, echo_parent),
                    "added_daughter_candidates": count_new_coords(primary_daughter, echo_daughter),
                }
        rows.append(
            {
                "case_id": case_id,
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "cohort": "control" if baseline_available[case_id] else "failure",
                "primary_available": primary_available,
                "profiles": profile_results,
                "candidate_set_changed": False,
                "graph_mutated": False,
            }
        )
        recovered = sum(
            result["available"] and not primary_available
            for result in profile_results.values()
        )
        print(
            f"[{index}/{len(case_ids)}] {sample_id} t{t}: "
            f"primary={primary_available} recovering_profiles={recovered}",
            flush=True,
        )

    profile_summaries = {}
    for floor in ECHO_FLOORS:
        for k_sigma in ECHO_K_SIGMAS:
            name = profile_name(floor, k_sigma)
            failures = [row for row in rows if row["cohort"] == "failure"]
            controls = [row for row in rows if row["cohort"] == "control"]
            frame_additions = []
            for row in rows:
                result = row["profiles"][name]
                frame_additions.extend(
                    (result["added_parent_candidates"], result["added_daughter_candidates"])
                )
            profile_summaries[name] = {
                "floor": floor,
                "k_sigma": k_sigma,
                "failure_recovered": sum(row["profiles"][name]["available"] for row in failures),
                "failure_total": len(failures),
                "control_raw_geometry_available": sum(
                    row["profiles"][name]["available"] for row in controls
                ),
                "control_total": len(controls),
                "added_candidates_per_event_frame": quantiles(frame_additions),
            }

    pareto = []
    for name, result in profile_summaries.items():
        dominated = any(
            other["failure_recovered"] >= result["failure_recovered"]
            and other["added_candidates_per_event_frame"]["median"]
            <= result["added_candidates_per_event_frame"]["median"]
            and (
                other["failure_recovered"] > result["failure_recovered"]
                or other["added_candidates_per_event_frame"]["median"]
                < result["added_candidates_per_event_frame"]["median"]
            )
            for other_name, other in profile_summaries.items()
            if other_name != name
        )
        if not dominated:
            pareto.append(name)

    max_recovery = max(item["failure_recovered"] for item in profile_summaries.values())
    if max_recovery == 0:
        decision = "NO_GO"
    elif not pareto:
        decision = "HOLD"
    else:
        decision = "HOLD_FOR_CONDITIONED_ROUTER_REVIEW"
    summary = {
        "status": "read_only_v23_low_confidence_peak_channel",
        "population": {"cases": len(rows), "failures": 7, "controls": 4},
        "decision": decision,
        "max_failure_recovery": max_recovery,
        "pareto_profiles": pareto,
        "profiles": profile_summaries,
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 Low-Confidence Peak Channel Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "The frozen CFAR primary was unioned in shadow with a lower-confidence `(1,3,3)` echo-peak pool. Sparse GT was used only for registered fork availability; unrelated echo peaks were measured as candidate inflation, not labeled false positives.",
        "",
        "| Profile | Recovered failures | Raw+echo geometry on production controls | Added/frame median | Added/frame p90 | Added/frame max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in sorted(
        profile_summaries.items(),
        key=lambda item: (
            -item[1]["failure_recovered"],
            item[1]["added_candidates_per_event_frame"]["median"],
        ),
    ):
        additions = result["added_candidates_per_event_frame"]
        lines.append(
            f"| `{name}` | {result['failure_recovered']}/7 | "
            f"{result['control_raw_geometry_available']}/4 | {additions['median']:.1f} | "
            f"{additions['p90']:.1f} | {additions['max']} |"
        )
    lines += [
        "",
        "Pareto profiles: " + ", ".join(f"`{name}`" for name in pareto) + ".",
        "",
        "Production preservation remains 4/4 by construction because this is a non-mutating shadow. One production control lacks valid raw-peak geometry and is recovered by the unchanged watershed stage; the control column therefore reports raw+echo availability, not a production regression.",
        "",
        "Guardrail: this result does not authorize production detections or graph mutation. Any retained profile must next be constrained by track prediction, temporal continuity, and ownership evidence.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "profiles"}, indent=2), flush=True)


if __name__ == "__main__":
    main()


