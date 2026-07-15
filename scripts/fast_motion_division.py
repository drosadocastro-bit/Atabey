import sys
from pathlib import Path
from collections import defaultdict
import numpy as np

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.zarr_reader import open_competition_array
from atabey.io.geff_reader import read_geff_graph
from run_hybrid_train_evaluation import _build_hybrid_graph
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth

def main():
    sample_id = "6bba_cdcfe533"
    train_dir = project_root / "train"
    sample_path = train_dir / f"{sample_id}.zarr"
    geff_path = train_dir / f"{sample_id}.geff"
    
    ground_truth = read_geff_graph(geff_path)
    max_timepoints = 100
    
    print(f"Building hybrid graph with motion_division for {sample_id}...", flush=True)
    
    # We only care about the linker output
    graph, _, _, _, _, _ = _build_hybrid_graph(
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
        cfar_link_strategy="motion_division", # FORCED
        cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
        cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        enable_watershed_refinement=True
    )
    
    rep = evaluate_sparse_ground_truth(graph, ground_truth)
    print(f"\nAudit Results with motion_division:")
    print(f"  TP: {rep.division_tp}")
    print(f"  FP: {rep.division_fp}")
    print(f"  FN: {rep.division_fn}")
    print(f"  Jaccard: {rep.division_jaccard}")
    
    # Get predicted division nodes directly
    out_edges = defaultdict(list)
    for edge in graph.edges():
        out_edges[edge.source_id].append(edge.target_id)
        
    predicted_divisions = [s for s, targets in out_edges.items() if len(targets) >= 2]
    print(f"  Total Predicted Division Sources: {len(predicted_divisions)}")
    print(f"  Predicted Division Source IDs: {predicted_divisions}")
    
if __name__ == "__main__":
    main()
