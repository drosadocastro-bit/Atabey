import os
import sys
import time
import math
import argparse
from pathlib import Path

import torch
import numpy as np

# Adjust path to include src
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.experiments.cnn_advisor import SimplePeakCNN, SparsePeakLoss, detect_cnn_peaks
from atabey.detection.baseline import threshold_local_maxima, threshold_local_maxima_cfar_sidelobe
from atabey.detection.cfar_watershed import robust_normalize
from atabey.evaluation.agreement_maps import compute_multi_source_agreement
from atabey.constants import DEFAULT_VOXEL_SCALE_UM

# 8 Fixed Validation Samples (including 44b6_0c582fdc from V14 collapse)
VALIDATION_SAMPLES = [
    "44b6_0c582fdc.zarr",
    "44b6_0113de3b.zarr",
    "44b6_0b24845f.zarr",
    "6bba_05db0fb1.zarr",
    "6bba_6ca87370.zarr",
    "44b6_341df25f.zarr",
    "6bba_76db78c1.zarr",
    "44b6_587a1e22.zarr"
]

def format_time(seconds):
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m {int(seconds % 60)}s"

def precompute_baselines(data_dir, max_t=1):
    print("Pre-computing CFAR and Adaptive baselines for 8 validation samples...")
    baselines = {}
    
    for sample_name in VALIDATION_SAMPLES:
        zarr_path = data_dir / sample_name
        if not zarr_path.exists():
            print(f"Warning: Validation sample {sample_name} not found.")
            continue
            
        array = open_competition_array(zarr_path)
        sample_id = zarr_path.stem
        
        sample_data = []
        for t in range(min(max_t, array.shape[0])):
            vol_np = read_timepoint(array, t)
            vol_norm = robust_normalize(vol_np)
            
            # CFAR
            cfar_dets = threshold_local_maxima_cfar_sidelobe(
                sample_id=sample_id, t=t, volume=vol_norm, threshold=0.50, cfar_k_sigma=1.1, min_distance_voxels=(1, 5, 5)
            )
            cfar_um = [DEFAULT_VOXEL_SCALE_UM.voxel_to_um(d.z, d.y, d.x) for d in cfar_dets]
            
            # Adaptive
            adapt_dets = threshold_local_maxima(
                sample_id=sample_id, t=t, volume=vol_norm, threshold=0.65, min_distance_voxels=(1, 5, 5)
            )
            adapt_um = [DEFAULT_VOXEL_SCALE_UM.voxel_to_um(d.z, d.y, d.x) for d in adapt_dets]
            
            # Prepare tensor for CNN
            vol_float = np.asarray(vol_np, dtype=np.float32)
            vol_mean, vol_std = vol_float.mean(), vol_float.std()
            if vol_std > 0:
                vol_float = (vol_float - vol_mean) / vol_std
            vol_tensor = torch.from_numpy(vol_float).unsqueeze(0).unsqueeze(0)
            
            sample_data.append({
                'vol_tensor': vol_tensor,
                'cfar_um': cfar_um,
                'adapt_um': adapt_um
            })
            
        baselines[sample_id] = sample_data
        
    print(f"Pre-computation complete for {len(baselines)} samples.")
    return baselines

def evaluate_checkpoints(model, baselines):
    model.eval()
    total_stats = {
        'cat_a_cnn_completed_pair': 0,
        'cat_b_cnn_joined_existing': 0,
        'cnn_isolated_flagged': 0,
        'original_adapt_cfar_only': 0
    }
    
    with torch.no_grad():
        for sample_id, t_data in baselines.items():
            for data in t_data:
                cnn_peaks = detect_cnn_peaks(model, data['vol_tensor'], threshold=0.5)
                cnn_um = [DEFAULT_VOXEL_SCALE_UM.voxel_to_um(z, y, x) for z, y, x in cnn_peaks]
                
                _, _, stats = compute_multi_source_agreement(
                    data['adapt_um'], data['cfar_um'], cnn_um, matching_radius_um=7.0, min_agreement=2
                )
                
                for k in total_stats:
                    total_stats[k] += stats[k]
                    
    return total_stats

def main():
    parser = argparse.ArgumentParser(description="Full V20 CNN-Advisor Training with Live Evaluation")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--max_hours", type=float, default=8.0)
    parser.add_argument("--patience", type=int, default=3)
    args = parser.parse_args()

    data_dir = project_root / "train"
    weights_dir = project_root / "weights"
    weights_dir.mkdir(exist_ok=True)
    best_model_path = weights_dir / "v20_cnn_best.pth"
    
    # Pre-computation
    val_baselines = precompute_baselines(data_dir, max_t=1)
    
    # Find training samples (excluding validation)
    all_zarrs = list(data_dir.glob("*.zarr"))
    train_zarrs = [z for z in all_zarrs if z.name not in VALIDATION_SAMPLES]
    print(f"Found {len(train_zarrs)} training samples.")
    
    # Initialize Model
    device = torch.device("cpu")
    model = SimplePeakCNN(in_channels=1, base_filters=16).to(device)
    criterion = SparsePeakLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    
    # --- Pre-flight Memory Check ---
    print("\n--- Running Pre-flight Memory Check ---")
    import psutil
    process = psutil.Process()
    mem_before = process.memory_info().rss / 1024**2
    
    # Dummy forward pass on a validation sample
    dummy_tensor = list(val_baselines.values())[0][0]['vol_tensor']
    _ = model(dummy_tensor)
    
    mem_after = process.memory_info().rss / 1024**2
    print(f"Memory before dummy forward: {mem_before:.2f} MB")
    print(f"Memory after dummy forward: {mem_after:.2f} MB")
    if mem_after > 24000: # 24 GB warning
        print("[WARNING] Memory usage is dangerously high. Aborting to respect 32GB ceiling.")
        sys.exit(1)
    print("[PASS] Pre-flight memory check passed.\n")
    
    # --- Training Loop ---
    start_time = time.time()
    max_seconds = args.max_hours * 3600
    
    best_ratio = -1.0
    consecutive_no_improvement = 0
    history = []
    
    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()
        model.train()
        epoch_loss = 0.0
        batches = 0
        
        # We process one timepoint per sample to keep batches simple
        for zarr_path in train_zarrs:
            # Check time limit
            if time.time() - start_time > max_seconds:
                print(f"\n[EARLY STOP] Hit maximum time limit of {args.max_hours} hours. Stopping.")
                return
                
            sample_id = zarr_path.stem
            
            t0 = time.time()
            geff_path = data_dir / f"{sample_id}.geff"
            if not geff_path.exists():
                continue
                
            try:
                graph = read_geff_graph(geff_path)
            except Exception:
                continue
            t1 = time.time()
                
            array = open_competition_array(zarr_path)
            if array.shape[0] < 1: continue
            t2 = time.time()
            
            t = 0
            gt_centers = []
            for node in graph.nodes:
                if node.t == t:
                    gt_centers.append((0, node.z, node.y, node.x))
                
            if len(gt_centers) == 0: continue
            t3 = time.time()
            
            vol_np = read_timepoint(array, t)
            t4 = time.time()
            
            vol_float = np.asarray(vol_np, dtype=np.float32)
            vol_mean, vol_std = vol_float.mean(), vol_float.std()
            if vol_std > 0:
                vol_float = (vol_float - vol_mean) / vol_std
            t5 = time.time()
                
            vol_tensor = torch.from_numpy(vol_float).unsqueeze(0).unsqueeze(0).to(device)
            
            optimizer.zero_grad()
            logits = model(vol_tensor)
            loss = criterion(logits, gt_centers)
            t6 = time.time()
            
            loss.backward()
            optimizer.step()
            t7 = time.time()
            
            epoch_loss += loss.item()
            batches += 1
            
            if batches == 1 and epoch == 1:
                print(f"  [Timing] Batch 1: geff={t1-t0:.2f}s, array={t2-t1:.2f}s, graph={t3-t2:.2f}s, vol={t4-t3:.2f}s, norm={t5-t4:.2f}s, fwd={t6-t5:.2f}s, bwd={t7-t6:.2f}s")
            
            if batches % 10 == 0:
                print(f"  [Epoch {epoch}] Processed {batches}/{len(train_zarrs)} samples...")
            
        avg_loss = epoch_loss / max(1, batches)
        elapsed = time.time() - epoch_start
        print(f"Epoch {epoch:02d}/{args.epochs} | Loss: {avg_loss:.4f} | Time: {elapsed:.1f}s")
        
        # --- Live Checkpoint Tracking (every 5 epochs, or epoch 1) ---
        if epoch == 1 or epoch % 5 == 0:
            print(f"\n--- Checkpoint Evaluation (Epoch {epoch}) ---")
            stats = evaluate_checkpoints(model, val_baselines)
            
            cat_a = stats['cat_a_cnn_completed_pair']
            cat_b = stats['cat_b_cnn_joined_existing']
            halls = stats['cnn_isolated_flagged']
            
            print(f"Category A (Net New Resolution): {cat_a}")
            print(f"Category B (Joined Existing):    {cat_b}")
            print(f"Hallucinations (Isolated):       {halls}")
            current_ratio = cat_a / (halls + 1)
            print(f"Ratio (Cat A / (Halls+1)):       {current_ratio:.3f}")
            print("-------------------------------------------\n")
            
            history.append({
                'epoch': epoch,
                'cat_a': cat_a,
                'cat_b': cat_b,
                'hallucinations': halls,
                'ratio': current_ratio
            })
            
            # Save best model
            if current_ratio > best_ratio:
                best_ratio = current_ratio
                torch.save(model.state_dict(), best_model_path)
                print(f"[*] New best model saved (Ratio: {current_ratio:.3f})")
                consecutive_no_improvement = 0
            else:
                consecutive_no_improvement += 1
                
            # Trend-based Early Stopping Rule:
            if consecutive_no_improvement >= 3:
                print(f"\n[EARLY STOP] Ratio hasn't improved for 3 checkpoints. Stopping early to prevent overfitting.")
                break
                
            if len(history) >= 2:
                prev_halls = history[-2]['hallucinations']
                prev_cata = history[-2]['cat_a']
                if halls > prev_halls * 2 and cat_a <= prev_cata * 1.1:
                    print(f"\n[EARLY STOP] Hallucinations doubled ({prev_halls}->{halls}) without meaningful Category A growth ({prev_cata}->{cat_a}). Stopping early.")
                    break
                    
        # Explicitly save per-epoch checkpoint
        epoch_model_path = weights_dir / f"v20_cnn_epoch_{epoch}.pth"
        torch.save(model.state_dict(), epoch_model_path)

    print(f"\nTraining completed. Best model saved to {best_model_path}")

if __name__ == "__main__":
    main()
