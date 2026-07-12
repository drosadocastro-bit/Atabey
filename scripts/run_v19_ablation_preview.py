import json
from pathlib import Path
import numpy as np

import atabey.evaluation.sparse_ground_truth_v19_experimental as exp
from atabey.io.geff_reader import read_geff_graph
from scripts.run_hybrid_submission import build_graph_cfar_sidelobe
from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS
from scripts.run_v19_category_a_localization_bias import evaluate_category_a_bias

def run_ablation(name: str, sidelobe_floor_ratio: float, cfar_guard_radius_voxels: tuple[int, int, int]):
    train_dir = Path("train")
    sample_ids = ["44b6_0113de3b", "44b6_0b24845f", "44b6_0c582fdc", "6bba_05b6850b", "6bba_05db0fb1"]
    
    all_offsets = []
    
    for sample_id in sample_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")
        profile, settings = choose_settings_for_sample(sample_path)
        
        if _should_use_cfar_route(profile=profile, adaptive_detector=settings.detector, cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy):
            graph, _ = build_graph_cfar_sidelobe(
                sample_path=sample_path,
                threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
                cfar_training_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels,
                cfar_guard_radius_voxels=cfar_guard_radius_voxels,
                cfar_threshold_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode,
                cfar_k_sigma=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
                cfar_pfa=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
                sidelobe_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
                sidelobe_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels,
                sidelobe_axial_z_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
                sidelobe_axial_xy_tolerance_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels,
                sidelobe_floor_ratio=sidelobe_floor_ratio,
                max_detections_per_timepoint=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
                guardrail_spike_multiplier=DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier,
                guardrail_min_history=DEFAULT_GUARDRAIL_SETTINGS.min_history,
                guardrail_history_window=DEFAULT_GUARDRAIL_SETTINGS.history_window,
                guardrail_min_absolute_count=DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count,
                guardrail_fallback_threshold=DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold,
                guardrail_fallback_max_detections=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
                link_strategy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
                max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
                max_timepoints=100,
            )
            offsets = evaluate_category_a_bias(graph, ground_truth)
            all_offsets.extend(offsets)
            
    if not all_offsets:
        print(f"\n--- {name} ---")
        print("No Category A edges found.")
        return
        
    all_offsets = np.array(all_offsets)
    mean_offset = np.mean(all_offsets, axis=0)
    std_offset = np.std(all_offsets, axis=0)
    median_offset = np.median(all_offsets, axis=0)
    
    print(f"\n--- {name} ---")
    print(f"Total Nodes Analyzed: {len(all_offsets)}")
    print(f"Mean Offset (Z, Y, X) [um]: {mean_offset}")
    print(f"Median Offset (Z, Y, X) [um]: {median_offset}")
    print(f"Std Dev (Z, Y, X) [um]: {std_offset}")


def main():
    print("Starting CFAR Ablation Preview")
    print("Baseline reference (Sidelobe ON, Guard Z=0): Mean Z-Offset ~ -4.36 um")
    
    # Ablation 1: Sidelobe OFF, Guard Z=0
    run_ablation(
        name="Ablation 1: Sidelobe OFF (sidelobe_floor=0.0), Guard=(0,1,1)",
        sidelobe_floor_ratio=0.0,
        cfar_guard_radius_voxels=(0, 1, 1)
    )
    
    # Ablation 2: Sidelobe OFF, Guard Z=1
    run_ablation(
        name="Ablation 2: Sidelobe OFF (sidelobe_floor=0.0), Guard=(1,1,1)",
        sidelobe_floor_ratio=0.0,
        cfar_guard_radius_voxels=(1, 1, 1)
    )

if __name__ == "__main__":
    main()
