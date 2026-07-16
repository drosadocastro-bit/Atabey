import sys
from pathlib import Path
from collections import defaultdict
import numpy as np
from skimage.measure import regionprops

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint

def main():
    sample_id = "6bba_cdcfe533"
    train_dir = project_root / "train"
    geff_path = train_dir / f"{sample_id}.geff"
    zarr_path = train_dir / f"{sample_id}.zarr"
    
    # Read ground truth
    gt_graph = read_geff_graph(geff_path)
    
    # Find divisions (nodes with out-degree >= 2)
    out_edges = defaultdict(list)
    for source, target in gt_graph.edges:
        out_edges[source].append(target)
        
    division_sources = []
    for source, targets in out_edges.items():
        if len(targets) >= 2:
            division_sources.append(source)
            
    print(f"Found {len(division_sources)} ground truth divisions in {sample_id}")
    
    # Map node_id to node
    nodes_by_id = {node.node_id: node for node in gt_graph.nodes}
    
    # Open Zarr array
    zarr_array = open_competition_array(zarr_path)
    
    # To compute properties, we need a function that extracts a local crop
    # and computes basic stats.
    # A simple threshold can act as a mask for the cell.
    
    for div_id in division_sources:
        div_node = nodes_by_id[div_id]
        t_div = div_node.t
        print(f"\n--- Division Event: Node {div_id} at T={t_div} ---")
        
        # We need to trace the parent node back 2-3 frames.
        # Let's find its predecessors.
        in_edges = defaultdict(list)
        for s, t in gt_graph.edges:
            in_edges[t].append(s)
            
        current_node = div_node
        history = [current_node]
        
        # Trace back up to 3 frames
        for _ in range(3):
            preds = in_edges.get(current_node.node_id, [])
            if not preds:
                break
            current_node = nodes_by_id[preds[0]]
            history.append(current_node)
            
        # history[0] is the dividing cell (right before division)
        # history[1] is T-1 relative to division, etc.
        history.reverse() # Chronological order
        
        for node in history:
            t = node.t
            z, y, x = node.z, node.y, node.x
            
            # Load the timepoint
            vol = read_timepoint(zarr_array, t)
            
            # Crop a small window (e.g., radius 10 in xy, 5 in z)
            rz, ry, rx = 5, 10, 10
            z_min, z_max = max(0, z - rz), min(vol.shape[0], z + rz + 1)
            y_min, y_max = max(0, y - ry), min(vol.shape[1], y + ry + 1)
            x_min, x_max = max(0, x - rx), min(vol.shape[2], x + rx + 1)
            
            crop = vol[z_min:z_max, y_min:y_max, x_min:x_max]
            
            # Segment the cell (e.g., threshold > 100 or Otsu)
            from skimage.filters import threshold_otsu
            try:
                thresh = threshold_otsu(crop)
                mask = crop > thresh
            except Exception:
                mask = crop > np.mean(crop)
                
            # Compute properties
            props = regionprops(mask.astype(int), intensity_image=crop)
            if not props:
                print(f"  T={t}: No region found")
                continue
                
            # Get the largest region (presumably the cell)
            main_prop = max(props, key=lambda p: p.area)
            
            # Compute metrics
            volume = main_prop.area
            mean_intensity = main_prop.intensity_mean
            max_intensity = main_prop.intensity_max
            
            eigvals = main_prop.inertia_tensor_eigvals
            # Eigenvalues are sorted in decreasing order: e0 >= e1 >= e2
            if eigvals[0] > 0 and eigvals[2] > 0:
                elongation = np.sqrt(eigvals[0] / eigvals[2]) # Ratio of major to minor axis
            else:
                elongation = 1.0
            
            print(f"  T={t} (z={z}, y={y}, x={x}):")
            print(f"    Volume: {volume}")
            print(f"    Mean Intensity: {mean_intensity:.2f}")
            print(f"    Max Intensity: {max_intensity:.2f}")
            print(f"    Elongation: {elongation:.2f}")
            
    # --- Negative Controls ---
    import random
    random.seed(42)
    
    non_division_sources = [s for s, targets in out_edges.items() if len(targets) == 1]
    # Filter to ensure they have at least 3 predecessors
    valid_controls = []
    in_edges = defaultdict(list)
    for s, t in gt_graph.edges:
        in_edges[t].append(s)
        
    for src in non_division_sources:
        curr = src
        history_len = 1
        for _ in range(3):
            preds = in_edges.get(curr, [])
            if not preds: break
            curr = preds[0]
            history_len += 1
        if history_len == 4:
            valid_controls.append(src)
            
    selected_controls = random.sample(valid_controls, min(4, len(valid_controls)))
    
    for c_id in selected_controls:
        c_node = nodes_by_id[c_id]
        t_c = c_node.t
        print(f"\n--- Control Event (Non-dividing): Node {c_id} at T={t_c} ---")
        
        current_node = c_node
        history = [current_node]
        for _ in range(3):
            preds = in_edges.get(current_node.node_id, [])
            if not preds: break
            current_node = nodes_by_id[preds[0]]
            history.append(current_node)
            
        history.reverse()
        for node in history:
            t = node.t
            z, y, x = node.z, node.y, node.x
            vol = read_timepoint(zarr_array, t)
            
            rz, ry, rx = 5, 10, 10
            z_min, z_max = max(0, z - rz), min(vol.shape[0], z + rz + 1)
            y_min, y_max = max(0, y - ry), min(vol.shape[1], y + ry + 1)
            x_min, x_max = max(0, x - rx), min(vol.shape[2], x + rx + 1)
            
            crop = vol[z_min:z_max, y_min:y_max, x_min:x_max]
            from skimage.filters import threshold_otsu
            try:
                thresh = threshold_otsu(crop)
                mask = crop > thresh
            except Exception:
                mask = crop > np.mean(crop)
                
            props = regionprops(mask.astype(int), intensity_image=crop)
            if not props: continue
            
            main_prop = max(props, key=lambda p: p.area)
            volume = main_prop.area
            mean_intensity = main_prop.intensity_mean
            max_intensity = main_prop.intensity_max
            eigvals = main_prop.inertia_tensor_eigvals
            if eigvals[0] > 0 and eigvals[2] > 0:
                elongation = np.sqrt(eigvals[0] / eigvals[2])
            else:
                elongation = 1.0
                
            print(f"  T={t} (z={z}, y={y}, x={x}):")
            print(f"    Volume: {volume}")
            print(f"    Mean Intensity: {mean_intensity:.2f}")
            print(f"    Max Intensity: {max_intensity:.2f}")
            print(f"    Elongation: {elongation:.2f}")

if __name__ == "__main__":
    main()
