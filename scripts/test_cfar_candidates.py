import sys
from pathlib import Path
import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from run_hybrid_train_evaluation import _build_hybrid_graph
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS

def test_cfar_candidates():
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
    
    print(f"Found {len(gt_divisions)} divisions in GT.")
    for gt_div in gt_divisions:
        t = gt_nodes_by_id[gt_div].t
        print(f"GT Division at parent node {gt_div} at t={t}")
        
    print("Building CFAR graph to inspect detections...")
    # Build graph with cfar_link_strategy="motion_mutual"
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
        
    for gt_div in gt_divisions:
        parent = gt_nodes_by_id[gt_div]
        daughters = [gt_nodes_by_id[tgt] for tgt in gt_edges_out[gt_div]]
        
        print(f"\n--- Investigating Division {gt_div} at t={parent.t} ---")
        print(f"Parent Pos: {parent.position_um}")
        for i, d in enumerate(daughters):
            print(f"GT Daughter {i+1} Pos: {d.position_um}")
            
        t_next = daughters[0].t
        candidates = pred_nodes_by_t.get(t_next, [])
        
        # Check how many CFAR candidates are near the parent
        parent_pos = np.array(parent.position_um)
        cand_positions = np.array([c.position_um for c in candidates])
        
        if len(cand_positions) > 0:
            dists = np.linalg.norm(cand_positions - parent_pos, axis=1)
            nearby = dists < 10.0
            nearby_dists = dists[nearby]
            print(f"CFAR found {len(nearby_dists)} candidates within 10um of parent at t={t_next}")
            for d in nearby_dists:
                print(f"  Candidate at dist {d:.2f} um")
                
test_cfar_candidates()
