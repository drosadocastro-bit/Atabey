import sys
from pathlib import Path
import math
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.geff_reader import read_geff_graph
from atabey.types import Detection
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints_bipartite
from atabey.constants import DEFAULT_VOXEL_SCALE_UM

def main():
    sample_id = "6bba_cdcfe533"
    train_dir = project_root / "train"
    geff_path = train_dir / f"{sample_id}.geff"
    
    gt_graph = read_geff_graph(geff_path)
    nodes_by_id = {int(n.node_id): n for n in gt_graph.nodes}
    
    # Convert GT nodes into Detections
    def to_det(node):
        return Detection(
            node_id=str(node.node_id),
            sample_id=sample_id,
            t=node.t,
            z=node.z, y=node.y, x=node.x,
            z_um=node.z * DEFAULT_VOXEL_SCALE_UM.z,
            y_um=node.y * DEFAULT_VOXEL_SCALE_UM.y,
            x_um=node.x * DEFAULT_VOXEL_SCALE_UM.x,
            intensity_mean=1.0,
            intensity_max=1.0
        )
    
    # Calculate exact distances
    def dist(d1, d2):
        return math.sqrt((d1.z_um - d2.z_um)**2 + (d1.y_um - d2.y_um)**2 + (d1.x_um - d2.x_um)**2)
    
    target_nodes = [29000464, 49000935, 53001039, 87002049]
    
    for parent_id in target_nodes:
        if parent_id not in nodes_by_id:
            print(f"Parent {parent_id} not found in GT graph!")
            continue
            
        parent_node = nodes_by_id[parent_id]
        
        # Find daughters in GT
        daughters = []
        for source_id, target_id in gt_graph.edges:
            if int(source_id) == parent_id:
                daughters.append(nodes_by_id[int(target_id)])
                
        print(f"\n=========================================")
        print(f"Parent {parent_id}: T={parent_node.t} Z={parent_node.z} Y={parent_node.y} X={parent_node.x}")
        for d in daughters:
            print(f"Daughter {d.node_id}: T={d.t} Z={d.z} Y={d.y} X={d.x}")
            
        if len(daughters) != 2:
            print("Expected 2 daughters, found", len(daughters))
            continue
            
        parent_det = to_det(parent_node)
        d1_det = to_det(daughters[0])
        d2_det = to_det(daughters[1])
        
        dist1 = dist(parent_det, d1_det)
        dist2 = dist(parent_det, d2_det)
        dist_d1_d2 = dist(d1_det, d2_det)
        
        # Kinematics (Raw)
        v1_raw = np.array([d1_det.z_um, d1_det.y_um, d1_det.x_um]) - np.array([parent_det.z_um, parent_det.y_um, parent_det.x_um])
        v2_raw = np.array([d2_det.z_um, d2_det.y_um, d2_det.x_um]) - np.array([parent_det.z_um, parent_det.y_um, parent_det.x_um])
        
        norm_v1_raw = np.linalg.norm(v1_raw)
        norm_v2_raw = np.linalg.norm(v2_raw)
        if norm_v1_raw < 1e-6 or norm_v2_raw < 1e-6:
            print("One of the raw daughter vectors has 0 length!")
            continue
            
        cos_theta_raw = np.dot(v1_raw, v2_raw) / (norm_v1_raw * norm_v2_raw)
        angle_raw = math.degrees(math.acos(np.clip(cos_theta_raw, -1.0, 1.0)))
        
        ratio_raw = max(norm_v1_raw, norm_v2_raw) / max(min(norm_v1_raw, norm_v2_raw), 1e-6)
        
        print(f"\n--- RAW KINEMATICS ---")
        print(f"Angle: {angle_raw:.2f} degrees (cos = {cos_theta_raw:.3f})")
        print(f"Distance ratio: {ratio_raw:.2f}")
        
        # Multi-frame Divergence Check
        def get_descendant_at(node_id, target_t):
            current = nodes_by_id[node_id]
            while current.t < target_t:
                next_nodes = [nodes_by_id[int(tgt)] for src, tgt in gt_graph.edges if int(src) == current.node_id]
                if not next_nodes:
                    return None
                current = next_nodes[0] # assume no divisions immediately after
            return current

        print(f"\n--- MULTI-FRAME DIVERGENCE ---")
        base_t = parent_node.t
        d1_nodes = [nodes_by_id[int(daughters[0].node_id)]]
        d2_nodes = [nodes_by_id[int(daughters[1].node_id)]]
        
        for offset in [2, 3]:
            if d1_nodes[-1] is None or d2_nodes[-1] is None:
                d1_nodes.append(None)
                d2_nodes.append(None)
                continue
            d1_next = get_descendant_at(d1_nodes[-1].node_id, base_t + offset)
            d2_next = get_descendant_at(d2_nodes[-1].node_id, base_t + offset)
            d1_nodes.append(d1_next)
            d2_nodes.append(d2_next)
            
        separations = []
        for i, (n1, n2) in enumerate(zip(d1_nodes, d2_nodes)):
            t = base_t + 1 + i
            if n1 is None or n2 is None:
                print(f"T={t}: One or both daughters track ended.")
                separations.append(None)
                continue
                
            det1 = to_det(n1)
            det2 = to_det(n2)
            sep = dist(det1, det2)
            separations.append(sep)
            print(f"T={t} Separation: {sep:.2f} um")
            
        # Check if strictly diverging
        valid_seps = [s for s in separations if s is not None]
        if len(valid_seps) >= 2:
            is_diverging = all(valid_seps[i+1] > valid_seps[i] for i in range(len(valid_seps)-1))
            print(f"Sustained Divergence? {'YES' if is_diverging else 'NO'}")
        else:
            print("Not enough frames to check divergence.")
    
    # Run bipartite solver with debug=True
    print("\n--- Running Bipartite Solver (Debug=True) ---")
    edges = link_adjacent_timepoints_bipartite(
        previous=previous,
        current=current,
        max_link_distance_um=9.0,
        predecessor_by_node_id={},
        debug=True,
    )
    
    print("\n--- Edges Produced ---")
    for edge in edges:
        print(f"Edge: {edge.source_id} -> {edge.target_id} (conf={edge.confidence:.2f}, rel={edge.relation})")

if __name__ == "__main__":
    main()
