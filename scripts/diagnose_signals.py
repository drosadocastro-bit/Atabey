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

def angle_between(v1, v2):
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cos_t = np.dot(v1, v2) / (n1 * n2)
    return math.degrees(math.acos(np.clip(cos_t, -1.0, 1.0)))

def run_known_cases():
    print("\n================ KNOWN REAL DIVISIONS ================")
    sample_id = "6bba_cdcfe533"
    geff_path = project_root / "train" / f"{sample_id}.geff"
    gt_graph = read_geff_graph(geff_path)
    nodes_by_id = {int(n.node_id): n for n in gt_graph.nodes}
    
    target_nodes = [29000464, 49000935, 53001039, 87002049]
    
    def to_det(node):
        return Detection(
            node_id=str(node.node_id), sample_id=sample_id, t=node.t,
            z=node.z, y=node.y, x=node.x,
            z_um=node.z * DEFAULT_VOXEL_SCALE_UM.z,
            y_um=node.y * DEFAULT_VOXEL_SCALE_UM.y,
            x_um=node.x * DEFAULT_VOXEL_SCALE_UM.x
        )
        
    for parent_id in target_nodes:
        if parent_id not in nodes_by_id:
            continue
        p_node = nodes_by_id[parent_id]
        daughters = [nodes_by_id[int(tgt)] for src, tgt in gt_graph.edges if int(src) == parent_id]
        if len(daughters) != 2:
            continue
            
        def get_descendant_at(node_id, target_t):
            current = nodes_by_id[node_id]
            while current.t < target_t:
                next_nodes = [nodes_by_id[int(tgt)] for src, tgt in gt_graph.edges if int(src) == current.node_id]
                if not next_nodes:
                    return None
                current = next_nodes[0]
            return current
            
        d1_nodes = [nodes_by_id[int(daughters[0].node_id)]]
        d2_nodes = [nodes_by_id[int(daughters[1].node_id)]]
        for offset in [2, 3]:
            if d1_nodes[-1] is None or d2_nodes[-1] is None:
                d1_nodes.append(None)
                d2_nodes.append(None)
                continue
            d1_nodes.append(get_descendant_at(d1_nodes[-1].node_id, p_node.t + offset))
            d2_nodes.append(get_descendant_at(d2_nodes[-1].node_id, p_node.t + offset))
            
        print(f"\n--- True Parent {parent_id} ---")
        axes = []
        for i, (n1, n2) in enumerate(zip(d1_nodes, d2_nodes)):
            if n1 and n2:
                v = np.array(to_det(n1).position_um) - np.array(to_det(n2).position_um)
                axes.append(v)
                
        if len(axes) >= 2:
            angles = []
            for i in range(len(axes)-1):
                ang = angle_between(axes[i], axes[i+1])
                # Vectors could be flipped depending on order, so we take min of ang and 180-ang
                ang = min(ang, 180.0 - ang)
                angles.append(ang)
            max_drift = max(angles)
            print(f"Directional Drift (Max angle change): {max_drift:.2f} degrees")
        else:
            print("Directional Drift: Not enough frames.")
            
        array = open_competition_array(project_root / "train" / f"{sample_id}.zarr")
        int_P = array[p_node.t][int(p_node.z), int(p_node.y), int(p_node.x)]
        d1 = daughters[0]
        d2 = daughters[1]
        int_D1 = array[d1.t][int(d1.z), int(d1.y), int(d1.x)]
        int_D2 = array[d2.t][int(d2.z), int(d2.y), int(d2.x)]
        print(f"Intensity: Parent={int_P}, D1={int_D1}, D2={int_D2}, SumD={int_D1+int_D2}")

def run_noise_cases():
    print("\n================ SURVIVING NOISE CANDIDATES ================")
    sample_id = "44b6_c50204e0"
    array = open_competition_array(project_root / "train" / f"{sample_id}.zarr")
    
    prev_dets = threshold_local_maxima(sample_id, 68, array[68], threshold=0.65, min_distance_voxels=(1,5,5))
    curr_dets = threshold_local_maxima(sample_id, 69, array[69], threshold=0.65, min_distance_voxels=(1,5,5))
    next_dets = threshold_local_maxima(sample_id, 70, array[70], threshold=0.65, min_distance_voxels=(1,5,5))
    next_next_dets = threshold_local_maxima(sample_id, 71, array[71], threshold=0.65, min_distance_voxels=(1,5,5))
    
    edges = link_adjacent_timepoints_bipartite(
        prev_dets, curr_dets, 
        max_link_distance_um=9.0, 
        predecessor_by_node_id={}, 
        divergence_angle_max_cos=1.0, daughter_distance_ratio=10.0
    )
    
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

    drift_angles = []
    
    for edge in [e for e in edges if e.relation == "division"]:
        s_det = next(d for d in prev_dets if d.node_id == edge.source_id)
        primary_id = next((e.target_id for e in edges if e.source_id == edge.source_id and e.target_id != edge.target_id), None)
        if not primary_id: continue
        
        t1_det = next(d for d in curr_dets if d.node_id == primary_id)
        t2_det = next(d for d in curr_dets if d.node_id == edge.target_id)
        
        # Loose Geometry
        v1 = np.array(t1_det.position_um) - np.array(s_det.position_um)
        v2 = np.array(t2_det.position_um) - np.array(s_det.position_um)
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < 1e-6 or n2 < 1e-6: continue
        ang = angle_between(v1, v2)
        rat = max(n1, n2) / min(n1, n2)
        if not (ang > 60.0 and rat < 4.0): continue
        
        # Multi-frame Tracking
        t1_70 = get_closest(t1_det.position_um, next_dets)
        t2_70 = get_closest(t2_det.position_um, next_dets)
        if not t1_70 or not t2_70: continue
        
        t1_71 = get_closest(t1_70.position_um, next_next_dets)
        t2_71 = get_closest(t2_70.position_um, next_next_dets)
        if not t1_71 or not t2_71: continue
        
        s69 = np.linalg.norm(np.array(t1_det.position_um) - np.array(t2_det.position_um))
        s70 = np.linalg.norm(np.array(t1_70.position_um) - np.array(t2_70.position_um))
        s71 = np.linalg.norm(np.array(t1_71.position_um) - np.array(t2_71.position_um))
        
        if s71 > s70 > s69:
            # THIS IS A SURVIVOR NOISE CANDIDATE!
            ax69 = np.array(t1_det.position_um) - np.array(t2_det.position_um)
            ax70 = np.array(t1_70.position_um) - np.array(t2_70.position_um)
            ax71 = np.array(t1_71.position_um) - np.array(t2_71.position_um)
            
            a1 = min(angle_between(ax69, ax70), 180.0 - angle_between(ax69, ax70))
            a2 = min(angle_between(ax70, ax71), 180.0 - angle_between(ax70, ax71))
            drift = max(a1, a2)
            drift_angles.append(drift)
            
            v_sep_1 = s70 - s69
            v_sep_2 = s71 - s70
            
            # Print intensities
            int_P = s_det.intensity_max
            int_D1 = t1_det.intensity_max
            int_D2 = t2_det.intensity_max
            print(f"Noise Pair {edge.source_id[:6]} -> {t1_det.node_id[:6]} & {t2_det.node_id[:6]}")
            print(f"  Directional Drift: {drift:.2f} degrees")
            print(f"  Separation Speeds: Step 1 = {v_sep_1:.2f} um/fr, Step 2 = {v_sep_2:.2f} um/fr")

    print(f"\nStats for {len(drift_angles)} surviving noise cases:")
    if drift_angles:
        print(f"Mean Directional Drift: {np.mean(drift_angles):.2f} degrees")
        print(f"Min Drift: {np.min(drift_angles):.2f}, Max Drift: {np.max(drift_angles):.2f}")

if __name__ == "__main__":
    run_known_cases()
    run_noise_cases()
