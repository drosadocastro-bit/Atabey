# V19 CFAR Watershed Centroid Refinement — Formal GO

**Status:** GO / Validated / Merge Approved  
**Branch:** `v19_cfar_centroid_shift`  
**Feature Flag:** `--enable-watershed-refinement`

## 1. The Narrative Arc: From Hypothesis to Validation

### The Starting Hypothesis
During the initial preview audit, we observed a massive -4.36µm downward Z-shift in the CFAR detections. Our working hypothesis was that there was a uniform structural downward bias inherent in the raw CFAR intensity peaks across the entire dataset.

### The Reframing
A full-cohort analysis over all 66 CFAR samples proved the initial hypothesis incorrect. The global Z-offset distribution for CFAR was perfectly symmetrical, with a median of 0.000µm. The original -4.36µm measurement was an illusion caused by severe **Sample Selection Bias** (the preview inadvertently drew two extreme outlier samples). The core issue was not a *directional* bias, but rather high *variance* in local sub-voxel localization within dense clusters. 

### Failed Intermediate Approaches
Before arriving at the final solution, two alternative mechanisms were tested and falsified:
1.  **Local Bounding-Box Center of Mass:** Truncated large biological cells. Applying a fixed 3x3x3 or 5x3x3 window around a CFAR peak failed because cells vary significantly in size, causing the fixed boundary to snip off portions of the true cell body and skewing the centroid.
2.  **Global Blob Centroid (ndimage.label):** Dangerously over-merged the dataset. Using a global binary mask (e.g. >= 0.65) and taking the center of mass for each blob resulted in single centroids being assigned to up to 284 closely packed cells, destroying sparse recall.

### The Final Approach
We decoupled the detection and localization layers using a **Marker-Based Watershed**:
1.  Use the raw CFAR peaks strictly as topological *markers*.
2.  Use the global `norm_vol >= 0.65` mask strictly as the *basin boundary*.
3.  Execute watershed segmentation to force the blob to divide geometrically around the CFAR markers.
4.  Snap each CFAR coordinate to the unweighted geometric centroid of its designated sub-region. 
5.  If a CFAR peak falls outside the global mask (dim cells), preserve its coordinate exactly as-is.

### Validated Results
Tested strictly via an A/B evaluation against the frozen V13 Baseline across all 66 CFAR-routed samples:
*   **Quality Score:** 0.7558 (+0.0255 gain)
*   **Distribution:** 57 Improved, 2 Flat, 7 Regressed
*   **Node Recall:** 79.74% (+2.78% gain)
*   **Edge Recall:** 71.42% (+2.32% gain)
*   **Runtime Overhead:** ~25 seconds of deterministic CPU time per sample (for the `skimage.watershed` segment). *Note: The earlier claim that the solver became algorithmically faster was an unverified hypothesis and has been formally retracted; our profiling proved the graph solver retains identical efficiency, and aggregate runtime drops were purely due to Zarr disk I/O caching jitter.*

## 2. Regression Tail Analysis
The 7 samples that regressed all shared one common characteristic: **Hyper-Density**. 
*   Six of the seven were from the notoriously dense `44b6_` cohort.
*   Four of the samples had a `median_largest_component_voxels` between 350,000 and 588,000 voxels, meaning the global mask was almost entirely one contiguous block. 
*   The regressions themselves were very shallow (the worst was -0.024, most were < -0.01) relative to the cohort average gain of +0.0308. 

**Full Circle Resolution:** Sample `44b6_0c582fdc` — the exact sample whose performance originally collapsed in V14, triggering this entire diagnostic chain — was successfully rescued. Under the V19 Watershed algorithm, it gained an incredible **+0.1038**, cleanly separating its historically merged dense clusters.

## 3. Explicit GO Retrospective
The `v19_cfar_centroid_shift` branch has satisfied all pre-registered criteria:
- [x] **Real Metric Gain:** Proven on the evaluation target (+0.0255 Quality).
- [x] **Broad Distribution:** 57/66 samples improved, cleanly outweighing the shallow regression tail.
- [x] **Bounded Runtime:** Deterministic ~25s/sample CPU overhead, keeping the CFAR route well within Kaggle submission budgets.
- [x] **Evaluator Consistency:** Validated using the unmodified, legacy `evaluate_sparse_ground_truth` evaluator.
- [x] **Isolated Architecture:** Wrapped safely behind the `--enable-watershed-refinement` opt-in flag.

## 4. Promotion Path
This document confirms the V19 Watershed as **Validated** and approved for merge to the experimental timeline. 
*This document does NOT dictate when or if this branch becomes a new official submission tag (e.g., V20). The promotion from validated-experimental to active-submission remains a separate, explicit command decision.*
