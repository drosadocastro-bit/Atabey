# Parallel Evaluation Strategy for Atabey

## Context
The local evaluation logic (`run_hybrid_train_evaluation.py` and ablation scripts) was originally written as a sequential `for sample_id in sample_ids:` loop. Because the watershed refinement step is CPU-bound (relying heavily on `scikit-image` and `scipy` for 3D topological processing), a single sample takes approximately 10-15 minutes to evaluate across all three pipeline variants (V13, V19, V20). Running the full 66-sample sparse ground-truth cohort sequentially required upwards of 15 hours.

## Multiprocessing Implementation
To fully utilize the 44-core host VMs associated with Colab TPU instances (v6e-1), the evaluation loop has been refactored into an embarrassingly parallel fan-out using Python's native `concurrent.futures.ProcessPoolExecutor`.

**Key changes:**
1. **Stateless Workers**: The evaluation logic per sample was abstracted into a top-level function (`_evaluate_single_sample`). Because samples share no state and evaluate entirely independently, they can be distributed flawlessly across a `ProcessPoolExecutor`.
2. **Memory Bounding**: Each worker loads only its target sample lazily from the Zarr store. Memory profiling confirmed that a single worker footprint peaks at roughly 350-400 MB.
3. **Thread Limitation**: To prevent thread contention between the host OS multiprocessing and internal numerical threads (e.g., NumPy/PyTorch), `torch.set_num_threads(1)` is enforced within the parallel script to restrict internal thread thrashing. 

## Memory Verification
A 4-worker, 4-sample test (`44b6_0c582fdc`, `44b6_24264f12`, `44b6_267148e4`, `6bba_05db0fb1`) verified the memory bounds:
- 1 main process (~270 MB)
- 4 worker processes (~350-400 MB each)
- **Total footprint**: ~1.7 GB

When scaled up to ~36 workers on a Colab host VM, the total memory footprint is projected to peak around **15 GB**, which is well within the typical 100+ GB available on TPU host nodes.

## Running Parallel Audits
A dedicated parallel script now exists for executing the Division Jaccard bounding audit:
```bash
# To run the default representative 10-sample subset with 8 workers
python scripts/run_parallel_division_audit.py --workers 8

# To run a custom subset
python scripts/run_parallel_division_audit.py --workers 4 --sample-ids 44b6_0c582fdc 44b6_24264f12 

# To run the full dataset
python scripts/run_parallel_division_audit.py --workers 36 --sample-ids all
```

## Runtime Improvements
- **Sequential**: ~15 hours for 66 samples.
- **Colab Parallel (35 workers)**: Evaluates ~35 samples simultaneously. The entire 66-sample cohort requires roughly 2 execution waves. Total wall-clock time drops from **15 hours to ~30 minutes**. 
