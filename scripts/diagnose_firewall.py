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

def validate_sample(sample_id):
    print(f"\n================ VALIDATING {sample_id} ================")
    geff_path = project_root / "train" / f"{sample_id}.geff"
    gt_graph = read_geff_graph(geff_path)
    nodes_by_id = {int(n.node_id): n for n in gt_graph.nodes}
    
    # Extract ALL true divisions from GT
    true_parents = []
    children_by_parent = {}
    for src_id, tgt_id in gt_graph.edges:
        src = int(src_id)
        children_by_parent.setdefault(src, []).append(int(tgt_id))
    for src, children in children_by_parent.items():
        if len(children) == 2:
            true_parents.append(src)
            
    print(f"Found {len(true_parents)} true divisions in GT.")
    
    def to_det(node):
        return Detection(
            node_id=str(node.node_id), sample_id=sample_id, t=node.t,
            z=node.z, y=node.y, x=node.x,
            z_um=node.z * DEFAULT_VOXEL_SCALE_UM.z,
            y_um=node.y * DEFAULT_VOXEL_SCALE_UM.y,
            x_um=node.x * DEFAULT_VOXEL_SCALE_UM.x
        )
        
    def get_descendant_at(node_id, target_t):
        current = nodes_by_id[node_id]
        while current.t < target_t:
            next_nodes = [nodes_by_id[int(tgt)] for src, tgt in gt_graph.edges if int(src) == current.node_id]
            if not next_nodes:
                return None
            current = next_nodes[0]
        return current
        
    passed_true = 0
    failed_true = 0
    
    for parent_id in true_parents:
        p_node = nodes_by_id[parent_id]
        daughters = children_by_parent[parent_id]
        
        d1_nodes = [nodes_by_id[daughters[0]]]
        d2_nodes = [nodes_by_id[daughters[1]]]
        for offset in [2, 3]:
            if d1_nodes[-1] is None or d2_nodes[-1] is None:
                d1_nodes.append(None)
                d2_nodes.append(None)
                continue
            d1_nodes.append(get_descendant_at(d1_nodes[-1].node_id, p_node.t + offset))
            d2_nodes.append(get_descendant_at(d2_nodes[-1].node_id, p_node.t + offset))
            
        axes = []
        seps = []
        for i, (n1, n2) in enumerate(zip(d1_nodes, d2_nodes)):
            if n1 and n2:
                v = np.array(to_det(n1).position_um) - np.array(to_det(n2).position_um)
                axes.append(v)
                seps.append(np.linalg.norm(v))
                
        if len(axes) >= 3:
            angles = []
            for i in range(len(axes)-1):
                ang = min(angle_between(axes[i], axes[i+1]), 180.0 - angle_between(axes[i], axes[i+1]))
                angles.append(ang)
            max_drift = max(angles)
            v_sep_1 = seps[1] - seps[0]
            v_sep_2 = seps[2] - seps[1]
            
            # Refined Rule
            if max_drift < 15.0 and v_sep_1 > 1.0:
                passed_true += 1
            else:
                print(f"  [!] True Div {parent_id} FAILED Firewall:")
                print(f"      Separations: T={p_node.t+1}: {seps[0]:.2f}, T={p_node.t+2}: {seps[1]:.2f}, T={p_node.t+3}: {seps[2]:.2f}")
                print(f"      Step Speeds: Step 1 = {v_sep_1:.2f}, Step 2 = {v_sep_2:.2f}")
                print(f"      Directional Drift: {max_drift:.1f} degrees")
                failed_true += 1
        else:
            # Fallback to strict geometry
            v1 = np.array(to_det(d1_nodes[0]).position_um) - np.array(to_det(p_node).position_um)
            v2 = np.array(to_det(d2_nodes[0]).position_um) - np.array(to_det(p_node).position_um)
            ang = angle_between(v1, v2)
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 > 1e-6 and n2 > 1e-6:
                ratio = max(n1, n2) / min(n1, n2)
                if ang > 90.0 and ratio < 2.0:
                    passed_true += 1
                else:
                    print(f"  [!] True Div {parent_id} (Fallback) FAILED: ang={ang:.1f}, rat={ratio:.1f}")
                    failed_true += 1

    print(f"True Divisions: {passed_true} Passed, {failed_true} Failed")

    print(f"\n--- Testing Noise at T=50 ---")
    array = open_competition_array(project_root / "train" / f"{sample_id}.zarr")
    
    prev_dets = threshold_local_maxima(sample_id, 50, array[50], threshold=0.65, min_distance_voxels=(1,5,5))
    curr_dets = threshold_local_maxima(sample_id, 51, array[51], threshold=0.65, min_distance_voxels=(1,5,5))
    next_dets = threshold_local_maxima(sample_id, 52, array[52], threshold=0.65, min_distance_voxels=(1,5,5))
    next_next_dets = threshold_local_maxima(sample_id, 53, array[53], threshold=0.65, min_distance_voxels=(1,5,5))
    
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

    raw_noise = 0
    pass_1 = 0
    survived_firewall = 0
    
    for edge in [e for e in edges if e.relation == "division"]:
        raw_noise += 1
        s_det = next(d for d in prev_dets if d.node_id == edge.source_id)
        primary_id = next((e.target_id for e in edges if e.source_id == edge.source_id and e.target_id != edge.target_id), None)
        if not primary_id: continue
        
        t1_det = next(d for d in curr_dets if d.node_id == primary_id)
        t2_det = next(d for d in curr_dets if d.node_id == edge.target_id)
        
        # Loose Geometry (Pass 1)
        v1 = np.array(t1_det.position_um) - np.array(s_det.position_um)
        v2 = np.array(t2_det.position_um) - np.array(s_det.position_um)
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < 1e-6 or n2 < 1e-6: continue
        ang = angle_between(v1, v2)
        rat = max(n1, n2) / min(n1, n2)
        if not (ang > 60.0 and rat < 4.0): continue
        pass_1 += 1
        
        # Multi-frame Tracking
        t1_52 = get_closest(t1_det.position_um, next_dets)
        t2_52 = get_closest(t2_det.position_um, next_dets)
        if not t1_52 or not t2_52: continue
        
        t1_53 = get_closest(t1_52.position_um, next_next_dets)
        t2_53 = get_closest(t2_52.position_um, next_next_dets)
        if not t1_53 or not t2_53: continue
        
        ax1 = np.array(t1_det.position_um) - np.array(t2_det.position_um)
        ax2 = np.array(t1_52.position_um) - np.array(t2_52.position_um)
        ax3 = np.array(t1_53.position_um) - np.array(t2_53.position_um)
        
        s1 = np.linalg.norm(ax1)
        s2 = np.linalg.norm(ax2)
        s3 = np.linalg.norm(ax3)
        
        drift = max(
            min(angle_between(ax1, ax2), 180.0 - angle_between(ax1, ax2)),
            min(angle_between(ax2, ax3), 180.0 - angle_between(ax2, ax3))
        )
        
        v_sep_1 = s2 - s1
        # Refined rule: initial velocity > 1.0 and drift < 15.0
        # No strict monotonic requirement.
        
        if drift < 15.0 and v_sep_1 > 1.0:
            print(f"  [!] NOISE LEAK: {edge.source_id[:6]} -> {t1_det.node_id[:6]} & {t2_det.node_id[:6]} (drift={drift:.1f}, v_sep_1={v_sep_1:.1f})")
            survived_firewall += 1

    print(f"Noise Cascade: Raw={raw_noise} -> Pass1={pass_1} -> Firewall Surviving={survived_firewall}")

def main():
    validate_sample("44b6_808952d6")
    validate_sample("6bba_74686d6a")
    validate_sample("44b6_95029e92")

if __name__ == "__main__":
    main()
