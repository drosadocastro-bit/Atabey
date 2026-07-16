import sys
from pathlib import Path
import numpy as np
from scipy.ndimage import maximum_filter, center_of_mass

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.io.geff_reader import read_geff_graph

def main():
    sample_id = "6bba_cdcfe533"
    train_dir = project_root / "train"
    geff_path = train_dir / f"{sample_id}.geff"
    zarr_path = train_dir / f"{sample_id}.zarr"
    
    gt_graph = read_geff_graph(geff_path)
    nodes_by_id = {n.node_id: n for n in gt_graph.nodes}
    zarr_array = open_competition_array(zarr_path)
    
    target_nodes = [29000464, 49000935, 53001039, 87002049]
    
    for div_id in target_nodes:
        div_node = nodes_by_id[div_id]
        t, z, y, x = div_node.t, div_node.z, div_node.y, div_node.x
        vol = read_timepoint(zarr_array, t)
        
        rz, ry, rx = 7, 15, 15
        z_min, z_max = max(0, z - rz), min(vol.shape[0], z + rz + 1)
        y_min, y_max = max(0, y - ry), min(vol.shape[1], y + ry + 1)
        x_min, x_max = max(0, x - rx), min(vol.shape[2], x + rx + 1)
        
        crop = vol[z_min:z_max, y_min:y_max, x_min:x_max]
        
        # Check for multiple bright peaks
        # Threshold at 75% of max intensity to see if it splits into two blobs
        max_val = np.max(crop)
        thresh_75 = crop > (max_val * 0.75)
        thresh_50 = crop > (max_val * 0.50)
        
        from skimage.measure import label
        labeled_75, num_features_75 = label(thresh_75, return_num=True)
        labeled_50, num_features_50 = label(thresh_50, return_num=True)
        
        print(f"Node {div_id} (T={t}): Max Intensity = {max_val}")
        print(f"  Blobs > 75% max: {num_features_75}")
        print(f"  Blobs > 50% max: {num_features_50}")

if __name__ == "__main__":
    main()
