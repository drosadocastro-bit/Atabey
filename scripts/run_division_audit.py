import sys
from pathlib import Path
import json
import time

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS

# Import the builders
from run_hybrid_train_evaluation import _build_v9_style_graph, _build_hybrid_graph
from run_v20_quality_score_ablation import _build_v20_graph

def main():
    train_dir = project_root / "train"
    
    # Representative subset (10 samples covering dense and typical cases)
    sample_ids = [
        "44b6_0c582fdc", # Dry run standard
        "44b6_24264f12", # Dense
        "44b6_267148e4", # Dense (OOM trigger)
        "6bba_05db0fb1",
        "44b6_40c45f5a",
        "6bba_283bf9f1",
        "44b6_0b24845f",
        "44b6_144b256d",
        "44b6_81c256f0",
        "6bba_a5e926bb"
    ]
    
    max_timepoints = 100
    
    # Store aggregated totals per route
    # route -> {"tp": 0, "fp": 0, "fn": 0}
    totals = {
        "V13 (Adaptive Baseline)": {"tp": 0, "fp": 0, "fn": 0, "nodes": 0},
        "V19 (CFAR Sidelobe)": {"tp": 0, "fp": 0, "fn": 0, "nodes": 0},
        "V20 (CNN Firewall)": {"tp": 0, "fp": 0, "fn": 0, "nodes": 0},
    }
    
    for sample_id in sample_ids:
        print(f"--- Evaluating Sample: {sample_id} ---")
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")
        
        # 1. V13
        graph_v13, _, _, _, _, _ = _build_v9_style_graph(sample_path, max_timepoints)
        rep_v13 = evaluate_sparse_ground_truth(graph_v13, ground_truth)
        totals["V13 (Adaptive Baseline)"]["tp"] += rep_v13.division_tp
        totals["V13 (Adaptive Baseline)"]["fp"] += rep_v13.division_fp
        totals["V13 (Adaptive Baseline)"]["fn"] += rep_v13.division_fn
        totals["V13 (Adaptive Baseline)"]["nodes"] += rep_v13.predicted_nodes
        
        # 2. V19
        graph_v19, _, _, _, _, _ = _build_hybrid_graph(
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
            cfar_link_strategy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
            cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
            cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
            enable_watershed_refinement=True
        )
        rep_v19 = evaluate_sparse_ground_truth(graph_v19, ground_truth)
        totals["V19 (CFAR Sidelobe)"]["tp"] += rep_v19.division_tp
        totals["V19 (CFAR Sidelobe)"]["fp"] += rep_v19.division_fp
        totals["V19 (CFAR Sidelobe)"]["fn"] += rep_v19.division_fn
        totals["V19 (CFAR Sidelobe)"]["nodes"] += rep_v19.predicted_nodes
        
        # 3. V20
        graph_v20, _, _, _, _, _ = _build_v20_graph(
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
            cfar_link_strategy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
            cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
            cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
            enable_watershed_refinement=True,
            cnn_weights_path=Path("weights/v20_cnn_best.pth")
        )
        rep_v20 = evaluate_sparse_ground_truth(graph_v20, ground_truth)
        totals["V20 (CNN Firewall)"]["tp"] += rep_v20.division_tp
        totals["V20 (CNN Firewall)"]["fp"] += rep_v20.division_fp
        totals["V20 (CNN Firewall)"]["fn"] += rep_v20.division_fn
        totals["V20 (CNN Firewall)"]["nodes"] += rep_v20.predicted_nodes
        
        print(f"  V13: J={rep_v13.division_jaccard} (TP:{rep_v13.division_tp} FP:{rep_v13.division_fp} FN:{rep_v13.division_fn})")
        print(f"  V19: J={rep_v19.division_jaccard} (TP:{rep_v19.division_tp} FP:{rep_v19.division_fp} FN:{rep_v19.division_fn})")
        print(f"  V20: J={rep_v20.division_jaccard} (TP:{rep_v20.division_tp} FP:{rep_v20.division_fp} FN:{rep_v20.division_fn})")

    print("\n--- Summary (10 Samples) ---")
    for route, metrics in totals.items():
        tp = metrics["tp"]
        fp = metrics["fp"]
        fn = metrics["fn"]
        jaccard = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
        print(f"{route}:")
        print(f"  Division Jaccard: {jaccard:.4f}")
        print(f"  TP: {tp}, FP: {fp}, FN: {fn}")
        print(f"  Total Predicted Nodes: {metrics['nodes']}")

if __name__ == '__main__':
    main()
