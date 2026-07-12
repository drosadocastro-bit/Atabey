import json
from pathlib import Path
import numpy as np

import atabey.evaluation.sparse_ground_truth_v19_experimental as exp
from atabey.io.geff_reader import read_geff_graph
from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route, _build_v9_style_graph
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS
from scripts.run_v19_category_a_localization_bias import evaluate_category_a_bias

def main():
    train_dir = Path("train")
    geff_files = list(train_dir.glob("*.geff"))
    
    all_offsets = []
    samples_processed = 0
    max_samples = 5
    
    for geff_file in geff_files:
        if samples_processed >= max_samples:
            break
            
        sample_id = geff_file.stem
        # Skip known hang
        if sample_id == "6bba_6ca87370":
            continue
            
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(geff_file)
        profile, settings = choose_settings_for_sample(sample_path)
        
        # Check if it routes to adaptive
        if not _should_use_cfar_route(profile=profile, adaptive_detector=settings.detector, cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy):
            print(f"Evaluating Adaptive Baseline Sample: {sample_id}...")
            # Route is adaptive
            graph, _, _, _, _, _ = _build_v9_style_graph(sample_path, max_timepoints=100)
            
            offsets = evaluate_category_a_bias(graph, ground_truth)
            all_offsets.extend(offsets)
            samples_processed += 1
            
    if not all_offsets:
        print("No Category A edges found in adaptive samples.")
        return
        
    all_offsets = np.array(all_offsets)
    mean_offset = np.mean(all_offsets, axis=0)
    std_offset = np.std(all_offsets, axis=0)
    median_offset = np.median(all_offsets, axis=0)
    abs_mean_offset = np.mean(np.abs(all_offsets), axis=0)
    
    print("\n--- Adaptive Baseline (v9-style) Category A Localization Bias ---")
    print(f"Total Nodes Analyzed: {len(all_offsets)}")
    print(f"Mean Offset (Z, Y, X) [um]: {mean_offset}")
    print(f"Median Offset (Z, Y, X) [um]: {median_offset}")
    print(f"Std Dev (Z, Y, X) [um]: {std_offset}")
    print(f"Mean Absolute Error (Z, Y, X) [um]: {abs_mean_offset}")

if __name__ == "__main__":
    main()
