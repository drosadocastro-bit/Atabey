"""Evaluate a track-conditioned, non-mutating low-confidence echo channel."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.detection.baseline import _cfar_background_stats_box, robust_normalize
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


ECHO_FLOOR = 0.35
ECHO_K_SIGMA = 0.80
ECHO_FOOTPRINT = (1, 3, 3)
ROUTER_RADIUS_UM = 14.0
DEDUP_RADIUS_UM = 3.0
OFFICIAL_RADIUS_UM = 7.0
FORMATION_RADIUS_UM = 14.0
SCALE = np.asarray(
    (DEFAULT_VOXEL_SCALE_UM.z, DEFAULT_VOXEL_SCALE_UM.y, DEFAULT_VOXEL_SCALE_UM.x),
    dtype=float,
)


def graph_signature(graph):
    nodes = tuple((node.node_id, int(node.t), *node.position_um) for node in graph.detections)
    edges = tuple((edge.source_id, edge.target_id, edge.relation) for edge in graph.edges)
    return nodes, edges


def prediction(node, incoming, nodes):
    predecessors = [nodes[source] for source in incoming.get(node.node_id, []) if source in nodes]
    predecessors = [item for item in predecessors if int(item.t) == int(node.t) - 1]
    current = np.asarray(node.position_um, dtype=float)
    if len(predecessors) != 1:
        return current, np.zeros(3, dtype=float), "stationary_fallback"
    previous = np.asarray(predecessors[0].position_um, dtype=float)
    velocity = current - previous
    return current + velocity, velocity, "velocity"


def echo_peaks(volume: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    source = volume.astype(np.float32)
    size = tuple(2 * radius + 1 for radius in ECHO_FOOTPRINT)
    maxima = ndimage.maximum_filter(source, size=size, mode="nearest")
    background_mean, background_std, _ = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
    )
    mask = (
        (source == maxima)
        & (normalized >= ECHO_FLOOR)
        & (normalized >= background_mean + ECHO_K_SIGMA * background_std)
    )
    coords_um = np.argwhere(mask).astype(float) * SCALE
    del normalized, source, maxima, background_mean, background_std, mask
    gc.collect()
    return coords_um


def gate_points(points: np.ndarray, centers: np.ndarray, radius_um: float) -> np.ndarray:
    if not len(points) or not len(centers):
        return np.empty((0, 3), dtype=float)
    from scipy.spatial import cKDTree

    tree = cKDTree(centers)
    distances, _ = tree.query(points, k=1)
    return points[distances <= radius_um]


def deduplicate_echo(echo: np.ndarray, primary: np.ndarray) -> np.ndarray:
    if not len(echo) or not len(primary):
        return echo
    from scipy.spatial import cKDTree

    distances, _ = cKDTree(primary).query(echo, k=1)
    return echo[distances > DEDUP_RADIUS_UM]


def combine(primary: np.ndarray, echo: np.ndarray) -> np.ndarray:
    new_echo = deduplicate_echo(echo, primary)
    if not len(primary):
        return new_echo
    if not len(new_echo):
        return primary
    return np.concatenate((primary, new_echo), axis=0)


def within(points: np.ndarray, target: np.ndarray, radius_um: float) -> np.ndarray:
    if not len(points):
        return np.empty((0, 3), dtype=float)
    return points[np.linalg.norm(points - target[None, :], axis=1) <= radius_um]


def geometry_available(parent_points, daughter_points, gt_parent, gt_daughters) -> bool:
    parents = within(parent_points, gt_parent, OFFICIAL_RADIUS_UM)
    left = within(daughter_points, gt_daughters[0], OFFICIAL_RADIUS_UM)
    right = within(daughter_points, gt_daughters[1], OFFICIAL_RADIUS_UM)
    for parent in parents:
        for first in left:
            for second in right:
                if np.linalg.norm(first - second) <= 1e-9:
                    continue
                if (
                    np.linalg.norm(first - parent) <= FORMATION_RADIUS_UM
                    and np.linalg.norm(second - parent) <= FORMATION_RADIUS_UM
                ):
                    return True
    return False


def approximate_roi_fraction(shape, centers: np.ndarray) -> float:
    if not len(centers):
        return 0.0
    from scipy.spatial import cKDTree

    axes = [
        np.linspace(0.0, max(0, dim - 1), count, dtype=float) * scale
        for dim, count, scale in zip(shape, (12, 64, 64), SCALE, strict=True)
    ]
    mesh = np.meshgrid(*axes, indexing="ij")
    probes = np.stack([axis.ravel() for axis in mesh], axis=1)
    distances, _ = cKDTree(centers).query(probes, k=1)
    return float(np.mean(distances <= ROUTER_RADIUS_UM))


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
    baseline_available = {row["case_id"]: bool(row["post_official_geometry_available"]) for row in prior}
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
        graph_nodes = {node.node_id: node for node in graph.detections}
        frame_nodes = defaultdict(list)
        for node in graph.detections:
            frame_nodes[int(node.t)].append(node)
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for edge in graph.edges:
            incoming[edge.target_id].append(edge.source_id)
            outgoing[edge.source_id].append(edge.target_id)

        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        array = open_competition_array(args.train_dir / f"{sample_id}.zarr")
        echo_cache = {}
        shape_cache = {}

        for case in cases:
            t = int(case["t"])
            for frame in (t, t + 1):
                if frame not in echo_cache:
                    volume = read_timepoint(array, frame)
                    shape_cache[frame] = tuple(int(value) for value in volume.shape)
                    echo_cache[frame] = echo_peaks(volume)
                    del volume
                    gc.collect()

            broken_centers = []
            broken_next_centers = []
            broken_modes = []
            for node in frame_nodes[t - 1]:
                next_ids = [target for target in outgoing.get(node.node_id, []) if target in graph_nodes and int(graph_nodes[target].t) == t]
                if next_ids:
                    continue
                predicted, velocity, mode = prediction(node, incoming, graph_nodes)
                broken_centers.append(predicted)
                broken_next_centers.append(predicted + velocity)
                broken_modes.append(mode)

            branch_centers = []
            branch_prediction_centers = []
            branch_modes = []
            for node in frame_nodes[t]:
                next_ids = [target for target in outgoing.get(node.node_id, []) if target in graph_nodes and int(graph_nodes[target].t) == t + 1]
                if len(next_ids) > 1:
                    continue
                predicted, _, mode = prediction(node, incoming, graph_nodes)
                branch_centers.append(np.asarray(node.position_um, dtype=float))
                branch_prediction_centers.append(predicted)
                branch_modes.append(mode)

            broken_centers_array = np.asarray(broken_centers, dtype=float).reshape((-1, 3))
            daughter_centers = np.asarray(
                branch_centers + branch_prediction_centers + broken_centers + broken_next_centers,
                dtype=float,
            ).reshape((-1, 3))
            gated_parent_echo = gate_points(echo_cache[t], broken_centers_array, ROUTER_RADIUS_UM)
            gated_daughter_echo = gate_points(echo_cache[t + 1], daughter_centers, ROUTER_RADIUS_UM)
            primary_parent = np.asarray([node.position_um for node in frame_nodes[t]], dtype=float).reshape((-1, 3))
            primary_daughter = np.asarray([node.position_um for node in frame_nodes[t + 1]], dtype=float).reshape((-1, 3))
            new_parent_echo = deduplicate_echo(gated_parent_echo, primary_parent)
            new_daughter_echo = deduplicate_echo(gated_daughter_echo, primary_daughter)
            combined_parent = combine(primary_parent, gated_parent_echo)
            combined_daughter = combine(primary_daughter, gated_daughter_echo)

            gt_parent = np.asarray(gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float)
            gt_daughters = [np.asarray(gt_nodes[int(node_id)].position_um, dtype=float) for node_id in case["gt_child_ids"]]
            primary_geometry = geometry_available(primary_parent, primary_daughter, gt_parent, gt_daughters)
            gated_geometry = geometry_available(combined_parent, combined_daughter, gt_parent, gt_daughters)
            rows.append({
                "case_id": case["case_id"],
                "sample_id": sample_id,
                "family": sample_id.split("_", 1)[0],
                "t": t,
                "cohort": "control" if baseline_available[case["case_id"]] else "failure",
                "detector": detector,
                "link_strategy": link_strategy,
                "broken_seed_count": len(broken_centers),
                "under_resolved_seed_count": len(branch_centers),
                "full_parent_echo_count": len(echo_cache[t]),
                "gated_parent_echo_count": len(gated_parent_echo),
                "new_parent_echo_count": len(new_parent_echo),
                "full_daughter_echo_count": len(echo_cache[t + 1]),
                "gated_daughter_echo_count": len(gated_daughter_echo),
                "new_daughter_echo_count": len(new_daughter_echo),
                "parent_echo_retention_fraction": len(gated_parent_echo) / max(1, len(echo_cache[t])),
                "daughter_echo_retention_fraction": len(gated_daughter_echo) / max(1, len(echo_cache[t + 1])),
                "parent_roi_volume_fraction_estimate": approximate_roi_fraction(shape_cache[t], broken_centers_array),
                "daughter_roi_volume_fraction_estimate": approximate_roi_fraction(shape_cache[t + 1], daughter_centers),
                "primary_geometry_available": primary_geometry,
                "range_gated_geometry_available": gated_geometry,
                "recovered": bool(not primary_geometry and gated_geometry),
                "abstained": bool(not len(broken_centers) and not len(branch_centers)),
                "zero_perturbation": before == graph_signature(graph),
                "candidate_set_changed": False,
                "graph_mutated": False,
            })
            print(
                f"{sample_id} t{t}: primary={primary_geometry} gated={gated_geometry} "
                f"echo={len(new_parent_echo)}+{len(new_daughter_echo)} "
                f"roi={rows[-1]['parent_roi_volume_fraction_estimate']:.3f}/"
                f"{rows[-1]['daughter_roi_volume_fraction_estimate']:.3f}",
                flush=True,
            )

    failures = [row for row in rows if row["cohort"] == "failure"]
    controls = [row for row in rows if row["cohort"] == "control"]
    added = [value for row in rows for value in (row["new_parent_echo_count"], row["new_daughter_echo_count"])]
    retention = [value for row in rows for value in (row["parent_echo_retention_fraction"], row["daughter_echo_retention_fraction"])]
    roi = [value for row in rows for value in (row["parent_roi_volume_fraction_estimate"], row["daughter_roi_volume_fraction_estimate"])]
    summary = {
        "status": "read_only_v23_range_gated_echo",
        "population": {"cases": len(rows), "failures": len(failures), "controls": len(controls)},
        "failure_recovered": sum(row["recovered"] for row in failures),
        "failure_geometry_available": sum(row["range_gated_geometry_available"] for row in failures),
        "control_geometry_available": sum(row["range_gated_geometry_available"] for row in controls),
        "added_echo_per_event_frame": {
            "median": float(np.median(added)),
            "p90": float(np.percentile(added, 90)),
            "max": int(max(added)),
        },
        "echo_retention_fraction": {
            "median": float(np.median(retention)),
            "p90": float(np.percentile(retention, 90)),
        },
        "roi_volume_fraction_estimate": {
            "median": float(np.median(roi)),
            "p90": float(np.percentile(roi, 90)),
        },
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    if summary["failure_recovered"] == 0:
        summary["decision"] = "NO_GO"
    elif summary["echo_retention_fraction"]["median"] >= 0.75:
        summary["decision"] = "NO_GO_ROUTER_TOO_BROAD"
    else:
        summary["decision"] = "HOLD_PARTIAL_RANGE_GATED_SIGNAL"

    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Range-Gated Echo Shadow Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "The fixed `floor=0.35, k=0.80` echo profile was admitted only inside 14 um windows generated from V19 broken endpoints and under-resolved parents. GT was used only after routing to score registered fork geometry. No candidates or graphs were mutated.",
        "",
        "| Event | Cohort | Primary geometry | Gated geometry | New parent + daughter echoes | ROI fraction parent / daughter |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['cohort']} | {row['primary_geometry_available']} | "
            f"{row['range_gated_geometry_available']} | {row['new_parent_echo_count']} + {row['new_daughter_echo_count']} | "
            f"{row['parent_roi_volume_fraction_estimate']:.3f} / {row['daughter_roi_volume_fraction_estimate']:.3f} |"
        )
    lines += [
        "",
        f"Failure recovery: **{summary['failure_recovered']}/{len(failures)}**.",
        f"Added echoes per event-frame: median **{summary['added_echo_per_event_frame']['median']:.1f}**, p90 **{summary['added_echo_per_event_frame']['p90']:.1f}**, max **{summary['added_echo_per_event_frame']['max']}**.",
        f"Echo-pool retention: median **{summary['echo_retention_fraction']['median']:.3f}**, p90 **{summary['echo_retention_fraction']['p90']:.3f}**.",
        f"Estimated ROI volume: median **{summary['roi_volume_fraction_estimate']['median']:.3f}**, p90 **{summary['roi_volume_fraction_estimate']['p90']:.3f}**.",
        "",
        "Guardrail: this is availability evidence only. It does not authorize candidate emission, edge creation, or graph mutation.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
