import argparse
import sys
import os
import torch
import numpy as np
from pathlib import Path
from tqdm import tqdm

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.experiments.cnn_advisor import SimplePeakCNN, detect_cnn_peaks
from atabey.evaluation.agreement_maps import compute_multi_source_agreement
from atabey.detection.baseline import robust_normalize, threshold_local_maxima_cfar_sidelobe

from atabey.constants import DEFAULT_VOXEL_SCALE_UM

def main():
    parser = argparse.ArgumentParser(description="V20 Agreement Ablation Shadow Mode")
    parser.add_argument("--max-samples", type=int, default=8, help="Max samples to run")
    parser.add_argument("--max-timepoints", type=int, default=1, help="Max timepoints per sample")
    args = parser.parse_args()

    # Get sample paths
    train_dir = project_root / "train"
    if not train_dir.exists():
        print(f"Warning: {train_dir} not found.")
        sys.exit(0)
        
    zarr_files = list(train_dir.glob("*.zarr"))[:args.max_samples]
    print(f"Found {len(zarr_files)} samples for ablation.")
    
    # Initialize un-trained CNN for pipeline check
    model = SimplePeakCNN(in_channels=1, base_filters=16)
    
    weights_path = project_root / "weights" / "v20_cnn_best.pth"
    if weights_path.exists():
        print(f"Loading full-trained weights from {weights_path}...")
        model.load_state_dict(torch.load(weights_path))
    else:
        print("Running with ZERO-SHOT UNTRAINED CNN weights...")
        
    model.eval()
    
    total_high_conf = 0
    total_flagged = 0
    total_stats = {
        'cat_a_cnn_completed_pair': 0,
        'cat_b_cnn_joined_existing': 0,
        'cnn_isolated_flagged': 0,
        'original_adapt_cfar_only': 0
    }

    for zarr_path in zarr_files:
        print(f"Processing {zarr_path.name}...")
        array = open_competition_array(zarr_path)
        
        for t in range(min(args.max_timepoints, array.shape[0])):
            vol_np = read_timepoint(array, t)
            
            # 1. CNN Advisor (Source 1)
            vol_float = np.asarray(vol_np, dtype=np.float32)
            vol_mean, vol_std = vol_float.mean(), vol_float.std()
            if vol_std > 0:
                vol_float = (vol_float - vol_mean) / vol_std
            vol_tensor = torch.from_numpy(vol_float).unsqueeze(0).unsqueeze(0)
            cnn_peaks = detect_cnn_peaks(model, vol_tensor, threshold=0.5)
            # Convert to physical coordinates
            cnn_points_um = [DEFAULT_VOXEL_SCALE_UM.voxel_to_um(z, y, x) for z, y, x in cnn_peaks]
            
            # 2. CFAR Watershed (Source 2) - Minimal extraction
            vol_norm = robust_normalize(vol_np)
            cfar_detections = threshold_local_maxima_cfar_sidelobe(
                sample_id=zarr_path.stem, t=t, volume=vol_norm, threshold=0.50, cfar_k_sigma=1.1, min_distance_voxels=(1, 5, 5)
            )
            # threshold_local_maxima_cfar_sidelobe returns list of Detection objects.
            cfar_points_um = [DEFAULT_VOXEL_SCALE_UM.voxel_to_um(d.z, d.y, d.x) for d in cfar_detections]
            
            # 3. Adaptive Baseline (Source 3) - Minimal local maxima
            from atabey.detection.baseline import threshold_local_maxima
            adaptive_detections = threshold_local_maxima(
                sample_id=zarr_path.stem, t=t, volume=vol_norm, threshold=0.65, min_distance_voxels=(1, 5, 5)
            )
            adaptive_points_um = [DEFAULT_VOXEL_SCALE_UM.voxel_to_um(d.z, d.y, d.x) for d in adaptive_detections]
            
            # 4. Multi-Source Agreement
            high_conf, flagged, stats = compute_multi_source_agreement(
                adaptive_points_um, cfar_points_um, cnn_points_um, matching_radius_um=7.0, min_agreement=2
            )
            
            total_high_conf += len(high_conf)
            total_flagged += len(flagged)
            for k in total_stats:
                total_stats[k] += stats[k]
            
            print(f" t={t}: {len(high_conf)} high-confidence, {len(flagged)} flagged. "
                  f"(CNN: {len(cnn_points_um)}, CFAR: {len(cfar_points_um)}, Adapt: {len(adaptive_points_um)})")
            
    print("\n--- Ablation Summary ---")
    print(f"Total High Confidence (2-of-3): {total_high_conf}")
    print(f"Total Flagged (<2 sources): {total_flagged}")
    print("\n--- Detailed Breakdown of CNN Contribution ---")
    print(f"Category A (CNN completed a pair): {total_stats['cat_a_cnn_completed_pair']}")
    print(f"Category B (CNN joined existing 2-of-3): {total_stats['cat_b_cnn_joined_existing']}")
    print(f"CNN Isolated (Flagged as hallucination): {total_stats['cnn_isolated_flagged']}")
    print(f"Original Adapt+CFAR only: {total_stats['original_adapt_cfar_only']}")
    print("Pipeline validation complete.")

if __name__ == "__main__":
    main()
