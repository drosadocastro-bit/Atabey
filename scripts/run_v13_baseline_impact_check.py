import sys
from pathlib import Path
import json
from dataclasses import asdict

# Patch the evaluation module *before* run_hybrid_train_evaluation imports it
import atabey.evaluation.sparse_ground_truth
import atabey.evaluation.sparse_ground_truth_v19_experimental as exp

atabey.evaluation.sparse_ground_truth.match_sparse_centroids = exp.match_sparse_centroids_global_greedy
atabey.evaluation.sparse_ground_truth.evaluate_sparse_ground_truth = exp.evaluate_sparse_ground_truth

from scripts.run_hybrid_train_evaluation import run_train_evaluation
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS

def main():
    train_dir = Path("train")
    geff_files = list(train_dir.glob("*.geff"))
    sample_ids = [f.stem for f in geff_files]

    print(f"Running V13 Baseline Impact Check on {len(sample_ids)} samples...")

    # Run with V13 frozen defaults (including max_timepoints=100)
    records = run_train_evaluation(
        train_dir=train_dir,
        sample_ids=sample_ids,
        output_json=Path("submissions/v13_baseline_impact_check.json"),
        output_summary_json=Path("submissions/v13_baseline_impact_check_summary.json"),
        max_timepoints=100,
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
        track_quality_shadow=True,
        track_quality_beacon_threshold=0.75,
        track_quality_min_track_length=3,
        latent_shadow=False,
        latent_shadow_window_frames=DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_window_frames,
        latent_shadow_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_max_link_distance_um,
        mitosis_shadow=False,
        mitosis_shadow_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_distance_um,
        mitosis_shadow_intensity_tolerance=DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_intensity_tolerance,
    )

if __name__ == "__main__":
    main()
