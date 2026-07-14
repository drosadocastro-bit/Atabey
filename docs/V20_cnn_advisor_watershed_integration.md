# V20: CNN-Advisor Integration on Watershed Backbone

## Objective

Build V20 as a new experimental branch on top of V19's validated watershed-refined CFAR backbone (public score 0.515, confirmed GO). The goal is to integrate the paused CNN-advisor work, informed by two new ideas inspired by Kaggle discussions:
1. **Sparse-Annotation-Aware Peak-Detection Loss**: A custom loss function that only penalizes errors around annotated centers and treats unannotated background with a zero-loss mask, directly addressing the sparsity of ground truth annotations.
2. **Multi-Source Agreement Mapping**: Using a 2-out-of-3 agreement consensus (Adaptive Baseline, Watershed CFAR, CNN-Advisor) as a high-confidence signal, without requiring any new external compute dependencies (e.g., optical flow ensembles).

## Hypothesis

By restricting a CNN to act only as an advisor (rather than a sole dictator of tracks) and training it with a loss function explicitly designed for sparse annotations, we can triangulate predictions to increase recall on dim/dense regions without triggering massive false positive explosions.

## Methodology

### 1. Hardware and Implementation Envelope
- **Hardware**: Local CPU-only training (AMD Ryzen 7000, 32GB RAM).
- **Constraints**: No Colab or external GPU compute. Memory footprint, batch size, and preprocessing must be sized to fit within 32GB RAM.

### 2. SparsePeakLoss
- A custom PyTorch local-softmax loss function that evaluates cross-entropy or MSE only in a defined neighborhood around known ground-truth centers.
- **Neighborhood Size**: Asymmetric $5 \times 3 \times 3$ (Z, Y, X) to account for voxel anisotropy (Z=1.625µm vs Y/X=0.40625µm).
- **Background Handling**: Non-annotated voxels contribute exactly 0.0 to the loss gradient.

### 3. Multi-Source Agreement
- Three signal sources:
  1. `v9_style_adaptive` (local maxima + motion_mutual)
  2. `hybrid_cfar_sidelobe` with watershed refinement
  3. CNN-Advisor predicted peaks
- **Consensus Threshold**: "High confidence" requires 2-out-of-3 sources to agree within a matching radius (e.g., 7.0µm). This leaves a margin for one source to miss without discarding the signal.

## Validation Gates

1. **Memory Pre-Check**: Ensure a single forward pass fits safely within the 32GB RAM ceiling before committing to a full bounded training loop.
2. **Bounded Smoke Test**: Confirm that the `SparsePeakLoss` converges on a 1-2 sample slice without collapsing to zero instantly.
3. **Agreement Ablation**: Measure the proportion of nodes categorized as high-confidence vs flagged-for-review against the V19 CFAR cohort.

## Go/No-Go Criteria
- **GO**: The CNN-advisor successfully triangulates with CFAR and the baseline to provide a reliable 2-of-3 consensus that improves validation metric scores beyond V19 levels without blowing up the timepoint prediction budget.
- **NO-GO**: The model collapses due to sparsity, or the 2-of-3 consensus merely duplicates CFAR errors without adding orthogonal signal.
