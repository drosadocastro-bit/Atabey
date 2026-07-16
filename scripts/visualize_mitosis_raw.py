import sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.io.geff_reader import read_geff_graph

def main():
    try:
        sample_id = "6bba_cdcfe533"
        train_dir = project_root / "train"
        geff_path = train_dir / f"{sample_id}.geff"
        zarr_path = train_dir / f"{sample_id}.zarr"
        
        gt_graph = read_geff_graph(geff_path)
        nodes_by_id = {n.node_id: n for n in gt_graph.nodes}
        zarr_array = open_competition_array(zarr_path)
        
        # Specific division nodes to inspect
        target_nodes = [29000464, 49000935, 53001039, 87002049]
        
        # Output directory in artifacts scratch
        # Ensure it exists
        out_dir = Path(r"C:\Users\draku\.gemini\antigravity\brain\4865a6e4-8e8c-4ecf-a05b-1b964c756bba\scratch")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Predecessors map
        from collections import defaultdict
        in_edges = defaultdict(list)
        for s, t in gt_graph.edges:
            in_edges[t].append(s)

        for div_id in target_nodes:
            div_node = nodes_by_id[div_id]
            
            # Get T-0 (the division node itself) and T-1 (its immediate predecessor)
            history = [div_node]
            preds = in_edges.get(div_node.node_id, [])
            if preds:
                history.append(nodes_by_id[preds[0]])
            
            # Sort so we have [T-1, T-0]
            history.sort(key=lambda n: n.t)
            
            fig, axes = plt.subplots(2, 2, figsize=(8, 8))
            fig.suptitle(f"Mitosis Precursor: Node {div_id}")
            
            for idx, node in enumerate(history):
                t, z, y, x = node.t, node.z, node.y, node.x
                vol = read_timepoint(zarr_array, t)
                
                rz, ry, rx = 7, 15, 15  # slightly larger crop for visual context
                z_min, z_max = max(0, z - rz), min(vol.shape[0], z + rz + 1)
                y_min, y_max = max(0, y - ry), min(vol.shape[1], y + ry + 1)
                x_min, x_max = max(0, x - rx), min(vol.shape[2], x + rx + 1)
                
                crop = vol[z_min:z_max, y_min:y_max, x_min:x_max]
                
                # MIP in XY (projecting across Z axis)
                mip_xy = np.max(crop, axis=0)
                # MIP in XZ (projecting across Y axis)
                mip_xz = np.max(crop, axis=1)
                
                # Label
                label = f"T-0 (T={t})" if node.node_id == div_id else f"T-1 (T={t})"
                
                ax_xy = axes[idx, 0]
                ax_xz = axes[idx, 1]
                
                ax_xy.imshow(mip_xy, cmap="inferno", origin="lower")
                ax_xy.set_title(f"{label} XY")
                ax_xy.axis('off')
                
                ax_xz.imshow(mip_xz, cmap="inferno", origin="lower")
                ax_xz.set_title(f"{label} XZ")
                ax_xz.axis('off')
                
            plt.tight_layout()
            save_path = out_dir / f"mitosis_raw_mip_{div_id}.png"
            plt.savefig(save_path, dpi=150)
            plt.close(fig)
            print(f"Saved {save_path}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
