import time
from pathlib import Path
import numpy as np
from scipy import ndimage
from skimage.segmentation import watershed
from collections import defaultdict

from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS, DEFAULT_GUARDRAIL_SETTINGS
from scripts.run_hybrid_submission import build_graph_cfar_sidelobe
from atabey.detection.baseline import robust_normalize
from atabey.io.zarr_reader import open_competition_array, read_timepoint

def main():
    train_dir = Path("train")
    sample_ids = ["44b6_0113de3b", "44b6_0b24845f", "44b6_0c582fdc", "6bba_05b6850b", "6bba_05db0fb1"]
    
    total_time = 0.0
    total_timepoints = 0
    total_peaks = 0
    total_unrefined = 0
    
    print("Running Watershed Runtime Ablation...")
    
    for sample_id in sample_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        profile, settings = choose_settings_for_sample(sample_path)
        array = open_competition_array(sample_path)
        
        if _should_use_cfar_route(profile=profile, adaptive_detector=settings.detector, cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy):
            print(f"Precomputing {sample_id} CFAR detections...")
            # We just need the graph to get the CFAR peaks.
            graph, _ = build_graph_cfar_sidelobe(
                sample_path=sample_path,
                threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
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
                guardrail_spike_multiplier=DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier,
                guardrail_min_history=DEFAULT_GUARDRAIL_SETTINGS.min_history,
                guardrail_history_window=DEFAULT_GUARDRAIL_SETTINGS.history_window,
                guardrail_min_absolute_count=DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count,
                guardrail_fallback_threshold=DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold,
                guardrail_fallback_max_detections=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
                link_strategy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
                max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
                max_timepoints=10, # Just run 10 timepoints per sample to get a robust average per timepoint
            )
            
            dets_by_t = defaultdict(list)
            for d in graph.detections:
                dets_by_t[d.t].append(d)
                
            for t, t_dets in dets_by_t.items():
                volume = read_timepoint(array, t)
                
                # Time the watershed step!
                start_time = time.perf_counter()
                
                # 1. Global threshold
                norm_vol = robust_normalize(volume)
                global_mask = norm_vol >= 0.65
                
                # 2. Markers
                markers = np.zeros_like(global_mask, dtype=np.int32)
                for i, d in enumerate(t_dets, start=1):
                    z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
                    z, y, x = min(z, global_mask.shape[0]-1), min(y, global_mask.shape[1]-1), min(x, global_mask.shape[2]-1)
                    z, y, x = max(z, 0), max(y, 0), max(x, 0)
                    markers[z, y, x] = i
                    
                # 3. Watershed (using inverted intensity as basin)
                # Watershed on the masked region only
                labeled_cells = watershed(image=-norm_vol, markers=markers, mask=global_mask)
                
                # 4. Centroids
                # Using ndimage.center_of_mass on the labeled array
                # center_of_mass returns a list of tuples if we pass multiple labels
                unique_labels = np.unique(labeled_cells)
                unique_labels = unique_labels[unique_labels > 0]
                
                if len(unique_labels) > 0:
                    centroids = ndimage.center_of_mass(global_mask, labeled_cells, unique_labels)
                
                # Count unrefined (peaks that didn't fall into the global mask, so their label is 0)
                unrefined_t = 0
                for i, d in enumerate(t_dets, start=1):
                    z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
                    z, y, x = min(z, global_mask.shape[0]-1), min(y, global_mask.shape[1]-1), min(x, global_mask.shape[2]-1)
                    z, y, x = max(z, 0), max(y, 0), max(x, 0)
                    if labeled_cells[z, y, x] == 0:
                        unrefined_t += 1
                        
                end_time = time.perf_counter()
                
                total_time += (end_time - start_time)
                total_timepoints += 1
                total_peaks += len(t_dets)
                total_unrefined += unrefined_t
                
    if total_timepoints > 0:
        avg_time_per_tp = total_time / total_timepoints
        print(f"\n--- Watershed Runtime Estimates ---")
        print(f"Avg time per timepoint: {avg_time_per_tp:.4f} seconds")
        print(f"Total CFAR peaks in ablation: {total_peaks}")
        print(f"Total peaks unrefined (kept as-is): {total_unrefined} ({(total_unrefined/total_peaks)*100:.1f}%)")
        print(f"Extrapolated cost per 100-timepoint sample: {avg_time_per_tp * 100:.2f} seconds")
        print(f"Extrapolated cost across 66 CFAR samples: {(avg_time_per_tp * 100 * 66) / 60:.2f} minutes")

if __name__ == "__main__":
    main()
