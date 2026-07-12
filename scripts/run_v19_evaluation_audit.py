from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Any

from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS, DEFAULT_KINEMATIC_RECOVERY_SETTINGS
from atabey.io.geff_reader import read_geff_graph

try:
    from run_hybrid_submission import build_graph_cfar_sidelobe
except ModuleNotFoundError:
    from scripts.run_hybrid_submission import build_graph_cfar_sidelobe


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V19 Evaluation Coverage Audit")
    parser.add_argument("--train-dir", default="train")
    parser.add_argument("--samples", type=int, default=None, help="Number of samples to run")
    parser.add_argument("--output-json", default="submissions/v19_evaluation_audit.json")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    train_dir = Path(args.train_dir)
    output_json = Path(args.output_json)

    zarr_files = sorted(list(train_dir.glob("*.zarr")))
    if not zarr_files:
        print("No zarr files found in train_dir")
        return

    samples_to_run = zarr_files[:args.samples]
    results = []

    total_strict_nodes = 0
    total_relaxed_nodes = 0
    total_strict_edges = 0
    total_relaxed_edges = 0
    total_evaluable_strict_edges = 0
    total_evaluable_relaxed_edges = 0

    defaults = DEFAULT_HYBRID_FROZEN_DEFAULTS

    for sample_path in samples_to_run:
        sample_id = sample_path.stem
        geff_path = train_dir / f"{sample_id}.geff"
        if not geff_path.exists():
            continue

        if sample_id == "6bba_6ca87370":
            print(f"Skipping known bad sample {sample_id}...")
            continue

        print(f"Building graph for {sample_id}...")
        start_time = time.perf_counter()
        graph, _fallbacks = build_graph_cfar_sidelobe(
            sample_path=sample_path,
            threshold=defaults.cfar_threshold,
            cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
            cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
            cfar_k_sigma=defaults.cfar_k_sigma,
            cfar_threshold_mode=defaults.cfar_threshold_mode,
            cfar_pfa=defaults.cfar_pfa,
            sidelobe_mode=defaults.sidelobe_mode,
            sidelobe_radius_voxels=defaults.sidelobe_radius_voxels,
            sidelobe_axial_z_radius_voxels=defaults.sidelobe_axial_z_radius_voxels,
            sidelobe_axial_xy_tolerance_voxels=defaults.sidelobe_axial_xy_tolerance_voxels,
            sidelobe_floor_ratio=defaults.sidelobe_floor_ratio,
            max_detections_per_timepoint=defaults.max_detections_per_timepoint,
            link_strategy=defaults.cfar_link_strategy,
            max_link_distance_um=defaults.cfar_max_link_distance_um,
            max_timepoints=None,
        )
        build_seconds = float(time.perf_counter() - start_time)

        print(f"Evaluating {sample_id}...")
        gt_graph = read_geff_graph(geff_path)

        strict_report = evaluate_sparse_ground_truth(graph, gt_graph, match_radius_um=7.0)
        relaxed_report = evaluate_sparse_ground_truth(graph, gt_graph, match_radius_um=14.0)

        results.append({
            "sample_id": sample_id,
            "build_seconds": build_seconds,
            "strict_matched_nodes": strict_report.matched_sparse_nodes,
            "relaxed_matched_nodes": relaxed_report.matched_sparse_nodes,
            "strict_evaluable_edges": strict_report.evaluable_sparse_edges,
            "relaxed_evaluable_edges": relaxed_report.evaluable_sparse_edges,
            "node_coverage_gain": relaxed_report.matched_sparse_nodes - strict_report.matched_sparse_nodes,
            "edge_coverage_gain": relaxed_report.evaluable_sparse_edges - strict_report.evaluable_sparse_edges,
        })

        total_strict_nodes += strict_report.matched_sparse_nodes
        total_relaxed_nodes += relaxed_report.matched_sparse_nodes
        total_strict_edges += strict_report.matched_sparse_edges
        total_relaxed_edges += relaxed_report.matched_sparse_edges
        total_evaluable_strict_edges += strict_report.evaluable_sparse_edges
        total_evaluable_relaxed_edges += relaxed_report.evaluable_sparse_edges

        # Save incrementally
        summary = {
            "samples_run": len(results),
            "total_strict_matched_nodes": total_strict_nodes,
            "total_relaxed_matched_nodes": total_relaxed_nodes,
            "node_coverage_increase_percent": ((total_relaxed_nodes - total_strict_nodes) / max(total_strict_nodes, 1)) * 100 if total_strict_nodes > 0 else 0,
            "total_strict_evaluable_edges": total_evaluable_strict_edges,
            "total_relaxed_evaluable_edges": total_evaluable_relaxed_edges,
            "edge_coverage_increase_percent": ((total_evaluable_relaxed_edges - total_evaluable_strict_edges) / max(total_evaluable_strict_edges, 1)) * 100 if total_evaluable_strict_edges > 0 else 0,
        }
        output_payload = {
            "metadata": {
                "experiment": "v19_evaluation_audit",
                "strict_radius_um": 7.0,
                "relaxed_radius_um": 14.0,
            },
            "summary": summary,
            "results": results,
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(f"V19 Audit complete. Wrote {output_json}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
