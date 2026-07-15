import sys
from pathlib import Path
import numpy as np
project_root = Path(__file__).resolve().parent

sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from run_hybrid_train_evaluation import _build_hybrid_graph
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints_motion_mutual, link_adjacent_timepoints_bipartite

def test_bipartite_dense():
    sample_id = "44b6_c50204e0"
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
    
    div_parent = gt_divisions[0]
    parent_t = gt_nodes_by_id[div_parent].t
    
    print(f"Testing Division {div_parent} at t={parent_t}")
    
    # We only need to run CFAR up to parent_t + 1!
    print("Building CFAR graph...")
    pred_graph, _, _, _, _, _ = _build_hybrid_graph(
        sample_path=sample_path,
        max_timepoints=parent_t + 2,
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
    
    gt_parent_pos = np.array(gt_nodes_by_id[div_parent].position_um)
    prev_positions = np.array([p.position_um for p in previous])
    best_parent_idx = np.argmin(np.linalg.norm(prev_positions - gt_parent_pos, axis=1))
    cfar_parent = previous[best_parent_idx]
    
    print(f"CFAR Parent Candidate: {cfar_parent.node_id} at {cfar_parent.position_um}")
    
    dummy_pred = {n.node_id: n for n in previous}
    mm_edges = link_adjacent_timepoints_motion_mutual(previous, current, 9.0, dummy_pred)
    bip_edges = link_adjacent_timepoints_bipartite(previous, current, 9.0, dummy_pred, debug=True)
    
    bip_assigned_targets = {e.target_id: e.source_id for e in bip_edges}
    bip_src_out = {}
    for e in bip_edges:
        bip_src_out.setdefault(e.source_id, []).append(e.target_id)
        
    if len(bip_src_out.get(cfar_parent.node_id, [])) >= 2:
        print(f"\nBIPARTITE SUCCESSFULLY FOUND DIVISION FOR PARENT {cfar_parent.node_id}!!!")
    else:
        print(f"\nBipartite linked parent {cfar_parent.node_id} to {len(bip_src_out.get(cfar_parent.node_id, []))} targets.")
        
    print(f"Total bipartite divisions in frame: {len([s for s, t in bip_src_out.items() if len(t) >= 2])}")

    # Zero-perturbation check
    mm_sources = {e.source_id for e in mm_edges}
    bip_sources = {e.source_id for e in bip_edges}
    divisions = [s for s, t in bip_src_out.items() if len(t) >= 2]
    
    perturbations = 0
    for edge in mm_edges:
        if edge.source_id not in divisions:
            # Check if this exact edge exists in bip_edges
            found = any(e.source_id == edge.source_id and e.target_id == edge.target_id for e in bip_edges)
            if not found:
                perturbations += 1
                
    print(f"\nZero-perturbation check: {perturbations} non-division edges were perturbed.")
    if perturbations == 0:
        print("SUCCESS: Non-division edges are byte-identical to motion_mutual.")
    else:
        print("FAILURE: Bipartite solver modified standard edges.")

if __name__ == "__main__":
    test_bipartite_dense()
