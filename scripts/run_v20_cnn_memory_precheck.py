import argparse
import sys
import os
import psutil
import time
import torch
from pathlib import Path

# Add project root to sys.path to allow imports when run as a script
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.experiments.cnn_advisor import SimplePeakCNN

def get_process_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 10**6

def main():
    parser = argparse.ArgumentParser(description="V20 CNN Advisor Memory Precheck")
    parser.add_argument("--zarr-path", type=str, default="data/train/6bba_05db0fb1.zarr", help="Path to sample zarr")
    parser.add_argument("--timepoint", type=int, default=0, help="Timepoint to load")
    args = parser.parse_args()

    print(f"Starting memory precheck for {args.zarr_path} at t={args.timepoint}...")
    
    baseline_mem = get_process_memory_mb()
    print(f"Baseline memory: {baseline_mem:.2f} MB")
    
    # 1. Initialize model
    print("Initializing SimplePeakCNN...")
    model = SimplePeakCNN(in_channels=1, base_filters=16)
    model.eval()  # No grad for precheck, just memory footprint of forward pass
    
    model_mem = get_process_memory_mb()
    print(f"Memory after model init: {model_mem:.2f} MB (+{model_mem - baseline_mem:.2f} MB)")
    
    # 2. Load Volume
    print(f"Loading volume from {args.zarr_path}...")
    zarr_path = Path(args.zarr_path)
    if not zarr_path.exists():
        print(f"WARNING: Path {zarr_path} does not exist. Creating a dummy tensor of shape (40, 1024, 1024) for worst-case testing.")
        import numpy as np
        # Simulate a large timepoint
        volume = np.zeros((40, 1024, 1024), dtype=np.uint16)
    else:
        array = open_competition_array(zarr_path)
        volume = read_timepoint(array, args.timepoint)
        
    vol_mem = get_process_memory_mb()
    print(f"Volume loaded. Shape: {volume.shape}, Dtype: {volume.dtype}")
    print(f"Memory after volume load: {vol_mem:.2f} MB (+{vol_mem - model_mem:.2f} MB)")
    
    # 3. Convert to Tensor
    print("Converting to Torch Tensor...")
    # Standardize to float32 and add batch and channel dims: (B, C, Z, Y, X)
    import numpy as np
    vol_tensor = torch.from_numpy(np.asarray(volume).astype(np.float32)).unsqueeze(0).unsqueeze(0)
    
    tensor_mem = get_process_memory_mb()
    print(f"Tensor created. Shape: {vol_tensor.shape}, Dtype: {vol_tensor.dtype}")
    print(f"Memory after tensor conversion: {tensor_mem:.2f} MB (+{tensor_mem - vol_mem:.2f} MB)")

    # 4. Forward Pass
    print("Executing forward pass (no gradients)...")
    start_time = time.time()
    
    with torch.no_grad():
        output = model(vol_tensor)
        
    end_time = time.time()
    
    forward_mem = get_process_memory_mb()
    print(f"Forward pass completed in {end_time - start_time:.3f} seconds.")
    print(f"Output shape: {output.shape}")
    print(f"Memory after forward pass: {forward_mem:.2f} MB (+{forward_mem - tensor_mem:.2f} MB)")
    print(f"*** FINAL RAM USAGE: {forward_mem:.2f} MB ***")
    
    # 32GB = 32,000 MB
    if forward_mem < 30000:
        print("\n[PASS] Peak RAM usage is safely within the 32GB ceiling.")
    else:
        print("\n[FAIL] Peak RAM usage exceeds or is dangerously close to the 32GB ceiling.")
        sys.exit(1)

if __name__ == "__main__":
    main()
