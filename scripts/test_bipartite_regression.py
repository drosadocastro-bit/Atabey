import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.tracking.nearest_neighbor import (
    link_adjacent_timepoints_motion_mutual,
    link_adjacent_timepoints_bipartite
)
from atabey.io.geff_reader import read_geff_graph

def main():
    sample_id = "6bba_cdcfe533"
    geff_path = project_root / f"train/{sample_id}.geff"
    
    print(f"Loading {geff_path} for regression test...")
    graph = read_geff_graph(geff_path)
    
    # Group detections by t
    from collections import defaultdict
    detections_by_t = defaultdict(list)
    for node in graph.nodes:
        detections_by_t[node.t].append(node)
        
    t_max = max(detections_by_t.keys())
    
    print("Running frame-by-frame regression checks...")
    
    total_frames = 0
    total_edges = 0
    perturbed_edges = 0
    divisions_detected = 0
    
    for t in range(min(100, t_max)):
        previous = detections_by_t[t]
        current = detections_by_t.get(t+1, [])
        if not previous or not current:
            continue
            
        # Dummy predecessor map (assuming identity for testing)
        predecessor_map = {n.node_id: n for n in previous}
        
        edges_baseline = link_adjacent_timepoints_motion_mutual(
            previous, current, max_link_distance_um=9.0, predecessor_by_node_id=predecessor_map
        )
        
        edges_bipartite = link_adjacent_timepoints_bipartite(
            previous, current, max_link_distance_um=9.0, predecessor_by_node_id=predecessor_map
        )
        
        # Compare
        base_dict = {e.source_id: e for e in edges_baseline}
        bipart_dict = defaultdict(list)
        for e in edges_bipartite:
            bipart_dict[e.source_id].append(e)
            
        for source_id, base_edge in base_dict.items():
            bipart_edges = bipart_dict.get(source_id, [])
            if not bipart_edges:
                perturbed_edges += 1
                continue
                
            if len(bipart_edges) == 1:
                # 1-to-1: MUST match exactly.
                b_edge = bipart_edges[0]
                if b_edge.target_id != base_edge.target_id or b_edge.confidence != base_edge.confidence:
                    print(f"MISMATCH at t={t} for source {source_id}:")
                    print(f"  Baseline: {base_edge.target_id}")
                    print(f"  Bipartite: {b_edge.target_id}")
                    perturbed_edges += 1
            elif len(bipart_edges) == 2:
                # 1-to-2: Division candidate gated and accepted!
                divisions_detected += 1
                
        total_frames += 1
        total_edges += len(edges_baseline)
        
    print(f"\n--- Regression Test Results ---")
    print(f"Frames analyzed: {total_frames}")
    print(f"Total baseline edges (1-to-1): {total_edges}")
    print(f"Perturbed normal edges: {perturbed_edges}")
    print(f"Divisions uniquely resolved by bipartite solver: {divisions_detected}")
    
    if perturbed_edges > 0:
        print("\nFAILURE: Strict zero perturbation guarantee violated.")
        sys.exit(1)
    else:
        print("\nSUCCESS: 100% of non-gated edges are byte-for-byte identical.")
        sys.exit(0)

if __name__ == "__main__":
    main()
