import sys
from pathlib import Path
import json
import time
import multiprocessing
import concurrent.futures

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS

# Import the builders
from run_hybrid_train_evaluation import _build_v9_style_graph, _build_hybrid_graph
from run_v20_quality_score_ablation import _build_v20_graph


def _evaluate_single_sample(sample_id: str, cfar_link_strategy: str, max_timepoints: int) -> dict:
    print(f"--- Evaluating Sample: {sample_id} ---", flush=True)
    train_dir = project_root / "train"
    sample_path = train_dir / f"{sample_id}.zarr"
    ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")

    results = {}

    # 1. V13
    graph_v13, _, detector_v13, link_v13, _, _ = _build_v9_style_graph(sample_path, max_timepoints)
    rep_v13 = evaluate_sparse_ground_truth(graph_v13, ground_truth)
    results["V13"] = {
        "tp": rep_v13.division_tp,
        "fp": rep_v13.division_fp,
        "fn": rep_v13.division_fn,
        "nodes": rep_v13.predicted_nodes,
        "jaccard": rep_v13.division_jaccard,
        "edge_recall": rep_v13.sparse_edge_recall,
        "detector": detector_v13,
        "link_strategy": link_v13,
    }

    # 2. V19
    graph_v19, _, detector_v19, link_v19, _, _ = _build_hybrid_graph(
        sample_path=sample_path,
        max_timepoints=max_timepoints,
        cfar_threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
        cfar_training_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels,
        cfar_threshold_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode,
        cfar_k_sigma=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
        cfar_pfa=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
        sidelobe_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
        sidelobe_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
        max_detections_per_timepoint=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
        cfar_link_strategy=cfar_link_strategy,
        cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
        cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        enable_watershed_refinement=True,
    )
    rep_v19 = evaluate_sparse_ground_truth(graph_v19, ground_truth)
    results["V19"] = {
        "tp": rep_v19.division_tp,
        "fp": rep_v19.division_fp,
        "fn": rep_v19.division_fn,
        "nodes": rep_v19.predicted_nodes,
        "jaccard": rep_v19.division_jaccard,
        "edge_recall": rep_v19.sparse_edge_recall,
        "detector": detector_v19,
        "link_strategy": link_v19,
    }

    # 3. V20 (with CNN Advisor + Firewall)
    graph_v20, _, detector_v20, link_v20, _, _ = _build_v20_graph(
        sample_path=sample_path,
        max_timepoints=max_timepoints,
        cfar_threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
        cfar_training_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels,
        cfar_threshold_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode,
        cfar_k_sigma=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
        cfar_pfa=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
        sidelobe_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
        sidelobe_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
        max_detections_per_timepoint=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
        cfar_link_strategy=cfar_link_strategy,
        cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
        cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        cnn_weights_path=project_root / "weights" / "v20_cnn_best.pth",
    )
    rep_v20 = evaluate_sparse_ground_truth(graph_v20, ground_truth)

    v20_label = "V20 (Bipartite)" if cfar_link_strategy == "bipartite" else "V20"
    results[v20_label] = {
        "tp": rep_v20.division_tp,
        "fp": rep_v20.division_fp,
        "fn": rep_v20.division_fn,
        "nodes": rep_v20.predicted_nodes,
        "jaccard": rep_v20.division_jaccard,
        "edge_recall": rep_v20.sparse_edge_recall,
        "detector": detector_v20,
        "link_strategy": link_v20,
    }

    print(f"[{sample_id}] Finished.", flush=True)
    return sample_id, results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run parallel division audit")
    parser.add_argument("--workers", type=int, default=8, help="Number of worker processes")
    parser.add_argument("--sample-ids", nargs="+", default=["bounded"], help="Samples to run")
    parser.add_argument("--cfar-link-strategy", type=str, default="motion_mutual", help="Linking strategy for CFAR watershed")
    parser.add_argument("--max-timepoints", type=int, default=100, help="Maximum timepoints per sample")
    args = parser.parse_args()

    if args.sample_ids == ["bounded"]:
        sample_ids = [
            "44b6_0c582fdc", "44b6_24264f12", "44b6_267148e4", "6bba_05db0fb1",
            "44b6_40c45f5a", "6bba_283bf9f1", "44b6_0b24845f", "44b6_144b256d",
            "44b6_81c256f0", "6bba_a5e926bb"
        ]
    elif args.sample_ids == ["all"]:
        sample_ids = [p.stem for p in (project_root / "train").glob("*.zarr")]
    else:
        sample_ids = args.sample_ids

    print(
        f"Starting parallel evaluation across {len(sample_ids)} samples using {args.workers} workers "
        f"and max_timepoints={args.max_timepoints}...",
        flush=True,
    )

    v20_label = "V20 (Bipartite)" if args.cfar_link_strategy == "bipartite" else "V20"

    totals = {
        "V13": {"tp": 0, "fp": 0, "fn": 0, "nodes": 0, "actual_routes": {}},
        "V19": {"tp": 0, "fp": 0, "fn": 0, "nodes": 0, "actual_routes": {}},
        v20_label: {"tp": 0, "fp": 0, "fn": 0, "nodes": 0, "actual_routes": {}},
    }

    start_time = time.time()

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_evaluate_single_sample, s_id, args.cfar_link_strategy, args.max_timepoints): s_id
            for s_id in sample_ids
        }

        for future in concurrent.futures.as_completed(futures):
            sample_id, results = future.result()

            for version, metrics in results.items():
                totals[version]["tp"] += metrics["tp"]
                totals[version]["fp"] += metrics["fp"]
                totals[version]["fn"] += metrics["fn"]
                totals[version]["nodes"] += metrics["nodes"]
                route_key = f"{metrics.get('detector')}|{metrics.get('link_strategy')}"
                routes = totals[version]["actual_routes"]
                routes[route_key] = routes.get(route_key, 0) + 1
                # For Edge Recall, let's just average them
                if metrics["edge_recall"] is not None:
                    if "edge_recall_sum" not in totals[version]:
                        totals[version]["edge_recall_sum"] = 0.0
                        totals[version]["edge_recall_count"] = 0
                    totals[version]["edge_recall_sum"] += metrics["edge_recall"]
                    totals[version]["edge_recall_count"] += 1

            print(f"--- Results for {sample_id} ---", flush=True)
            for version, metrics in results.items():
                print(
                    f"  {version}: detector={metrics.get('detector')} link={metrics.get('link_strategy')} "
                    f"DivJ={metrics['jaccard']} (TP:{metrics['tp']} FP:{metrics['fp']} FN:{metrics['fn']}) "
                    f"| EdgeRecall={metrics['edge_recall']}",
                    flush=True,
                )

    end_time = time.time()
    print(f"\n--- Parallel Summary ({len(sample_ids)} Samples) ---", flush=True)
    print(f"Elapsed Time: {end_time - start_time:.2f} seconds", flush=True)
    for route in ["V13", "V19", v20_label]:
        metrics = totals[route]
        tp = metrics["tp"]
        fp = metrics["fp"]
        fn = metrics["fn"]
        jaccard = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0

        avg_edge_recall = (metrics.get("edge_recall_sum", 0.0) / metrics.get("edge_recall_count", 1)) if metrics.get("edge_recall_count", 0) > 0 else 0.0

        print(f"{route}:", flush=True)
        print(f"  Division Jaccard: {jaccard:.4f}", flush=True)
        print(f"  Average Edge Recall: {avg_edge_recall:.4f}", flush=True)
        print(f"  TP: {tp}, FP: {fp}, FN: {fn}", flush=True)
        print(f"  Total Predicted Nodes: {metrics['nodes']}", flush=True)
        print(f"  Actual detector/link counts: {metrics['actual_routes']}", flush=True)


if __name__ == '__main__':
    # Ensure torch doesn't try to use all CPU cores within each worker,
    # as we are parallelizing at the process level
    import torch
    torch.set_num_threads(1)

    multiprocessing.set_start_method("spawn")
    main()
