import sys
from pathlib import Path
import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from run_hybrid_train_evaluation import _build_hybrid_graph
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints_motion_mutual, link_adjacent_timepoints_bipartite

def test_orphan_status():
    sample_id = "6bba_cdcfe533"
    train_dir = project_root / "train"
    sample_path = train_dir / f"{sample_id}.zarr"
    geff_path = train_dir / f"{sample_id}.geff"
    
    print("Loading Ground Truth...")
    gt_graph = read_geff_graph(geff_path)
    
    gt_edges_out = {}
    for src, tgt in gt_graph.edges:
        gt_edges_out.setdefault(src, []).append(tgt)
        
    gt_divisions = [src for src, tgts in gt_edges_out.items() if len(tgts) >= 2]
    gt_nodes_by_id = {n.node_id: n for n in gt_graph.nodes}
    
    # 53001039 is at t=52
    div_parent = 53001039
    parent_t = gt_nodes_by_id[div_parent].t
    
    print("Building CFAR graph...")
    # Build graph with cfar_link_strategy="bipartite"
    pred_graph, _, _, _, _, _ = _build_hybrid_graph(
        sample_path=sample_path,
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
        cfar_link_strategy="motion_mutual",
        cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
        cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        enable_watershed_refinement=True
    )
    
    pred_nodes_by_t = {}
    for d in pred_graph.detections:
        pred_nodes_by_t.setdefault(d.t, []).append(d)
        
    previous = pred_nodes_by_t.get(parent_t, [])
    current = pred_nodes_by_t.get(parent_t + 1, [])
    
    print(f"\nAnalyzing Frame Transition {parent_t} -> {parent_t+1}")
    
    # We need to find the CFAR candidate corresponding to the parent
    gt_parent_pos = np.array(gt_nodes_by_id[div_parent].position_um)
    prev_positions = np.array([p.position_um for p in previous])
    best_parent_idx = np.argmin(np.linalg.norm(prev_positions - gt_parent_pos, axis=1))
    cfar_parent = previous[best_parent_idx]
    
    print(f"CFAR Parent Candidate: {cfar_parent.node_id} at {cfar_parent.position_um}")
    
    # Run motion mutual
    dummy_pred = {n.node_id: n for n in previous}
    mm_edges = link_adjacent_timepoints_motion_mutual(previous, current, 9.0, dummy_pred)
    
    assigned_targets = {e.target_id: e.source_id for e in mm_edges}
    
    cfar_parent_pos = np.array(cfar_parent.position_um)
    curr_positions = np.array([c.position_um for c in current])
    dists = np.linalg.norm(curr_positions - cfar_parent_pos, axis=1)
    
    nearby_indices = np.where(dists <= 10.0)[0]
    print(f"Found {len(nearby_indices)} current candidates near CFAR Parent:")
    for idx in nearby_indices:
        cand = current[idx]
        dist = dists[idx]
        if cand.node_id in assigned_targets:
            src_id = assigned_targets[cand.node_id]
            print(f"  Candidate {cand.node_id} (dist {dist:.2f}): ASSIGNED to {src_id}")
        else:
            print(f"  Candidate {cand.node_id} (dist {dist:.2f}): ORPHAN")

    print("\nRunning Bipartite Resolver...")
    bip_edges = link_adjacent_timepoints_bipartite(previous, current, 9.0, dummy_pred)
    
    bip_assigned_targets = {e.target_id: e.source_id for e in bip_edges}
    
    for idx in nearby_indices:
        cand = current[idx]
        print(f"  Candidate {cand.node_id} Pos: {cand.position_um}")

if __name__ == "__main__":
    test_orphan_status()
