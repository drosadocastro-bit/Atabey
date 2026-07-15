import sys
from pathlib import Path
import math
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.zarr_reader import open_competition_array
from atabey.io.geff_reader import read_geff_graph
from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.types import Detection
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints_bipartite
from atabey.detection.baseline import threshold_local_maxima

def main():
    sample_id = "44b6_c50204e0"
    train_dir = project_root / "train"
    zarr_path = train_dir / f"{sample_id}.zarr"
    
    array = open_competition_array(zarr_path)
    
    # Run detection on T=68 and T=69
    print("Detecting at T=68...")
    prev_vol = array[68]
    prev_dets = threshold_local_maxima(sample_id, 68, prev_vol, threshold=0.65, min_distance_voxels=(1,5,5))
    
    print("Detecting at T=69...")
    curr_vol = array[69]
    curr_dets = threshold_local_maxima(sample_id, 69, curr_vol, threshold=0.65, min_distance_voxels=(1,5,5))
    
    # Run bipartite solver WITHOUT strict geometric guardrails to find the noise
    edges = link_adjacent_timepoints_bipartite(
        prev_dets, curr_dets, 
        max_link_distance_um=9.0, 
        predecessor_by_node_id={}, 
        divergence_angle_max_cos=1.0, # no angle check
        daughter_distance_ratio=10.0, # no ratio check
    )
    
    div_edges = [e for e in edges if e.relation == "division"]
    print(f"Found {len(div_edges)} division candidates (noise)")
    
    # Test all candidates
    candidates = div_edges
    
    # To track forward, we need detections at T=70 and T=71
    print("Detecting at T=70...")
    next_vol = array[70]
    next_dets = threshold_local_maxima(sample_id, 70, next_vol, threshold=0.65, min_distance_voxels=(1,5,5))
    
    print("Detecting at T=71...")
    next_next_vol = array[71]
    next_next_dets = threshold_local_maxima(sample_id, 71, next_next_vol, threshold=0.65, min_distance_voxels=(1,5,5))
    
    def get_closest(pos_um, dets):
        pos = np.array(pos_um)
        best_det = None
        best_dist = 9.0
        for d in dets:
            dist = np.linalg.norm(np.array(d.position_um) - pos)
            if dist < best_dist:
                best_dist = dist
                best_det = d
        return best_det
        
    pass_count = 0
    fail_merged = 0
    fail_converged = 0
    fail_track_ended = 0
    
    pass_geometry_only = 0
    
    for edge in candidates:
        source_id = edge.source_id
        target_id = edge.target_id # orphan
        
        # Find the primary target
        primary_id = None
        for e in edges:
            if e.source_id == source_id and e.target_id != target_id:
                primary_id = e.target_id
                break
                
        if not primary_id:
            continue
            
        s_det = next(d for d in prev_dets if d.node_id == source_id)
        t1_det = next(d for d in curr_dets if d.node_id == primary_id)
        t2_det = next(d for d in curr_dets if d.node_id == target_id)
        
        # Loose Geometry Check
        v1 = np.array(t1_det.position_um) - np.array(s_det.position_um)
        v2 = np.array(t2_det.position_um) - np.array(s_det.position_um)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        
        passes_geometry = False
        if norm_v1 > 1e-6 and norm_v2 > 1e-6:
            cos_theta = np.dot(v1, v2) / (norm_v1 * norm_v2)
            angle = math.degrees(math.acos(np.clip(cos_theta, -1.0, 1.0)))
            ratio = max(norm_v1, norm_v2) / min(norm_v1, norm_v2)
            if angle > 60.0 and ratio < 4.0:
                passes_geometry = True
                
        if passes_geometry:
            pass_geometry_only += 1
        else:
            continue # Only track candidates that pass Pass 1
            
        # T=69 Separation
        sep_69 = np.linalg.norm(np.array(t1_det.position_um) - np.array(t2_det.position_um))
        
        # T=70 Separation
        t1_70 = get_closest(t1_det.position_um, next_dets)
        t2_70 = get_closest(t2_det.position_um, next_dets)
        if not t1_70 or not t2_70:
            fail_track_ended += 1
            continue
            
        sep_70 = np.linalg.norm(np.array(t1_70.position_um) - np.array(t2_70.position_um))
        
        # T=71 Separation
        t1_71 = get_closest(t1_70.position_um, next_next_dets)
        t2_71 = get_closest(t2_70.position_um, next_next_dets)
        if not t1_71 or not t2_71:
            fail_track_ended += 1
            continue
            
        sep_71 = np.linalg.norm(np.array(t1_71.position_um) - np.array(t2_71.position_um))
        
        is_diverging = (sep_71 > sep_70 > sep_69)
        if is_diverging:
            pass_count += 1
        elif sep_71 == 0.0 or sep_70 == 0.0:
            fail_merged += 1
        else:
            fail_converged += 1

    print(f"\n--- NOISE VALIDATION RESULTS ---")
    print(f"Total Raw Candidates: {len(candidates)}")
    print(f"Passes Pass 1 (Loose Geometry): {pass_geometry_only}")
    print(f"Passes Pass 2 (Divergence Check): {pass_count}")
    print(f"Failed Pass 2 (Merged): {fail_merged}")
    print(f"Failed Pass 2 (Converged/Stopped Diverging): {fail_converged}")
    print(f"Failed Pass 2 (Track Ended Early): {fail_track_ended}")

if __name__ == "__main__":
    main()
