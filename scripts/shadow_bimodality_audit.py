import sys
from pathlib import Path
import numpy as np
from collections import defaultdict
import random
from skimage.measure import label

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.io.geff_reader import read_geff_graph

def score_bimodality(crop: np.ndarray, relative_threshold: float = 0.75) -> int:
    """
    Counts the number of distinct local intensity peaks above a relative threshold
    within the candidate's voxel neighborhood.
    """
    max_val = np.max(crop)
    if max_val == 0:
        return 0
    
    thresh = crop > (max_val * relative_threshold)
    _, num_features = label(thresh, return_num=True)
    return num_features

def main():
    train_dir = project_root / "train"
    geff_files = list(train_dir.glob("*.geff"))
    
    all_divisions = []
    all_controls = []
    
    for geff_path in geff_files:
        sample_id = geff_path.stem
        zarr_path = train_dir / f"{sample_id}.zarr"
        
        if not zarr_path.exists():
            continue
            
        print(f"Processing {sample_id}...")
        gt_graph = read_geff_graph(geff_path)
        nodes_by_id = {n.node_id: n for n in gt_graph.nodes}
        
        # Find divisions
        out_edges = defaultdict(list)
        for s, t in gt_graph.edges:
            out_edges[s].append(t)
            
        division_ids = [s for s, tgts in out_edges.items() if len(tgts) >= 2]
        
        # Find non-dividing controls
        # Must exist and have out-degree == 1 (normal continuation)
        valid_controls = [s for s, tgts in out_edges.items() if len(tgts) == 1]
        
        # Balance classes
        num_divisions = len(division_ids)
        if num_divisions == 0:
            continue
            
        sampled_controls = random.sample(valid_controls, min(len(valid_controls), num_divisions * 3))
        
        zarr_array = open_competition_array(zarr_path)
        
        def process_nodes(node_ids, is_division):
            results = []
            for nid in node_ids:
                node = nodes_by_id[nid]
                t, z, y, x = node.t, node.z, node.y, node.x
                
                # Check bounds
                if t >= zarr_array.shape[0]:
                    continue
                    
                vol = read_timepoint(zarr_array, t)
                
                rz, ry, rx = 7, 15, 15
                z_min, z_max = max(0, z - rz), min(vol.shape[0], z + rz + 1)
                y_min, y_max = max(0, y - ry), min(vol.shape[1], y + ry + 1)
                x_min, x_max = max(0, x - rx), min(vol.shape[2], x + rx + 1)
                
                crop = vol[z_min:z_max, y_min:y_max, x_min:x_max]
                if crop.size == 0:
                    continue
                    
                peaks_75 = score_bimodality(crop, 0.75)
                peaks_85 = score_bimodality(crop, 0.85)
                
                results.append({
                    "sample": sample_id,
                    "node_id": nid,
                    "is_division": is_division,
                    "peaks_75": peaks_75,
                    "peaks_85": peaks_85
                })
            return results
            
        all_divisions.extend(process_nodes(division_ids, True))
        all_controls.extend(process_nodes(sampled_controls, False))

    print("\n--- Bimodality Audit Results ---")
    print(f"Total Divisions Analyzed: {len(all_divisions)}")
    print(f"Total Controls Analyzed: {len(all_controls)}")
    
    def analyze_threshold(metric_key, threshold_val, target_lobes):
        div_pass = sum(1 for d in all_divisions if d[metric_key] >= target_lobes)
        ctrl_pass = sum(1 for c in all_controls if c[metric_key] >= target_lobes)
        
        div_pass_rate = div_pass / len(all_divisions) if all_divisions else 0
        ctrl_pass_rate = ctrl_pass / len(all_controls) if all_controls else 0
        
        print(f"\nCondition: >= {target_lobes} lobes at {metric_key}")
        print(f"  Divisions meeting condition: {div_pass}/{len(all_divisions)} ({div_pass_rate:.1%})")
        print(f"  Controls meeting condition:  {ctrl_pass}/{len(all_controls)} ({ctrl_pass_rate:.1%})")
        if ctrl_pass_rate > 0:
            print(f"  Enrichment Ratio: {div_pass_rate / ctrl_pass_rate:.1f}x")
            
    analyze_threshold("peaks_75", 0.75, 2)
    analyze_threshold("peaks_85", 0.85, 2)
    
if __name__ == "__main__":
    main()
