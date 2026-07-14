import argparse
import sys
import os
import torch
import torch.optim as optim
import numpy as np
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.experiments.cnn_advisor import SimplePeakCNN, SparsePeakLoss, train_cnn_advisor_smoke, get_memory_mb

def main():
    parser = argparse.ArgumentParser(description="V20 CNN Advisor Bounded Smoke Test")
    parser.add_argument("--zarr-path", type=str, default="train/6bba_05db0fb1.zarr")
    parser.add_argument("--geff-path", type=str, default="train/6bba_05db0fb1.geff")
    parser.add_argument("--timepoint", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()

    zarr_full_path = project_root / args.zarr_path
    geff_full_path = project_root / args.geff_path
    
    if not zarr_full_path.exists() or not geff_full_path.exists():
        print(f"Error: {zarr_full_path} or {geff_full_path} not found.")
        sys.exit(1)

    print(f"Loading Ground Truth from {geff_full_path}...")
    gt_graph = read_geff_graph(geff_full_path)
    
    # Filter for the specified timepoint
    nodes_t = [node for node in gt_graph.nodes if node.t == args.timepoint]
    print(f"Found {len(nodes_t)} GT centers at timepoint {args.timepoint}.")
    
    # Format for the loss function: list of tuples (batch_idx, z, y, x)
    gt_centers = [(0, int(node.z), int(node.y), int(node.x)) for node in nodes_t]
    
    print(f"Loading Volume from {zarr_full_path}...")
    array = open_competition_array(zarr_full_path)
    volume_np = read_timepoint(array, args.timepoint)
    print(f"Volume loaded. Shape: {volume_np.shape}, dtype: {volume_np.dtype}")
    
    # Preprocess: Normalize volume and convert to tensor (B, C, Z, Y, X)
    # Basic Z-score normalization for smoke test
    volume_float = np.asarray(volume_np, dtype=np.float32)
    vol_mean, vol_std = volume_float.mean(), volume_float.std()
    if vol_std > 0:
        volume_float = (volume_float - vol_mean) / vol_std
    
    volume_tensor = torch.from_numpy(volume_float).unsqueeze(0).unsqueeze(0)
    
    print("Initializing Model and Loss...")
    model = SimplePeakCNN(in_channels=1, base_filters=16)
    loss_fn = SparsePeakLoss(window_shape=(5, 3, 3))
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    
    print("Starting Bounded Training Loop...")
    loss_history = train_cnn_advisor_smoke(
        model=model,
        optimizer=optimizer,
        loss_fn=loss_fn,
        volume=volume_tensor,
        gt_centers=gt_centers,
        epochs=args.epochs
    )
    
    # Validate convergence
    if len(loss_history) > 1 and loss_history[-1] < loss_history[0]:
        print(f"\n[PASS] Loss converged from {loss_history[0]:.6f} -> {loss_history[-1]:.6f}")
        
        # Save weights for ablation
        weights_dir = project_root / "weights"
        weights_dir.mkdir(exist_ok=True)
        weights_path = weights_dir / "smoke_cnn.pth"
        torch.save(model.state_dict(), weights_path)
        print(f"Saved smoke-trained weights to {weights_path}")
        
    else:
        print(f"\n[FAIL] Loss did not converge. Start: {loss_history[0]:.6f} -> End: {loss_history[-1]:.6f}")
        sys.exit(1)

if __name__ == "__main__":
    main()
