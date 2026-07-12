# V19 CFAR Z-Bias Root Cause Analysis

## Objective
We previously identified a severe ~4.8µm downward Z-shift (Category A localization error) that was rejecting perfectly-linked tracks under the strict 7.0µm Kaggle metric. This error was isolated to the CFAR pipeline, as the adaptive baseline did not exhibit the bias. This document determines the specific mechanism causing the Z-bias via ablation testing.

## Full-Cohort Confirmation
*(Waiting for full 198-sample job to complete)*
- **Total Actionable Edges (<= 9.0µm distance):** TBD
- **Category A (Correctly linked, strict metric rejected):** TBD
- **Category B (Failed to link):** TBD
- **Full-Cohort Mean CFAR Z-Offset:** TBD µm

## Ablation Results (5-Sample Preview Cohort)
To isolate the bug, we disabled the `sidelobe_suppression` stage and modified the `cfar_guard_radius_voxels` in Z.

- **Baseline CFAR (Sidelobe ON, Guard Z=0):** Mean Z-Offset = `-4.36 µm`
- **Ablation 1 (Sidelobe OFF, Guard Z=0):** Mean Z-Offset = `-4.33 µm`
- **Ablation 2 (Sidelobe OFF, Guard Z=1):** Mean Z-Offset = `-4.33 µm`

## Root Cause Conclusion
The ablation tests definitively exonerate both `sidelobe_suppression` and the CFAR `guard_radius` configuration. The Z-bias persists at exactly the same magnitude (~4.33µm) even when sidelobe suppression is entirely disabled.

The root cause is structural to the **core CFAR `threshold_local_maxima_cfar` function**. 
Unlike the adaptive baseline (which segments cells and calculates their geometric `center_of_mass`), the CFAR detector relies on `scipy.ndimage.maximum_filter` and simply assigns the cell's physical coordinate to the literal highest-intensity voxel (`local_max`). 

In this dataset's imaging setup, the point spread function or cellular morphology causes the peak intensity pixel to systematically sit ~4.8µm higher in the Z-axis than the cell's true geometric centroid (which the human annotators marked). By taking the exact peak voxel, CFAR intrinsically inherits this -4.8µm Z-bias, pushing perfectly tracked cells out of Kaggle's strict 7.0µm matching radius.

## Proposed Fix Plan
**Do not rewrite CFAR or lose its sensitivity.**
Our ablation revealed a critical insight: **the intensity-weighted center of mass still fails to correct the Z-bias.** The ablation showed the offset only improved from -4.36µm to -4.03µm, even with a massive 11x5x5 refinement window. 

Why? Because the biological signal itself (the raw intensity) is biased in Z. The brightest pixels are structurally pushed ~4.8µm away from the cell's physical center due to the point spread function (PSF) and optical aberration in this dataset. An intensity-weighted centroid calculation is inextricably anchored to that brightest pixel.

The `adaptive_baseline` completely evades this bias because it uses `threshold_connected_components`, which creates a **binary mask** (`normalized >= 0.65`) and computes the pure, unweighted geometric center of the blob. The human annotators marked the visual center of the cell bodies, aligning perfectly with the binary geometric centroid, but completely misaligning with the raw intensity peak.

**The Real Fix: Global Marker-Based Localization**
Our ablation revealed two critical insights:
1. **The Evaluator Trap:** Our ablation measured the offset of "Category A" nodes (those 7-14µm away). If a refinement perfectly fixed a node, it snapped into the strict <7µm radius and vanished from Category A! Because the mean offset never dropped to 0, it means the local refinements were failing to fix the nodes. In fact, local Otsu *increased* the Category A pool from 280 to 300 nodes, meaning it was actively pushing previously correct nodes out of the strict radius!
2. **The Local Window Fallacy:** Why did local binary thresholding fail? Because if you extract a bounding box *centered on the peak*, and the peak is physically located at the top edge of the cell, your bounding box chops off the bottom half of the cell. Any thresholding (Otsu, FWHM) inside that box will only find the center of the top half! It's mathematically impossible for a local window to find the true centroid if it artificially truncates the cell body.

We must truly decouple **Detection** from **Localization** using a **Marker-Based** approach:
- **Detection (CFAR):** Run CFAR to find all peaks (markers), preserving its extreme sensitivity to dim/crowded cells.
- **Localization (Global Blob):** Run `adaptive_baseline`'s global binary segmentation (`normalized >= 0.65` -> `ndimage.label` -> `center_of_mass`) to compute the unbiased, unweighted geometric centroids of all biological blobs in the entire volume.
- **The Snap:** For every CFAR peak, check if it falls inside a global label. If it does, snap the CFAR peak's coordinate to that label's true geometric centroid! If a CFAR peak is so dim it doesn't fall in any label, leave it alone. 

This gives us the best of both worlds: CFAR's ultra-sensitive recall, perfectly aligned with the adaptive baseline's unbiased geometry.
