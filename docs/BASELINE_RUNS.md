# Baseline Runs

These runs are local calibration evidence, not official Kaggle scores. Sparse labels are partial annotations, so unmatched predictions are not automatically false positives.

## 2026-06-30 - Smallest Training Sample

Sample: `6bba_2540cd90`

Ground truth metadata:

- sparse nodes: 529
- sparse edges: 523
- estimated total nodes: 3,783

Baseline settings unless noted:

- full 100 timepoints
- link radius: 7.0 um
- robust percentile normalization per timepoint
- threshold connected components
- nearest-neighbor adjacent-frame linking

### Threshold Sweep, `min_volume=8`

| threshold | elapsed s | predicted nodes | predicted edges | matched sparse nodes | sparse recall | mean error um | sparse edge recall | node ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.80 | 60.38 | 2,317 | 2,179 | 526 | 0.9943 | 2.0622 | 0.9961 | 0.6125 |
| 0.75 | 53.97 | 2,353 | 2,237 | 529 | 1.0000 | 2.0114 | 0.9981 | 0.6220 |
| 0.70 | 53.27 | 2,417 | 2,294 | 529 | 1.0000 | 1.9644 | 0.9981 | 0.6389 |
| 0.65 | 57.15 | 2,496 | 2,362 | 529 | 1.0000 | 1.9345 | 0.9981 | 0.6598 |

### Volume Sweep, `threshold=0.65`

| min volume | elapsed s | predicted nodes | predicted edges | matched sparse nodes | sparse recall | mean error um | sparse edge recall | node ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 57.75 | 2,606 | 2,414 | 529 | 1.0000 | 1.9345 | 0.9981 | 0.6889 |
| 2 | 58.08 | 2,949 | 2,521 | 529 | 1.0000 | 1.9338 | 0.9924 | 0.7795 |
| 1 | 62.13 | 5,075 | 3,392 | 529 | 1.0000 | 1.9278 | 0.9656 | 1.3415 |

Interpretation:

- The simple detector already covers sparse annotated nodes on this easy/small sample.
- `min_volume=8` underpredicts total nodes relative to the GEFF estimate.
- `min_volume=2` is a useful next baseline setting to test across more samples.
- `min_volume=1` overpredicts the estimated total and weakens sparse edge recall, so it is too permissive for this sample.
- These conclusions should not be generalized until tested across both embryos and higher-density samples.

## 2026-06-30 - Mixed Six-Sample Calibration Slice

Settings:

- full 100 timepoints per sample
- threshold: 0.65
- min component volume: 2 voxels
- link radius: 7.0 um
- robust percentile normalization per timepoint
- threshold connected components
- nearest-neighbor adjacent-frame linking

The shell command hit its timeout immediately after printing the complete summary, so the run
returned exit code 124 even though all six sample rows were produced.

| sample | embryo | estimated nodes | elapsed s | predicted nodes | predicted edges | sparse nodes | matched sparse nodes | sparse recall | mean error um | sparse edge recall | node ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 44b6_95029e92 | 44b6 | 5,161 | 307.57 | 5,298 | 3,685 | 200 | 172 | 0.8600 | 1.4398 | 0.9634 | 1.0265 |
| 44b6_40c45f5a | 44b6 | 32,681 | 387.51 | 10,360 | 5,558 | 200 | 4 | 0.0200 | 5.7522 | n/a | 0.3170 |
| 44b6_18ced818 | 44b6 | 78,644 | 1,382.51 | 31,204 | 14,089 | 100 | 40 | 0.4000 | 3.1324 | 0.7667 | 0.3968 |
| 6bba_2540cd90 | 6bba | 3,783 | 58.36 | 2,949 | 2,521 | 529 | 529 | 1.0000 | 1.9338 | 0.9924 | 0.7795 |
| 6bba_20852818 | 6bba | 9,758 | 159.60 | 6,643 | 5,142 | 952 | 738 | 0.7752 | 2.0678 | 0.9211 | 0.6808 |
| 6bba_05db0fb1 | 6bba | 69,800 | 726.38 | 27,708 | 18,611 | 1,229 | 329 | 0.2677 | 2.9131 | 0.8241 | 0.3970 |

Interpretation:

- The current threshold baseline is useful as a scaffold but not robust across samples.
- Low-density samples can look strong under sparse calibration, but median/high-density samples expose severe under-detection.
- The failure is not only total count: `44b6_40c45f5a` matched only 4 of 200 sparse nodes despite producing 10,360 detections, suggesting contrast/domain variation rather than a simple count knob.
- Runtime is a serious constraint: the high-density `44b6_18ced818` sample took about 23 minutes locally.
- Next work should prioritize faster detection summaries, per-sample intensity diagnostics, and adaptive thresholding before adding state or division machinery.

## 2026-06-30 - Intensity and Component Failure Diagnostics

Purpose: explain why `threshold=0.65, min_volume=2` matched sparse labels well on some samples but failed badly on `44b6_40c45f5a`.

Intensity diagnostics read only annotated timepoints and measure sparse annotated centroids under the same robust normalization used by the baseline detector.

| sample | annotated nodes | centroid >= threshold | local max >= threshold | median normalized centroid | median normalized local max |
|---|---:|---:|---:|---:|---:|
| 6bba_2540cd90 | 529 | 0.9698 | 0.9962 | 1.0000 | 1.0000 |
| 44b6_40c45f5a | 200 | 1.0000 | 1.0000 | 0.9224 | 0.9930 |
| 6bba_05db0fb1 | 1,229 | 0.4060 | 0.4841 | 0.5860 | 0.6354 |

Component-at-annotation diagnostics label the thresholded volume and inspect the component containing each sparse annotation.

| sample | annotated nodes | centroid above threshold | median component size | mean component size | median component-centroid distance um | total components | kept components min_volume=2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6bba_2540cd90 | 529 | 513 | 4,171 | 3,994.7 | 1.81 | 5,075 | 2,949 |
| 44b6_40c45f5a | 200 | 200 | 345,313.5 | 315,519.6 | 26.49 | 41,711 | 10,360 |

Interpretation:

- `44b6_40c45f5a` did not fail because sparse annotations are dim; every annotated centroid is above the baseline threshold.
- It failed because thresholded foreground regions merge into huge components, so component centroids drift far away from actual annotated cell centers.
- `6bba_05db0fb1` has a different problem: many sparse annotations are below the current normalized threshold, so dense samples may need adaptive or local contrast handling too.
- The next detector should move from whole-component centroids to local maxima/blob centers or watershed-like splitting inside thresholded foreground.
- This remains calibration evidence, not an official metric or biological conclusion.

## 2026-06-30 - Local-Maxima Detector Trial

Purpose: replace whole-component centroids with peak candidates after diagnosing merged foreground regions in `44b6_40c45f5a`.

Implementation note:

- component detector remains available as `detector="components"`
- new detector is available as `detector="local_maxima"`
- thresholding uses robust normalized intensity
- peak finding uses raw intensity maxima so percentile clipping does not flatten true peaks
- local maxima are candidate centers, not confirmed cells

Sample: `44b6_40c45f5a`

Previous component result at `threshold=0.65, min_volume=2`:

- predicted nodes: 10,360
- matched sparse nodes: 4 / 200
- sparse recall: 0.0200
- node ratio: 0.3170

Local-maxima sweep at `threshold=0.65`:

| peak min distance z/y/x | elapsed s | predicted nodes | predicted edges | matched sparse nodes | sparse recall | mean error um | sparse edge recall | node ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/3/3 | 588.82 | 41,616 | 29,809 | 195 | 0.9750 | 3.3863 | 0.6455 | 1.2734 |
| 1/4/4 | 536.87 | 36,617 | 27,303 | 194 | 0.9700 | 3.5288 | 0.6898 | 1.1204 |
| 1/5/5 | 495.64 | 33,934 | 25,719 | 193 | 0.9650 | 3.6099 | 0.6811 | 1.0383 |
| 2/5/5 | 410.88 | 27,351 | 21,631 | 186 | 0.9300 | 3.9000 | 0.7143 | 0.8369 |

Interpretation:

- The detector change fixes the merged-component centroid failure: sparse recall rises from 0.0200 to roughly 0.93-0.98 on this sample.
- `peak_min_distance_voxels=(1, 5, 5)` is the best first calibration point because it stays close to estimated total node count while preserving high sparse recall.
- Edge recall remains much weaker than node recall, so the next limitation is linking/candidate ambiguity rather than simply finding annotated centers.
- Runtime remains high for local maxima, so hidden-test viability will require profiling and/or cheaper candidate pruning.

## 2026-06-30 - Candidate Cap and Link-Radius Calibration

Purpose: test whether the local-maxima detector's edge weakness on `44b6_40c45f5a` is mostly caused by too many candidates or by link-radius choice.

Detector setting unless noted:

- detector: `local_maxima`
- threshold: 0.65
- peak min distance: `(1, 5, 5)`

Candidate cap sweep at link radius 7.0 um:

| max detections per timepoint | elapsed s | predicted nodes | predicted edges | matched sparse nodes | sparse recall | mean error um | sparse edge recall | node ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 495.64 | 33,934 | 25,719 | 193 | 0.9650 | 3.6099 | 0.6811 | 1.0383 |
| 250 | 487.90 | 24,907 | 18,469 | 188 | 0.9400 | 3.6494 | 0.6966 | 0.7621 |
| 300 | 486.19 | 28,837 | 21,642 | 191 | 0.9550 | 3.6550 | 0.6813 | 0.8824 |

Link-radius sweep using uncapped candidates, with peaks detected once and relinked:

| link radius um | predicted nodes | predicted edges | matched sparse nodes | sparse recall | sparse edge recall | matched/evaluable sparse edges | node ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.0 | 33,934 | 20,863 | 193 | 0.9650 | 0.5892 | 109/185 | 1.0383 |
| 5.0 | 33,934 | 24,847 | 193 | 0.9650 | 0.6649 | 123/185 | 1.0383 |
| 7.0 | 33,934 | 25,719 | 193 | 0.9650 | 0.6811 | 126/185 | 1.0383 |
| 9.0 | 33,934 | 25,966 | 193 | 0.9650 | 0.6865 | 127/185 | 1.0383 |
| 12.0 | 33,934 | 26,050 | 193 | 0.9650 | 0.6865 | 127/185 | 1.0383 |

Interpretation:

- Confidence capping reduces node count but does not materially solve sparse edge recall.
- Link radius saturates around 9 um with only a small gain over 7 um.
- The remaining limitation is likely identity ambiguity in dense candidate fields, not simply candidate count or radius.
- Next linker work should compare one-way greedy nearest neighbor against stricter alternatives such as mutual nearest-neighbor, motion-gated linking, or track-state prediction.

## 2026-07-01 - Mutual Nearest-Neighbor Link Trial

Purpose: compare one-way greedy nearest-neighbor linking against mutual nearest-neighbor linking after local maxima improved detection on `44b6_40c45f5a`.

Detector setting:

- detector: `local_maxima`
- threshold: 0.65
- peak min distance: `(1, 5, 5)`
- candidate nodes: 33,934

| strategy | link radius um | predicted edges | matched sparse nodes | sparse recall | sparse edge recall | matched/evaluable sparse edges | node ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| greedy | 7.0 | 25,719 | 193 | 0.9650 | 0.6811 | 126/185 | 1.0383 |
| greedy | 9.0 | 25,966 | 193 | 0.9650 | 0.6865 | 127/185 | 1.0383 |
| greedy | 12.0 | 26,050 | 193 | 0.9650 | 0.6865 | 127/185 | 1.0383 |
| mutual | 7.0 | 25,105 | 193 | 0.9650 | 0.6649 | 123/185 | 1.0383 |
| mutual | 9.0 | 25,165 | 193 | 0.9650 | 0.6649 | 123/185 | 1.0383 |
| mutual | 12.0 | 25,175 | 193 | 0.9650 | 0.6649 | 123/185 | 1.0383 |

Interpretation:

- Mutual nearest-neighbor is cleaner conceptually and rejects asymmetric links, but it does not improve sparse edge recall on this sample.
- The best simple nearest-neighbor setting remains greedy linking around 9 um for this calibration case.
- The next useful linker change should add temporal context, such as velocity prediction, gap tolerance, or local track competition, rather than only stricter pairwise nearest-neighbor matching.

## 2026-07-01 - Motion-Predicted Nearest-Neighbor Trial

Purpose: test a minimal temporal-context linker after mutual nearest-neighbor failed to improve sparse edge recall on `44b6_40c45f5a`.

Implementation note:

- `link_strategy="motion"` uses the previous accepted edge for a source detection when available.
- The predicted next position is `current_position + (current_position - predecessor_position)`.
- Short tracks without a predecessor fall back to ordinary nearest-neighbor behavior.
- The motion prediction is a deterministic linking aid, not evidence of biological identity.

Detector setting:

- detector: `local_maxima`
- threshold: 0.65
- peak min distance: `(1, 5, 5)`
- candidate nodes: 33,934

| strategy | link radius um | predicted edges | matched sparse nodes | sparse recall | sparse edge recall | matched/evaluable sparse edges | node ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| greedy | 7.0 | 25,719 | 193 | 0.9650 | 0.6811 | 126/185 | 1.0383 |
| greedy | 9.0 | 25,966 | 193 | 0.9650 | 0.6865 | 127/185 | 1.0383 |
| greedy | 12.0 | 26,050 | 193 | 0.9650 | 0.6865 | 127/185 | 1.0383 |
| motion | 7.0 | 24,660 | 193 | 0.9650 | 0.7027 | 130/185 | 1.0383 |
| motion | 9.0 | 24,997 | 193 | 0.9650 | 0.7081 | 131/185 | 1.0383 |
| motion | 12.0 | 25,122 | 193 | 0.9650 | 0.7081 | 131/185 | 1.0383 |

Interpretation:

- Motion-predicted linking improves sparse edge recall on this dense calibration sample without changing detection recall or node count.
- The improvement is modest but meaningful: best sparse edge recall rises from 0.6865 to 0.7081, while predicted edges decrease slightly.
- Best current setting for this sample is `detector="local_maxima"`, `peak_min_distance_voxels=(1, 5, 5)`, `link_strategy="motion"`, and `max_link_distance_um=9.0`.
- Next validation should run this setting across the same mixed six-sample slice before making it the default competition path.

## 2026-07-01 - Mixed Six-Sample Validation for Local-Maxima + Motion

Purpose: validate the current best dense-sample setting across the same mixed slice used by the component baseline.

Settings:

- detector: `local_maxima`
- threshold: 0.65
- peak min distance: `(1, 5, 5)`
- link strategy: `motion`
- max link distance: 9.0 um

| sample | embryo | estimated nodes | elapsed s | predicted nodes | predicted edges | sparse nodes | matched sparse nodes | sparse recall | mean error um | sparse edge recall | node ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 44b6_95029e92 | 44b6 | 5,161 | 141.12 | 4,816 | 3,716 | 200 | 200 | 1.0000 | 1.3708 | 0.8283 | 0.9332 |
| 44b6_40c45f5a | 44b6 | 32,681 | 592.04 | 33,934 | 24,997 | 200 | 193 | 0.9650 | 3.6099 | 0.7081 | 1.0383 |
| 44b6_18ced818 | 44b6 | 78,644 | 1,056.67 | 75,759 | 54,286 | 100 | 95 | 0.9500 | 2.4212 | 0.6304 | 0.9633 |
| 6bba_2540cd90 | 6bba | 3,783 | 96.75 | 3,394 | 2,564 | 529 | 502 | 0.9490 | 3.2432 | 0.5897 | 0.8972 |
| 6bba_20852818 | 6bba | 9,758 | 166.14 | 8,481 | 6,812 | 952 | 755 | 0.7931 | 2.2922 | 0.7249 | 0.8691 |
| 6bba_05db0fb1 | 6bba | 69,800 | 630.79 | 43,474 | 33,285 | 1,229 | 517 | 0.4207 | 2.5638 | 0.6777 | 0.6228 |

Comparison against the earlier component baseline:

- The new setting dramatically improves the `44b6` median/high-density failures:
  - `44b6_40c45f5a`: sparse recall 0.0200 -> 0.9650; node ratio 0.3170 -> 1.0383.
  - `44b6_18ced818`: sparse recall 0.4000 -> 0.9500; node ratio 0.3968 -> 0.9633.
- The new setting improves `44b6_95029e92` sparse recall but lowers sparse edge recall compared with component linking.
- The new setting regresses the easy low-density `6bba_2540cd90` case: sparse edge recall 0.9924 -> 0.5897.
- `6bba_05db0fb1` remains difficult: sparse recall improves from 0.2677 to 0.4207 but still indicates many sparse annotations are not handled by this detector/threshold.

Interpretation:

- `local_maxima + motion` is a better general candidate path for dense/merged-foreground samples, especially `44b6`.
- It should not blindly replace the component detector for all samples yet, because low-density `6bba` tracking quality worsens.
- The next useful baseline should choose detector settings adaptively from quick per-sample diagnostics: component detector for clean low-density foreground, local-maxima detector for merged/large-component foreground, and possibly lower/local thresholding for dim dense `6bba` samples.
- Runtime is improved versus the previous high-density component run for `44b6_18ced818` but remains too high for a comfortable notebook-only hidden test path without pruning/profiling.

## 2026-07-01 - Adaptive Detector Selector

Purpose: choose between the component detector and local-maxima detector using image-only foreground diagnostics, so hidden-test samples can be routed without sparse-label access.

Rule implemented in `atabey.detection.adaptive`:

- sample timepoints: first, quarter, middle, three-quarter, final
- compute thresholded foreground at threshold 0.65
- if median largest connected component >= 100,000 voxels or median foreground fraction >= 0.05:
  - detector: `local_maxima`
  - peak min distance: `(1, 5, 5)`
  - link strategy: `motion`
  - max link distance: 9.0 um
- otherwise:
  - detector: `components`
  - min volume: 2
  - link strategy: `greedy`
  - max link distance: 7.0 um

Selector decisions on the mixed six-sample calibration slice:

| sample | median largest component | median foreground fraction | selected detector | selected linker |
|---|---:|---:|---|---|
| 44b6_95029e92 | 6,145 | 0.0147 | components | greedy |
| 44b6_40c45f5a | 356,588 | 0.0933 | local_maxima | motion |
| 44b6_18ced818 | 465,747 | 0.1364 | local_maxima | motion |
| 6bba_2540cd90 | 5,539 | 0.0120 | components | greedy |
| 6bba_20852818 | 7,818 | 0.0166 | components | greedy |
| 6bba_05db0fb1 | 201,885 | 0.0775 | local_maxima | motion |

Expected behavior from prior full validation:

- This should avoid the catastrophic `44b6` component-centroid failures by routing merged foreground to local maxima.
- It should preserve the stronger component-based edge behavior on clean low-foreground `6bba` samples.
- It does not fully solve dim/dense `6bba_05db0fb1`; that sample likely needs local contrast or lower-threshold candidate recovery.

Submit-readiness note:

- This is good enough as a local measurement baseline and a scaffold for generating a submission file on the visible test set.
- It is not yet safe as an official Kaggle hidden-test submission path because runtime is still likely too high for the 12-hour notebook limit if hidden test is train-sized.
- Before a serious Kaggle submission, add a runtime profile and pruning/cap strategy, then run a clean notebook smoke that writes `submission.csv` for all visible test samples.

## 2026-07-01 - Visible Test Adaptive Submission Smoke

Purpose: run the adaptive baseline over the four visible test samples and write a Kaggle-shaped submission CSV.

Command output artifacts:

- submission CSV: `submissions/visible_test_adaptive_submission.csv`
- runtime report: `submissions/visible_test_adaptive_report.json`

Output CSV shape:

- rows: 243,987
- columns: `id,dataset,row_type,node_id,t,z,y,x,source_id,target_id`

Per-sample runtime and output counts:

| sample | elapsed s | detector | linker | predicted nodes | predicted edges | median largest component | foreground fraction |
|---|---:|---|---|---:|---:|---:|---:|
| 44b6_0113de3b | 522.74 | components | greedy | 20,904 | 17,511 | 2,511 | 0.0226 |
| 44b6_0b24845f | 1,537.36 | local_maxima | motion | 74,414 | 46,313 | 1,636,334 | 0.3932 |
| 6bba_05b6850b | 98.43 | components | greedy | 4,431 | 3,655 | 12,132 | 0.0178 |
| 6bba_05db0fb1 | 614.98 | local_maxima | motion | 43,474 | 33,285 | 201,885 | 0.0775 |

Interpretation:

- The adaptive runner can generate a valid visible-test submission artifact and per-sample audit report.
- Total visible-test runtime was about 46.2 minutes locally for 4 samples.
- Runtime is not yet safe for a serious hidden-test Kaggle submission if hidden test is approximately train-sized.
- The `44b6_0b24845f` visible sample is the strongest runtime warning: one sample took about 25.6 minutes and produced 120,727 rows.
- The next competition-readiness step should be runtime pruning/profiling for local-maxima samples, not more scoring tweaks.

## 2026-07-01 - Detector Extraction Runtime Optimization

Purpose: remove per-label rescans from detector extraction and re-run the visible-test adaptive submission smoke.

Implementation change:

- component detections now use vectorized label counts, coordinate sums, and intensity summaries
- local-maxima detections now emit peak coordinates directly instead of labeling and rescanning peak components
- detector semantics remain bounded candidate generation, not confirmed identity

10-timepoint visible-test smoke after optimization:

| sample | elapsed s | detector | predicted nodes | predicted edges |
|---|---:|---|---:|---:|
| 44b6_0113de3b | 3.59 | components | 1,805 | 1,445 |
| 44b6_0b24845f | 5.46 | local_maxima | 4,894 | 2,729 |
| 6bba_05b6850b | 3.22 | components | 498 | 379 |
| 6bba_05db0fb1 | 5.01 | local_maxima | 4,769 | 3,317 |

Full visible-test adaptive submission after optimization:

- submission CSV: `submissions/visible_test_adaptive_submission_fast.csv`
- runtime report: `submissions/visible_test_adaptive_report_fast.json`
- rows: 244,472
- columns: `id,dataset,row_type,node_id,t,z,y,x,source_id,target_id`

| sample | old elapsed s | new elapsed s | detector | predicted nodes | predicted edges |
|---|---:|---:|---|---:|---:|
| 44b6_0113de3b | 522.74 | 36.67 | components | 20,904 | 17,511 |

## 2026-07-01 - Official Kaggle Hidden-Test Leaderboard Scores

These are the first official Kaggle scores for Atabey, not local sparse calibration. They come from
the two adaptive-baseline notebook submissions that ran offline on the four hidden-test samples.

| version | kernel output | linker | submission rows | total runtime s | leaderboard score |
|---|---|---|---:|---:|---:|
| v7 | `kaggle_kernel/remote_output_v7/` | motion | 244,472 | ~191.7 | 0.498 |
| v8 | `kaggle_kernel/remote_output_v8/` | motion_division | 254,680 | ~234.4 | 0.499 |

Both versions share identical detection (adaptive components / local maxima by foreground profile),
`threshold=0.65`, `min_volume=2`, `peak_min_distance_voxels=(1, 5, 5)`. The only difference is the
linker on merged-foreground samples: v7 uses `motion`, v8 uses conservative division-aware
`motion_division`, which adds 10,208 edge rows.

Interpretation:

- Both submissions are valid hidden-test runs and finished far under the notebook runtime limit.
- The division-aware linker (v8) improved the score by only +0.001 over plain motion linking (v7).
- The gain is real but marginal, and it came entirely from added edges, so division-aware linking is
  not clearly worth its extra complexity at this scoring level yet.
- These scores are the first true anchor for the metric. Local sparse recall (~0.97 node,
  ~0.66 edge on `44b6_40c45f5a`) does not map linearly to the official score, so future changes must
  be validated against the leaderboard, not only sparse calibration.
- Next work should target the weakest measured axis, edge/identity quality in dense fields, since
  detection already covers most annotated centers and linker changes so far move the score only
  slightly.
| 44b6_0b24845f | 1,537.36 | 52.76 | local_maxima | 74,519 | 46,334 |
| 6bba_05b6850b | 98.43 | 30.47 | components | 4,431 | 3,655 |
| 6bba_05db0fb1 | 614.98 | 50.35 | local_maxima | 43,769 | 33,349 |

Interpretation:

- Full visible-test runtime dropped from about 46.2 minutes to about 2.84 minutes.
- This makes an official Kaggle baseline submission technically more plausible from a runtime perspective.
- It is still a baseline-quality submission: sparse validation shows unresolved weaknesses on dim/dense `6bba` samples and edge recall is still limited.
- Next before submission: package a Kaggle-notebook-compatible path and, if possible, run one local train-slice regression check after the optimization to ensure sparse behavior did not drift meaningfully.


## 2026-07-01 - Optimized Adaptive Train-Slice Regression

Purpose: re-check the adaptive baseline after optimizing component and local-maxima extraction, using the same mixed six-sample training slice.

Settings are selected from image-only foreground profiling:

- compact foreground: `detector="components"`, `link_strategy="greedy"`, radius 7.0 um
- merged/high-foreground samples: `detector="local_maxima"`, `link_strategy="motion"`, radius 9.0 um
- threshold: 0.65
- min component volume: 2 voxels
- local-maxima spacing: `(1, 5, 5)`

| sample | selected detector | link strategy | elapsed s | predicted nodes | predicted edges | matched sparse nodes | sparse recall | median error um | sparse edge recall | node ratio |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 44b6_95029e92 | components | greedy | 35.11 | 5,298 | 3,685 | 172/200 | 0.8600 | 0.5579 | 0.9634 | 1.0265 |
| 44b6_40c45f5a | local_maxima | motion | 51.59 | 34,066 | 25,020 | 193/200 | 0.9650 | 3.4947 | 0.7027 | 1.0424 |
| 44b6_18ced818 | local_maxima | motion | 53.17 | 76,052 | 54,348 | 95/100 | 0.9500 | 2.2981 | 0.6304 | 0.9670 |
| 6bba_2540cd90 | components | greedy | 30.26 | 2,949 | 2,521 | 529/529 | 1.0000 | 1.8195 | 0.9924 | 0.7795 |
| 6bba_20852818 | components | greedy | 32.60 | 6,643 | 5,142 | 738/952 | 0.7752 | 1.7034 | 0.9211 | 0.6808 |
| 6bba_05db0fb1 | local_maxima | motion | 51.05 | 43,769 | 33,349 | 517/1,229 | 0.4207 | 2.0313 | 0.6711 | 0.6271 |

Summary:

- total runtime: 254.44 s for six full training samples
- median sparse recall: 0.9050
- median sparse edge recall: 0.8119
- median predicted-to-estimated node ratio: 0.8733
- total predicted nodes: 168,777
- total predicted edges: 124,065

Interpretation:

- The optimized detector preserves the adaptive routing behavior from the slower validation runs while making full-sample iteration practical.
- Component routing intentionally remains better for clean/compact samples such as `6bba_2540cd90`, where local maxima had reduced sparse edge recall.
- Local-maxima routing still fixes the merged-component failure on `44b6_40c45f5a` and keeps node count close to the GEFF estimate.
- `6bba_05db0fb1` remains the main weak sample: recall is still low, so future work should target dim/dense detection rather than more nearest-neighbor linking.
- This is good enough for a first baseline submission to measure the official metric and runtime envelope, but it should be presented as a baseline measurement rather than a strong competition model.

Artifacts:

- `submissions/train_slice_adaptive_regression_fast.json`
- `submissions/visible_test_adaptive_submission_fast.csv`
- `submissions/visible_test_adaptive_report_fast.json`

## 2026-07-01 - First Kaggle Baseline Submission

Direct CSV upload was rejected because this is a notebooks-only code competition. The baseline was packaged as a private Kaggle script kernel and submitted from the completed kernel output.

Kernel:

- slug: `drakus74/atabey-adaptive-baseline`
- submitted kernel version: 7
- code path: `kaggle_kernel/run.py`
- remote output report: `kaggle_kernel/remote_output_v7/adaptive_runtime_report.json`
- remote output CSV: `kaggle_kernel/remote_output_v7/submission.csv`

Packaging notes:

- Kaggle did not include `zarr` or `numcodecs` in the runtime image.
- The submitted script includes a minimal Zarr v3 reader for the competition chunk layout, using Kaggle's available `blosc2` package to decompress chunks.
- The script writes `/kaggle/working/submission.csv` as required by the code competition.

Submission:

- submission id: `54234740`
- submitted at: `2026-07-01 14:15:13.280000` Kaggle time
- message: `optimized adaptive baseline kernel v7: components/local-maxima motion`
- public score: `0.498`
- status at local check: `COMPLETE`

Interpretation:

- The baseline scored `0.498` on the public leaderboard.
- Use the public score from this submission as the first official calibration anchor before optimizing dim/dense detection or division handling.

## 2026-07-01 - Motion-Division Linker Trial

Purpose: test whether a conservative second-child edge improves tracking calibration without changing the detector.

Implementation:

- new link strategy: `motion_division`
- starts from the existing one-to-one motion linker
- adds at most one second outgoing edge per source
- the extra target must be unused, within the same link radius, and must have the same source as its nearest previous detection
- split edges are marked with `relation="division"`
- this is a bounded mitosis candidate, not a biological assertion

Train-slice regression, compared with the previous adaptive route:

| sample | detector | tested link | nodes | edges | extra division edges | sparse recall | sparse edge recall |
|---|---|---|---:|---:|---:|---:|---:|
| 44b6_95029e92 | components | greedy | 5,298 | 3,685 | 0 | 0.8600 | 0.9634 |
| 44b6_40c45f5a | local_maxima | motion_division | 34,066 | 27,012 | 2,062 | 0.9650 | 0.7405 |
| 44b6_18ced818 | local_maxima | motion_division | 76,052 | 59,490 | 5,552 | 0.9500 | 0.6522 |
| 6bba_2540cd90 | components | greedy | 2,949 | 2,521 | 0 | 1.0000 | 0.9924 |
| 6bba_20852818 | components | greedy | 6,643 | 5,142 | 0 | 0.7752 | 0.9211 |
| 6bba_05db0fb1 | local_maxima | motion_division | 43,769 | 35,866 | 2,707 | 0.4207 | 0.6998 |

Summary:

- median sparse recall: 0.9050, unchanged from the prior adaptive baseline
- median sparse edge recall: 0.8308, up from 0.8119
- total division-labeled edges on train slice: 10,321
- total predicted edges: 133,716, up from 124,065

Visible-test local run:

- output CSV: `submissions/visible_test_motion_division_submission.csv`
- report JSON: `submissions/visible_test_motion_division_report.json`
- rows: 254,680
- nodes: 143,623
- edges: 111,057

Interpretation:

- Local sparse calibration supports trying this as the next official submission.
- The added split edges improve sparse edge recall on all local-maxima routed train samples.
- Risk: the official metric penalizes false positive edges, so public score may fall if the conservative split rule still overpredicts divisions or edges on hidden labels.

Kaggle submission:

- kernel slug: `drakus74/atabey-adaptive-baseline`
- submitted kernel version: 8
- submission id: `54240604`
- message: `motion_division adaptive baseline: conservative split edges`
- status at local check: `PENDING`
- remote output report: `kaggle_kernel/remote_output_v8/adaptive_runtime_report.json`
- remote output CSV: `kaggle_kernel/remote_output_v8/submission.csv`


## 2026-07-01 - Stricter Identity Linker (motion_mutual) Prototype and Local Validation

Purpose: prototype a stricter identity-gated linker to attack the weakest measured axis
(edge/identity quality in dense fields) rather than adding more edges. The two official scores
showed that adding edges via `motion_division` moved the score only +0.001 over plain `motion`,
so this trial goes the other direction: reject contested links instead of adding them.

New strategy: `motion_mutual`

- Forward gate: each source keeps its motion-predicted nearest target (directional, same as `motion`).
- Identity gate: the link is accepted only if that target's nearest previous detection in physical
  microns is the same source (mutual nearest-neighbor).
- Effect: contested targets in dense candidate fields are dropped, trading a little recall for fewer
  identity switches. It is a bounded linking aid, not a biological identity claim.
- Available in both `src/atabey/tracking/nearest_neighbor.py` and the self-contained
  `kaggle_kernel/run.py`. Adaptive routing is unchanged; `motion_mutual` is opt-in for now.

Unit tests added (`tests/test_baseline.py`), full suite 26 passed:

- `test_motion_mutual_rejects_contested_target`: `motion` links a source to a target that physically
  belongs to another source; `motion_mutual` correctly reassigns the target to its physical owner.
- `test_motion_mutual_accepts_uncontested_prediction`: an uncontested motion-predicted continuation
  is still linked.

Local edge-count comparison on the two merged-foreground visible-test samples
(`detector=local_maxima`, `threshold=0.65`, `peak_min_distance_voxels=(1, 5, 5)`, radius 9.0 um,
first 15 timepoints). Node counts are identical across strategies because detection is unchanged.

| sample | strategy | nodes | edges | edge/node | elapsed s |
|---|---|---:|---:|---:|---:|
| 44b6_0b24845f | motion | 7,674 | 4,404 | 0.5739 | 10.83 |
| 44b6_0b24845f | motion_division | 7,674 | 5,177 | 0.6746 | 9.31 |
| 44b6_0b24845f | motion_mutual | 7,674 | 3,858 | 0.5027 | 9.48 |
| 6bba_05db0fb1 | motion | 7,318 | 5,227 | 0.7143 | 9.51 |
| 6bba_05db0fb1 | motion_division | 7,318 | 5,673 | 0.7752 | 9.20 |
| 6bba_05db0fb1 | motion_mutual | 7,318 | 5,064 | 0.6920 | 9.09 |

Interpretation:

- `motion_mutual` is the strictest linker: it produces the fewest edges on both merged samples
  (about 12 percent fewer than `motion`, about 25 percent fewer than `motion_division`).
- Runtime is comparable to `motion`, so the mutual identity gate adds no meaningful cost.
- Edge count alone cannot decide value: the official metric penalizes both missing and false edges.
  If the dropped edges are mostly identity switches, the score could rise; if they are correct
  continuations, it could fall.
- This is calibration evidence only. A real leaderboard submission is required to know whether
  stricter identity gating beats the current v8 score of 0.499. Do not conclude from local counts.


## 2026-07-01 - v9 Adaptive Routing Switched to motion_mutual (Full Visible-Test)

Purpose: promote the stricter `motion_mutual` linker into the adaptive routing so merged-foreground
samples use mutual-identity gating instead of division-aware edge adding. This is the v9 candidate
to compare against v7 (`motion`, 0.498) and v8 (`motion_division`, 0.499).

Change: `choose_adaptive_baseline_settings` now routes merged-foreground samples to
`link_strategy="motion_mutual"` (was `motion_division`). Compact samples still use
`components` + `greedy`. Detection is unchanged, so node counts match v7/v8 exactly.
Updated in `src/atabey/detection/adaptive.py`, the self-contained `kaggle_kernel/run.py`, and the
adaptive routing test. Full suite: 26 passed.

Full visible-test submission artifacts:

- submission CSV: `submissions/visible_test_v9_motion_mutual_submission.csv`
- runtime report: `submissions/visible_test_v9_motion_mutual_report.json`
- total data rows: 238,713

Per-sample outputs (full 100 timepoints):

| sample | detector | linker | nodes | edges | elapsed s |
|---|---|---|---:|---:|---:|
| 44b6_0113de3b | components | greedy | 20,904 | 17,511 | 47.64 |
| 44b6_0b24845f | local_maxima | motion_mutual | 74,519 | 41,474 | 73.49 |
| 6bba_05b6850b | components | greedy | 4,431 | 3,655 | 44.38 |
| 6bba_05db0fb1 | local_maxima | motion_mutual | 43,769 | 32,450 | 75.18 |

Merged-sample edge counts vs prior versions (compact samples are identical across all versions):

| merged sample | v7 motion edges | v8 motion_division edges | v9 motion_mutual edges |
|---|---:|---:|---:|
| 44b6_0b24845f | 46,334 | 54,025 | 41,474 |
| 6bba_05db0fb1 | 33,349 | 35,866 | 32,450 |

Total submission rows by version:

| version | linker (merged) | total rows | leaderboard score |
|---|---|---:|---:|
| v7 | motion | 244,472 | 0.498 |
| v8 | motion_division | 254,680 | 0.499 |
| v9 | motion_mutual | 238,713 | 0.504 |

Interpretation:

- v9 is the leanest submission: about 5,759 fewer rows than v7 and about 15,967 fewer than v8, all
  from removed edges on the two merged samples. Node counts are identical to v7/v8.
- This is the direct test of the hypothesis that dense-field score is limited by identity switches
  (false edges) rather than by too few edges.
- Official result: v9 scored 0.504, which is +0.005 over v8 (0.499) and +0.006 over v7 (0.498).
  This is strong evidence that stricter identity gating removed more harmful edges than useful ones.
- With v10 now submitted and pending, the key question is whether crowding-gated edge recovery can
  keep most of v9's identity gain while recovering additional correct continuations.
- This remains local calibration evidence. Only the official leaderboard score decides v9 vs v8/v7.

v9 Kaggle submission was pushed from a kernel that routed merged samples to `motion_mutual`. The
kernel source has since advanced to the v10 `motion_crowding` routing (see the next section), so to
reproduce v9 exactly, check out the `motion_mutual` routing revision before pushing.


## 2026-07-01 - v10 Crowding-Gated Hybrid Linker (motion_crowding, Full Visible-Test)

Purpose: test whether applying the strict identity gate only where it is needed beats both the
permissive `motion` (v7) and the fully strict `motion_mutual` (v9). The hypothesis from v9 was that
some of the edges v9 trimmed were genuine sparse-region continuations, not identity switches.

New strategy: `motion_crowding` (crowding-gated hybrid)

- Each source keeps its motion-predicted nearest target (permissive, like `motion`).
- A target is flagged "contested" by a Lowe-style ratio test on physical distance: it is contested
  when its nearest and second-nearest previous detections are within `crowding_ratio` of each other
  (`nearest / second_nearest > crowding_ratio`). Default `crowding_ratio = 0.8`.
- The `motion_mutual` identity gate is enforced only for contested targets. Uncontested (sparse)
  targets stay permissive to preserve recall; contested (crowded) targets require mutual agreement
  to suppress identity switches.
- Boundaries: `crowding_ratio = 1.0` reduces to `motion`; `crowding_ratio = 0.0` approaches
  `motion_mutual`. The ratio is a geometric ambiguity signal, not biological identity evidence.
- Added to `src/atabey/tracking/nearest_neighbor.py` and the self-contained `kaggle_kernel/run.py`.
  Adaptive routing for merged samples now selects `motion_crowding` (was `motion_mutual`).

Unit tests added (`tests/test_baseline.py`), full suite 28 passed:

- `test_motion_crowding_gates_only_contested_targets`: a crowded target where `motion` switches to a
  far predicted source; the crowding gate reassigns it to the physical owner (matches mutual).
- `test_motion_crowding_ratio_one_reduces_to_motion`: with `crowding_ratio = 1.0` nothing is
  contested, so the hybrid reproduces permissive motion linking.

Full visible-test submission artifacts:

- submission CSV: `submissions/visible_test_v10_motion_crowding_submission.csv`
- runtime report: `submissions/visible_test_v10_motion_crowding_report.json`
- total data rows: 241,544

Per-sample outputs (full 100 timepoints):

| sample | detector | linker | nodes | edges | elapsed s |
|---|---|---|---:|---:|---:|
| 44b6_0113de3b | components | greedy | 20,904 | 17,511 | 50.79 |
| 44b6_0b24845f | local_maxima | motion_crowding | 74,519 | 43,921 | 73.98 |
| 6bba_05b6850b | components | greedy | 4,431 | 3,655 | 45.47 |
| 6bba_05db0fb1 | local_maxima | motion_crowding | 43,769 | 32,834 | 74.79 |

Merged-sample edge counts across all four linkers (compact samples identical everywhere):

| merged sample | v7 motion | v8 motion_division | v9 motion_mutual | v10 motion_crowding |
|---|---:|---:|---:|---:|
| 44b6_0b24845f | 46,334 | 54,025 | 41,474 | 43,921 |
| 6bba_05db0fb1 | 33,349 | 35,866 | 32,450 | 32,834 |

Total submission rows by version:

| version | linker (merged) | total rows | leaderboard score |
|---|---|---:|---:|
| v7 | motion | 244,472 | 0.498 |
| v8 | motion_division | 254,680 | 0.499 |
| v9 | motion_mutual | 238,713 | 0.504 |
| v10 | motion_crowding | 241,544 | 0.500 |

Interpretation:

- v10 lands exactly between v9 (strict) and v7 (permissive) on both merged samples, confirming the
  hybrid keeps sparse-region continuations that v9 trimmed while still dropping crowded switches.
- On `44b6_0b24845f` v10 recovers 2,447 edges over v9; on `6bba_05db0fb1` it recovers 384. These are
  the links the ratio test judged unambiguous.
- Official result: v10 scored 0.500, which is below v9 (0.504) but above v8 (0.499) and v7 (0.498).
- This suggests the crowding-gated recovery restored some useful continuations over older baselines,
  but it also reintroduced enough identity errors to underperform the stricter v9 operating point.
- Immediate implication: keep v9 (`motion_mutual`) as the best current anchor. Treat v10 as evidence
  that selective edge recovery must be tighter before it can beat v9.
- `crowding_ratio` is a single tunable knob spanning v7 (1.0) to v9 (0.0). If v10 is promising, the
  next sweep is `crowding_ratio` in {0.6, 0.7, 0.8, 0.9} to find the recall/precision knee.
- This is local calibration evidence only. The official leaderboard score decides v10 vs v9/v8/v7.

v10 official Kaggle score is now recorded. Next branch decision should compare two options:

- tighten crowding recovery (lower `crowding_ratio`, toward v9 behavior)
- keep v9 as tracking anchor and test a minimal latent-bridge mechanism on top


## 2026-07-02 - v11 Minimal Latent Bridge on v9 Anchor (motion_mutual_latent, Full Visible-Test)

Purpose: keep v9's strict identity anchor (`motion_mutual`) and add a bounded one-frame latent
recovery path for short gaps, translated from the dormant-potential concept without relaxing
identity discipline globally.

New strategy: `motion_mutual_latent`

- Primary adjacent linking remains strict `motion_mutual`.
- A source enters latent only if it was unmatched and has established track history
  (minimum 2 accepted edges).
- Latent window is fixed to 1 frame.
- Latent recovery only considers currently unmatched targets and requires:
  - bounded prediction error (<= link radius)
  - bounded physical step distance scaled by gap size
- Recovered edges are marked with `relation="latent_recovery"` for auditability.
- Expired latent tracks are removed deterministically.

Implementation notes:

- package path updated:
  - `src/atabey/tracking/nearest_neighbor.py`
  - `src/atabey/baseline.py`
  - `src/atabey/detection/adaptive.py`
- self-contained Kaggle path updated:
  - `kaggle_kernel/run.py`

Tests:

- added/updated pipeline tests for:
  - one-frame latent recovery on a stable track
  - no latent recovery for tracks without sufficient history
  - no latent recovery for first-appearance tracks without predecessor context
- adaptive routing test updated to merged-strategy `motion_mutual_latent`
- full suite: 31 passed (`python -m pytest -q`)

Full visible-test submission artifacts:

- submission CSV: `submissions/visible_test_v11_motion_mutual_latent_submission.csv`
- runtime report: `submissions/visible_test_v11_motion_mutual_latent_report.json`
- total data rows: 245,450

Per-sample outputs (full 100 timepoints):

| sample | detector | linker | nodes | edges | elapsed s |
|---|---|---|---:|---:|---:|
| 44b6_0113de3b | components | greedy | 20,904 | 17,511 | 62.76 |
| 44b6_0b24845f | local_maxima | motion_mutual_latent | 74,519 | 46,508 | 78.37 |
| 6bba_05b6850b | components | greedy | 4,431 | 3,655 | 28.82 |
| 6bba_05db0fb1 | local_maxima | motion_mutual_latent | 43,769 | 34,153 | 50.68 |

Latent-edge diagnostics (local, full visible test):

- total predicted edges: 101,827
- latent recovery edges: 10,397
- latent recovery by merged sample:
  - `44b6_0b24845f`: 7,568
  - `6bba_05db0fb1`: 2,829

Comparison vs prior versions (visible-test local counts):

| version | linker (merged) | total edges | total rows | leaderboard score |
|---|---|---:|---:|---:|
| v9 | motion_mutual | 95,090 | 238,713 | 0.504 |
| v10 | motion_crowding | 97,921 | 241,544 | 0.500 |
| v11 | motion_mutual_latent | 101,827 | 245,450 | 0.493 |

Interpretation:

- v11 increases edges over v9 (+6,737) and v10 (+3,906), entirely from bounded gap recovery
  on merged samples.
- This is a targeted continuity experiment, not a looser global linker: adjacent-frame identity
  remains strict `motion_mutual`.
- Official result: v11 scored 0.493, which is below v10 (0.500) and v9 (0.504).
- This supports the edge-precision risk hypothesis: latent recovery increased continuity edges
  but likely added enough false continuity to hurt the metric.
- Decision anchor remains clear: v9 at 0.504 is still the peak reference, while v11 at 0.493
  marks the current lower bound for over-recovery behavior.

Lessons learned:

- More continuity is not automatically better: the latent bridge improved edge count, but the
  leaderboard score fell to 0.493, so over-recovery can cost more than it helps.
- Runtime discipline still matters: the feature added complexity and more output rows without a
  score gain, so the next candidate should justify its cost with measurable quality improvement.


## 2026-07-02 - CFAR and Side-Lobe Suppression Concept Probe (Local Calibration Only)

Purpose: test radar-inspired detection concepts as local calibration experiments (not submission):

- CFAR-style adaptive thresholding in dense/heterogeneous background
- side-lobe-style suppression of nearby weaker peaks

This probe is explicitly exploratory. It does not alter adaptive submission routing.

Why these ideas are plausible for cell tracking:

- CFAR can adapt the detection threshold to local background structure, which matters when the
  embryo image has uneven density, contrast, or large merged foreground regions.
- Side-lobe suppression can reduce duplicate or nearby weaker peaks around a stronger center,
  which is useful when one biological cell produces several candidate peaks in a dense cluster.
- The intended effect is not biological certainty. The goal is to improve candidate recovery and
  reduce ambiguous peak clutter so downstream linking has a cleaner set of cell candidates.

Implementation:

- Added detector variants in `src/atabey/detection/baseline.py`:
  - `threshold_local_maxima_cfar`
  - `threshold_local_maxima_cfar_sidelobe`
- Added experiment runner:
  - `scripts/run_cfar_sidelobe_experiment.py`
- Added detector tests in `tests/test_baseline.py`.

Experiment setup (smoke):

- samples: `44b6_40c45f5a`, `6bba_05db0fb1` (hard merged/dense cases)
- timepoints: first 30 only (bounded runtime)
- linking held constant for fairness: `motion_mutual`, radius 9.0 um
- strategies compared:
  - `local_maxima_baseline` (current local-max detector)
  - `cfar`
  - `cfar_sidelobe`
- output artifact: `submissions/cfar_sidelobe_experiment_smoke.json`

Smoke results:

| sample | strategy | elapsed s | predicted nodes | predicted edges | matched sparse nodes | sparse recall | sparse edge recall | node ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 44b6_40c45f5a | local_maxima_baseline | 25.64 | 7,933 | 5,548 | 60 | 0.3000 | 0.6897 | 0.2427 |
| 44b6_40c45f5a | cfar | 194.20 | 9,478 | 6,519 | 60 | 0.3000 | 0.6897 | 0.2900 |
| 44b6_40c45f5a | cfar_sidelobe | 235.90 | 9,478 | 6,519 | 60 | 0.3000 | 0.6897 | 0.2900 |
| 6bba_05db0fb1 | local_maxima_baseline | 27.61 | 15,417 | 10,995 | 145 | 0.1180 | 0.6639 | 0.2209 |
| 6bba_05db0fb1 | cfar | 147.56 | 23,579 | 16,954 | 236 | 0.1920 | 0.6683 | 0.3378 |
| 6bba_05db0fb1 | cfar_sidelobe | 219.05 | 23,579 | 16,954 | 236 | 0.1920 | 0.6683 | 0.3378 |

Findings:

- CFAR improved sparse node recall on dim/dense `6bba_05db0fb1` in this smoke (+0.074 absolute,
  from 0.1180 to 0.1920), with a small sparse edge-recall lift.
- On `44b6_40c45f5a`, CFAR increased node/edge counts in 30-timepoint smoke but did not change
  sparse recall at that depth (0.3000).
- Current side-lobe suppression settings had no measurable effect relative to CFAR alone on this
  smoke configuration.
- Runtime cost is currently high: CFAR and CFAR+sidelobe are much slower than the baseline local
  maxima path.

Interpretation:

- CFAR concept is promising for dim/dense detection recovery, but current implementation is too slow
  and not yet selective enough to be a submission candidate.
- Side-lobe suppression concept is not yet effective with current parameters and needs retuning
  (radius, floor ratio, or confidence definition) before meaningful value can be claimed.
- Next CFAR-focused step, if continued, should be runtime optimization and stronger suppression
  tuning before any leaderboard submission.


## 2026-07-02 - CFAR Runtime Optimization and Bounded Parameter Sweep (Local Smoke)

Purpose: reduce CFAR detector runtime and run a bounded parameter sweep to find a practical
recall/runtime tradeoff under competition-time constraints.

Optimization changes:

- CFAR local background statistics now use box-filter ring math (training box minus guard box)
  instead of explicit 3D convolution kernels.
- Side-lobe suppression now uses voxel-neighborhood indexing for faster stronger-neighbor checks.
- Experiment runner now supports repeated sweep specs from CLI for structured parameter trials.

Validation:

- full suite: 34 passed (`python -m pytest -q`)

Sweep setup:

- samples: `44b6_40c45f5a`, `6bba_05db0fb1`
- timepoints: first 20 only (smoke bound)
- strategies: `local_maxima_baseline`, `cfar`, `cfar_sidelobe`
- constant linker: `motion_mutual`, radius 9.0 um
- output artifact: `submissions/cfar_sidelobe_experiment_optimized_smoke.json`

Parameter specs tested (format: `threshold|train|guard|k_sigma|sidelobe_radius|sidelobe_floor`):

- `0.50|1,7,7|0,1,1|1.0|0,2,2|0.85`
- `0.52|1,6,6|0,1,1|1.1|0,2,2|0.80`
- `0.55|1,6,6|0,1,1|1.2|0,2,2|0.75`

Selected results (`cfar` only):

| sample | params | elapsed s | predicted nodes | matched sparse nodes | sparse recall | sparse edge recall | node ratio |
|---|---|---:|---:|---:|---:|---:|---:|
| 44b6_40c45f5a | 0.50/1,7,7/0,1,1/k1.0 | 34.51 | 5,968 | 40 | 0.2000 | 0.7368 | 0.1826 |
| 44b6_40c45f5a | 0.52/1,6,6/0,1,1/k1.1 | 26.25 | 5,726 | 38 | 0.1900 | 0.7059 | 0.1752 |
| 44b6_40c45f5a | 0.55/1,6,6/0,1,1/k1.2 | 25.99 | 5,515 | 36 | 0.1800 | 0.6970 | 0.1688 |
| 6bba_05db0fb1 | 0.50/1,7,7/0,1,1/k1.0 | 36.19 | 15,440 | 126 | 0.1025 | 0.6881 | 0.2212 |
| 6bba_05db0fb1 | 0.52/1,6,6/0,1,1/k1.1 | 26.60 | 14,646 | 113 | 0.0919 | 0.6737 | 0.2098 |
| 6bba_05db0fb1 | 0.55/1,6,6/0,1,1/k1.2 | 26.35 | 13,540 | 99 | 0.0806 | 0.7500 | 0.1940 |

Findings:

- The optimized CFAR path supports practical sweep iteration on bounded smoke windows.
- Parameter tightening (`threshold` up, smaller training window, larger `k_sigma`) reduces runtime
  and predicted nodes, but also reduces sparse node recall.
- On `6bba_05db0fb1`, all CFAR settings still improve sparse node recall over local-max baseline
  in this 20-timepoint smoke slice.
- Current side-lobe suppression settings still produced identical node/edge outcomes to CFAR-only
  across this sweep, so suppression remains unproven for quality gains.

Decision guidance:

- For CFAR continuation, `0.52|1,6,6|0,1,1|1.1|0,2,2|0.80` is a reasonable next operating point
  for runtime-aware exploration (faster than `0.50` with partial recall retention).
- Keep CFAR out of official submission routing until a longer-window run confirms net quality under
  realistic runtime and side-lobe suppression demonstrates measurable precision benefit.


## 2026-07-02 - Three-Step CFAR Follow-Through (30tp Validation, Sidelobe Sweep, Contrast Upgrade)

Purpose: execute the three agreed continuation steps end-to-end:

- validate CFAR tradeoffs on a longer smoke window (30 timepoints)
- run sidelobe-only calibration at fixed CFAR core settings
- if sidelobe remains neutral, upgrade suppression confidence and re-test

### Step 1: 30-timepoint stability check

Artifact:

- `submissions/cfar_sidelobe_experiment_optimized_30tp.json`

Outcome summary:

- The 20tp pattern remains stable at 30tp:
  - CFAR improves sparse node recall on `6bba_05db0fb1` versus local-max baseline
  - tighter CFAR parameters reduce nodes/runtime but reduce sparse node recall
  - side-lobe suppression remains effectively neutral under the original confidence definition

Representative 30tp CFAR rows:

| sample | params | elapsed s | matched sparse nodes | sparse recall |
|---|---|---:|---:|---:|
| 44b6_40c45f5a | 0.50/1,7,7/0,1,1/k1.0 | 38.81 | 60 | 0.3000 |
| 44b6_40c45f5a | 0.52/1,6,6/0,1,1/k1.1 | 38.22 | 58 | 0.2900 |
| 6bba_05db0fb1 | 0.50/1,7,7/0,1,1/k1.0 | 38.93 | 236 | 0.1920 |
| 6bba_05db0fb1 | 0.52/1,6,6/0,1,1/k1.1 | 39.06 | 216 | 0.1758 |

### Step 2: sidelobe-only sweep at fixed CFAR core

Artifact:

- `submissions/cfar_sidelobe_only_sweep_30tp.json`

Sweep settings:

- fixed CFAR core: `0.52|1,6,6|0,1,1|1.1`
- swept side-lobe: radius in `{0,1,1}`, `{0,2,2}`, `{1,2,2}`, `{1,3,3}` and floor in `{0.95,0.85,0.80,0.75,0.65}`

Outcome summary:

- Under the original confidence definition, `cfar_sidelobe` produced the same node/edge/recall outputs as `cfar` across tested sidelobe settings.
- Conclusion: sidelobe mechanism was neutral in effect and needed a stronger salience definition.

### Step 3: sidelobe confidence upgrade and re-test

Implementation update:

- `src/atabey/detection/baseline.py`
  - CFAR detection confidence now uses a local contrast margin:
    - `confidence = max(0, (signal - adaptive_threshold) / adaptive_threshold)`
  - CFAR peak ranking now uses this margin confidence (not raw normalized intensity)
  - Side-lobe suppression therefore compares locally salient peaks, not globally bright peaks

Validation:

- full suite: 34 passed (`python -m pytest -q`)

Post-upgrade targeted artifact:

- `submissions/cfar_sidelobe_contrast_sweep_30tp.json`

Targeted sweep used:

- fixed CFAR core: `0.52|1,6,6|0,1,1|1.1`
- side-lobe radii: `{0,2,2}`, `{1,8,8}`, `{1,12,12}`
- side-lobe floor: `0.80`

Observed deltas (`cfar_sidelobe` vs `cfar`):

- `44b6_40c45f5a`:
  - `sr1,12,12`: nodes `9105 -> 8533`, sparse edge recall `0.6667 -> 0.7037`
- `6bba_05db0fb1`:
  - `sr1,12,12`: nodes `22420 -> 21100`, sparse edge recall `0.6631 -> 0.6898`

Interpretation:

- The confidence upgrade successfully made side-lobe suppression non-neutral.
- Larger suppression neighborhoods can reduce node count while improving sparse edge recall on these 30tp smoke runs.
- Runtime increases with larger sidelobe neighborhoods, so this is still exploratory and not submission-ready.

Decision guidance:

- Keep CFAR as a local calibration branch (not official routing) until full-length evidence confirms net benefit.
- If continuing, use fixed CFAR core `0.52|1,6,6|0,1,1|1.1` and run a bounded side-lobe radius sweep around `{1,8,8}` to `{1,12,12}` with explicit runtime tracking.
- Promote only if gains persist on longer windows and do not break the notebook runtime envelope.


## 2026-07-02 - CFAR + Side-Lobe Three-Track Continuation (30tp, Merged Hard Samples)

Purpose: execute all three next-step tracks in one pass while keeping CFAR+sidelobe as a local
calibration branch:

- Track 1: fixed-core control check (`baseline` vs `cfar` vs `cfar_sidelobe`)
- Track 2: side-lobe radius sweep at fixed CFAR core
- Track 3: side-lobe floor-ratio sweep at strong radius

Common setup:

- samples: `44b6_40c45f5a`, `6bba_05db0fb1`
- timepoints: first 30
- fixed CFAR core: `threshold=0.52`, `training=1,6,6`, `guard=0,1,1`, `k_sigma=1.1`
- linking held constant: `motion_mutual`, radius 9.0 um

Artifacts:

- `submissions/cfar_sidelobe_track1_core_30tp.json`
- `submissions/cfar_sidelobe_track2_radius_30tp.json`
- `submissions/cfar_sidelobe_track3_floor_30tp.json`

### Track 1: fixed-core control check

Key outcomes:

- `44b6_40c45f5a`:
  - baseline edge recall: `0.6897`
  - CFAR edge recall: `0.6667`
  - CFAR+sidelobe (`sr0,2,2 sf0.80`) edge recall: `0.6667`
- `6bba_05db0fb1`:
  - baseline sparse recall: `0.1180`
  - CFAR sparse recall: `0.1758` (retained strong dim/dense gain)
  - CFAR+sidelobe (`sr0,2,2 sf0.80`) edge recall: `0.6578` (below CFAR `0.6631`)

Interpretation:

- CFAR still provides the main detection lift on dim/dense sample `6bba_05db0fb1`.
- Small side-lobe neighborhood (`sr0,2,2`) remains weak and can slightly hurt edge recall.

### Track 2: side-lobe radius sweep (`sf0.80`)

Radii tested: `sr0,2,2`, `sr1,8,8`, `sr1,12,12`.

Representative deltas (`cfar_sidelobe` vs `cfar`):

| sample | radius | nodes delta | sparse edge recall delta |
|---|---|---:|---:|
| 44b6_40c45f5a | sr0,2,2 | -2 | +0.0000 |
| 44b6_40c45f5a | sr1,8,8 | -157 | +0.0000 |
| 44b6_40c45f5a | sr1,12,12 | -572 | +0.0370 |
| 6bba_05db0fb1 | sr0,2,2 | -4 | -0.0053 |
| 6bba_05db0fb1 | sr1,8,8 | -378 | +0.0160 |
| 6bba_05db0fb1 | sr1,12,12 | -1320 | +0.0267 |

Interpretation:

- Larger neighborhoods are where suppression becomes useful.
- `sr1,12,12` gives the strongest precision-style signal in this 30tp window: fewer nodes with
  better sparse edge recall on both samples.

### Track 3: floor-ratio sweep at `sr1,12,12`

Floors tested: `0.95`, `0.85`, `0.80`, `0.75`, `0.65`.

Observed behavior:

- Higher floor ratio increases suppression strength (larger node reduction).
- `44b6_40c45f5a` edge recall remained stable at `0.7037` across all tested floors.
- `6bba_05db0fb1` edge recall peaked at `0.6898` for floors `0.80` and `0.75`.
- Very loose floor `0.65` regressed `6bba` edge recall back to CFAR-level (`0.6631`).

Decision guidance:

- Continue CFAR calibration around `sr1,12,12` with floor in `[0.75, 0.85]`.
- Keep this branch out of official submission routing until full-length visible-test evidence is
  positive under runtime constraints.
- Preserve leaderboard anchor discipline: compare all branch ideas against v9 (`0.504`) with v11
  (`0.493`) as over-recovery floor reference.


## 2026-07-02 - 50tp Stability Check + Quality-per-Second Ranking (Best Side-Lobe Settings)

Purpose: execute the agreed 50-timepoint stability pass on the best side-lobe settings and add
runtime-aware ranking support directly in the CFAR experiment runner.

Runner update:

- `scripts/run_cfar_sidelobe_experiment.py` now emits per-record runtime-normalized metrics:
  - `nodes_per_second`
  - `edges_per_second`
  - `matched_sparse_nodes_per_second`
  - `quality_score = 0.5 * sparse_recall + 0.5 * sparse_edge_recall`
  - `quality_per_second`
- Added optional summary artifact support:
  - `--output-summary-json`
  - `--top-k`

50tp experiment setup:

- samples: `44b6_40c45f5a`, `6bba_05db0fb1`
- timepoints: first 50
- fixed CFAR core: `0.52|1,6,6|0,1,1|1.1`
- side-lobe radius: `1,12,12`
- floor candidates: `0.85`, `0.75`
- constant linker: `motion_mutual`, radius 9.0 um

Artifacts:

- `submissions/cfar_sidelobe_best_50tp.json`
- `submissions/cfar_sidelobe_best_50tp_summary.json`

Ranked strategy summaries (50tp, ranking metric: `quality_per_second`):

| rank | strategy | mean quality score | quality per second |
|---:|---|---:|---:|
| 1 | local_maxima_baseline + `sr1,12,12 sf0.75` | 0.5390 | 0.0220 |
| 2 | local_maxima_baseline + `sr1,12,12 sf0.85` | 0.5390 | 0.0201 |
| 3 | cfar + `sr1,12,12 sf0.75` | 0.5510 | 0.0084 |
| 4 | cfar + `sr1,12,12 sf0.85` | 0.5510 | 0.0084 |
| 5 | cfar_sidelobe + `sr1,12,12 sf0.85` | 0.5587 | 0.0080 |
| 6 | cfar_sidelobe + `sr1,12,12 sf0.75` | 0.5573 | 0.0080 |

CFAR+sidelobe sample-level deltas (`sf0.75` vs `sf0.85`):

- `44b6_40c45f5a`:
  - sparse edge recall stayed `0.7500` for both floors
  - `sf0.85` was slightly more suppressive (fewer nodes)
- `6bba_05db0fb1`:
  - sparse edge recall was slightly higher at `sf0.85` (`0.7094`) than `sf0.75` (`0.7037`)
  - both floors retained CFAR dim/dense node-recall lift versus local-max baseline

Decision guidance:

- For ongoing CFAR+sidelobe calibration, prefer:
  - core `0.52|1,6,6|0,1,1|1.1`
  - radius `1,12,12`
  - floor `0.85` (slightly better CFAR+sidelobe quality and runtime-normalized ranking)
- Keep this branch local-only until a full-length visible-test run confirms net value under notebook runtime limits and does not regress the v9 leaderboard anchor.


## 2026-07-03 - 100tp Stability Check (Best CFAR+Side-Lobe Setting)

Purpose: run a longer stability pass on the two hard train samples using the current best CFAR+sidelobe setting.

Setup:

- samples: `44b6_40c45f5a`, `6bba_05db0fb1`
- timepoints: first 100
- sweep spec: `0.52|1,6,6|0,1,1|1.1|1,12,12|0.85`
- linker: `motion_mutual`, radius 9.0 um

Artifacts:

- `submissions/cfar_sidelobe_best_100tp.json`
- `submissions/cfar_sidelobe_best_100tp_summary.json`

Per-sample highlights:

- `44b6_40c45f5a`
  - local-max baseline: sparse recall `0.9650`, sparse edge recall `0.6919`
  - cfar: sparse recall `0.8850`, sparse edge recall `0.6708`
  - cfar+sidelobe: sparse recall `0.8750`, sparse edge recall `0.6962`
- `6bba_05db0fb1`
  - local-max baseline: sparse recall `0.4207`, sparse edge recall `0.6843`
  - cfar: sparse recall `0.5932`, sparse edge recall `0.6995`
  - cfar+sidelobe: sparse recall `0.5883`, sparse edge recall `0.7176`

Top-ranked strategies at 100tp (`quality_per_second`):

| rank | strategy | mean quality score | quality per second |
|---:|---|---:|---:|
| 1 | local_maxima_baseline + `sr1,12,12 sf0.85` | 0.6905 | 0.0130 |
| 2 | cfar_sidelobe + `sr1,12,12 sf0.85` | 0.7193 | 0.0051 |
| 3 | cfar + `sr1,12,12 sf0.85` | 0.7121 | 0.0048 |

Interpretation:

- Quality-first ordering remains `cfar_sidelobe > cfar > local_max` on this hard pair.
- Runtime-normalized ordering remains `local_max > cfar_sidelobe > cfar`.
- At 100tp, sidelobe remains net-positive versus plain CFAR on edge continuity while staying slightly faster.


## 2026-07-03 - Bounded Visible-Test Calibration (CFAR+Side-Lobe, 50tp)

Purpose: run the same best CFAR+sidelobe setting on visible test as a bounded calibration pass and compare runtime envelope to the v9 anchor path.

Implementation:

- Added script: `scripts/run_cfar_visible_submission.py`
- This runner streams visible-test `.zarr`, builds CFAR+sidelobe graphs with fixed settings, writes Kaggle-format CSV, and emits per-sample runtime report + aggregate summary.

Run setup:

- input: `test/` (4 visible samples)
- timepoints: first 50 (bounded)
- detector: `threshold=0.52`, CFAR `tr1,6,6 gr0,1,1 k1.1`, sidelobe `sr1,12,12 sf0.85`
- linker: `motion_mutual`, radius 9.0 um

Artifacts:

- `submissions/visible_test_v12_cfar_sidelobe_submission.csv`
- `submissions/visible_test_v12_cfar_sidelobe_report.json`
- `submissions/visible_test_v12_cfar_sidelobe_summary.json`

Bounded visible-test output summary (50tp):

- total elapsed: `285.79s`
- total predicted nodes: `81,416`
- total predicted edges: `54,870`
- mean nodes/sec: `274.02`
- mean edges/sec: `184.60`

v9 envelope comparison (using `submissions/visible_test_v9_motion_mutual_report.json`):

- v9 full visible-test totals: elapsed `240.69s`, nodes `143,623`, edges `95,090`
- v9 aggregate throughput: `596.71` nodes/sec, `395.07` edges/sec
- v12 bounded CFAR+sidelobe throughput: `284.88` nodes/sec, `191.99` edges/sec

Interpretation:

- The bounded CFAR+sidelobe path is currently much heavier than the v9 anchor path in throughput terms.
- Using a rough per-sample-per-timepoint proxy (assuming v9 report is full 100tp):
  - v9: about `0.60s` per sample-timepoint
  - v12 bounded: about `1.43s` per sample-timepoint
  - bounded CFAR+sidelobe is about `2.37x` slower
- Branch remains calibration-only; do not promote to official submission routing yet.


## 2026-07-03 - Runtime Squeeze + Merged-Heavy 100tp Rerun (Both)

Purpose: execute both requested follow-ups together:

- runtime squeeze on bounded visible-test CFAR+sidelobe calibration
- 100tp rerun on merged-heavy visible samples only

### Runtime squeeze trials (visible test, 50tp)

To support targeted runs, `scripts/run_cfar_visible_submission.py` was extended with:

- `--sample-ids` (explicit sample filtering)
- `--max-detections-per-timepoint` (optional detector output cap)

Trial A (lighter CFAR neighborhood):

- config: `thr0.52 tr1,4,4 gr0,1,1 k1.0 sr1,8,8 sf0.85`
- artifacts:
  - `submissions/visible_test_v13a_cfar_sidelobe_submission.csv`
  - `submissions/visible_test_v13a_cfar_sidelobe_report.json`
  - `submissions/visible_test_v13a_cfar_sidelobe_summary.json`
- summary: elapsed `444.80s`, nodes `84,238`, edges `56,472`, throughput `189.38` nodes/s and `126.96` edges/s

Trial B (same v12 params + candidate cap):

- config: v12 detector params + `--max-detections-per-timepoint 900`
- artifacts:
  - `submissions/visible_test_v13b_cfar_sidelobe_cap_submission.csv`
  - `submissions/visible_test_v13b_cfar_sidelobe_cap_report.json`
  - `submissions/visible_test_v13b_cfar_sidelobe_cap_summary.json`
- summary: elapsed `279.84s`, nodes `81,416`, edges `54,870`, throughput `290.94` nodes/s and `196.08` edges/s

Observed deltas vs v12 bounded run:

- v13a is slower by `+159.01s` and not a runtime improvement
- v13b is faster by `-5.95s`
- v13b kept node/edge totals identical to v12 (`81,416` / `54,870`)

Runtime-squeeze interpretation:

- The lighter neighborhood trial (v13a) underperformed runtime-wise on this hardware/data mix.
- Candidate cap at 900 (v13b) gave a small but clean runtime win without changing aggregate output volume.
- Keep v13b as the preferred bounded CFAR+sidelobe calibration profile.

### Merged-heavy visible rerun (100tp, 2 samples)

Run:

- sample IDs: `44b6_0b24845f`, `6bba_05db0fb1`
- timepoints: first 100
- config: `thr0.52 tr1,6,6 gr0,1,1 k1.1 sr1,12,12 sf0.85`
- linker: `motion_mutual`, radius 9.0 um

Artifacts:

- `submissions/visible_test_v13_merged2_100tp_cfar_sidelobe_submission.csv`
- `submissions/visible_test_v13_merged2_100tp_cfar_sidelobe_report.json`
- `submissions/visible_test_v13_merged2_100tp_cfar_sidelobe_summary.json`

Summary:

- total elapsed: `296.57s`
- total predicted nodes: `142,169`
- total predicted edges: `92,859`
- mean nodes/sec: `478.28`
- mean edges/sec: `313.01`

Per-sample highlights:

- `44b6_0b24845f`: `82,209` nodes, `48,048` edges, `150.69s`
- `6bba_05db0fb1`: `59,960` nodes, `44,811` edges, `145.88s`

Decision update:

- For local CFAR+sidelobe calibration, use v13b-style bounded profile first (same best detector params, cap 900).
- Keep CFAR+sidelobe outside official submission routing until throughput approaches the v9 envelope with stable quality evidence.


## 2026-07-03 - Cap Sweep (700/800/900/1000) on Bounded Visible-Test CFAR+Side-Lobe

Purpose: pick the best runtime/volume knee for bounded visible-test calibration under the fixed best detector settings.

Fixed settings:

- detector: `thr0.52 tr1,6,6 gr0,1,1 k1.1 sr1,12,12 sf0.85`
- linker: `motion_mutual`, radius 9.0 um
- window: first 50 timepoints
- samples: all 4 visible test samples

Artifacts:

- `submissions/visible_test_v13_cap700_summary.json`
- `submissions/visible_test_v13_cap800_summary.json`
- `submissions/visible_test_v13_cap900_summary.json`
- `submissions/visible_test_v13_cap1000_summary.json`

Cap sweep summary (vs v12 bounded baseline):

| cap | elapsed s | nodes | edges | elapsed delta vs v12 | node delta vs v12 | edge delta vs v12 |
|---:|---:|---:|---:|---:|---:|---:|
| v12 (no cap) | 285.79 | 81,416 | 54,870 | 0.00 | 0 | 0 |
| 700 | 280.52 | 77,088 | 51,549 | -5.27 | -4,328 | -3,321 |
| 800 | 278.64 | 81,031 | 54,646 | -7.15 | -385 | -224 |
| 900 | 284.57 | 81,416 | 54,870 | -1.22 | 0 | 0 |
| 1000 | 362.43 | 81,416 | 54,870 | +76.64 | 0 | 0 |

Interpretation:

- `cap=800` is the best knee observed here: fastest total runtime with only a very small output-volume reduction relative to v12.
- `cap=900` is conservative (identical output counts) but gives less speedup than 800.
- `cap=700` trims too much output volume for the runtime gained.
- `cap=1000` is materially worse on runtime in this run and should be avoided.

Decision update:

- For bounded visible-test CFAR+sidelobe calibration, prefer `--max-detections-per-timepoint 800` as the new default trial cap.
- Keep `cap=900` as fallback when strict output-volume preservation is required.


## 2026-07-03 - Cap 800 vs 900 on Merged-Heavy 100tp Probe

Purpose: test whether the broad cap-800 knee also holds on the two merged-heavy visible samples, or whether cap 900 is safer for submission-candidate probing.

Fixed settings:

- samples: `44b6_0b24845f`, `6bba_05db0fb1`
- timepoints: first 100
- detector: `thr0.52 tr1,6,6 gr0,1,1 k1.1 sr1,12,12 sf0.85`
- linker: `motion_mutual`, radius 9.0 um

Artifacts:

- `submissions/visible_test_v15_merged2_cap800_100tp_submission.csv`
- `submissions/visible_test_v15_merged2_cap800_100tp_report.json`
- `submissions/visible_test_v15_merged2_cap800_100tp_summary.json`
- `submissions/visible_test_v15_merged2_cap900_100tp_submission.csv`
- `submissions/visible_test_v15_merged2_cap900_100tp_report.json`
- `submissions/visible_test_v15_merged2_cap900_100tp_summary.json`

Head-to-head summary:

| cap | elapsed s | nodes | edges | rows |
|---:|---:|---:|---:|---:|
| 800 | 289.98 | 132,044 | 86,526 | 218,570 |
| 900 | 287.94 | 136,142 | 89,024 | 225,166 |

Interpretation:

- On the merged-heavy 100tp pair, cap 900 is slightly faster and preserves more output volume than cap 800.
- This differs from the broad 50tp visible sweep, where cap 800 was the best runtime/volume knee.
- The difference likely reflects sample composition: cap 800 is a broad calibration default, while cap 900 is better for merged-heavy submission-candidate probes.

Operating policy:

- Use `cap=800` as the default for broad bounded CFAR+sidelobe calibration.
- Use `cap=900` only when probing merged-heavy submission candidates or when output-volume preservation matters more than the small broad-sweep runtime gain.
- Do not promote CFAR+sidelobe to official submission routing yet. The full visible 100tp cap-800 path remained about `2.36x` slower than the v9 anchor envelope.

Submission readiness gate:

- A CFAR+sidelobe candidate should not be submitted until it satisfies both:
  - sparse-train quality remains at or above the current hard-sample cap-800/cap-900 evidence band
  - full visible-test runtime is close enough to the v9 anchor envelope to avoid notebook-limit risk


## 2026-07-03 - Cap 900 Full-Gate Calibration

Purpose: continue calibration patiently by testing cap 900 on both sparse-labeled hard train samples and the full visible-test 100tp runtime envelope.

Fixed settings:

- detector: `thr0.52 tr1,6,6 gr0,1,1 k1.1 sr1,12,12 sf0.85`
- linker: `motion_mutual`, radius 9.0 um
- cap: `--max-detections-per-timepoint 900`

Artifacts:

- `submissions/cfar_sidelobe_cap900_100tp.json`
- `submissions/cfar_sidelobe_cap900_100tp_summary.json`
- `submissions/visible_test_v16_cap900_submission.csv`
- `submissions/visible_test_v16_cap900_report.json`
- `submissions/visible_test_v16_cap900_summary.json`

Hard-train sparse comparison (`cfar_sidelobe`, 100tp hard pair):

| cap | elapsed s | nodes | edges | mean sparse recall | mean sparse edge recall | mean quality |
|---:|---:|---:|---:|---:|---:|---:|
| 800 | 280.82 | 96,695 | 70,765 | 0.7316 | 0.7077 | 0.7197 |
| 900 | 278.99 | 96,699 | 70,770 | 0.7316 | 0.7069 | 0.7193 |

Full visible-test 100tp comparison:

| cap | elapsed s | nodes | edges | rows |
|---:|---:|---:|---:|---:|
| 800 | 568.28 | 158,488 | 107,914 | 266,402 |
| 900 | 562.64 | 162,586 | 110,412 | 272,998 |

Interpretation:

- Cap 900 is slightly faster than cap 800 on the full visible-test 100tp run and preserves more output volume.
- Cap 800 is slightly stronger on sparse hard-train mean edge recall and mean quality, but by a very small margin.
- Neither cap is ready for official submission routing because full visible-test runtime remains far slower than the v9 anchor envelope.

Current policy update:

- Keep `cap=800` as the broad calibration default where sparse-quality caution is prioritized.
- Use `cap=900` for merged-heavy and submission-candidate probes where output-volume preservation is prioritized.
- Do not submit CFAR+sidelobe yet.


## 2026-07-03 - Hybrid Routing Prototype (v9 Clean Samples + CFAR Side-Lobe Merged Samples)

Purpose: address the runtime blocker by routing only merged-foreground samples through CFAR+sidelobe while keeping clean samples on the adaptive baseline path.

Implementation:

- Added `scripts/run_hybrid_submission.py`.
- Router uses existing image-only adaptive foreground profile:
  - clean compact foreground -> adaptive baseline (`components`, greedy, v9-style clean path)
  - merged/high-foreground samples -> CFAR+sidelobe (`cap=900`, `motion_mutual`)
- This preserves the core boundary: CFAR is used only where foreground structure justifies the extra cost.

20tp smoke artifacts:

- `submissions/visible_test_hybrid_smoke20_submission.csv`
- `submissions/visible_test_hybrid_smoke20_report.json`
- `submissions/visible_test_hybrid_smoke20_summary.json`

20tp smoke result:

- route counts: `adaptive_baseline=2`, `cfar_sidelobe=2`
- total elapsed: `72.14s`
- total nodes: `31,585`
- total edges: `20,867`
- routing matched expectation:
  - `44b6_0113de3b`, `6bba_05b6850b` -> adaptive baseline
  - `44b6_0b24845f`, `6bba_05db0fb1` -> CFAR+sidelobe

Full visible-test 100tp artifacts:

- `submissions/visible_test_v17_hybrid_cap900_submission.csv`
- `submissions/visible_test_v17_hybrid_cap900_report.json`
- `submissions/visible_test_v17_hybrid_cap900_summary.json`

Full visible-test 100tp summary:

- total elapsed: `349.12s`
- total nodes: `161,477`
- total edges: `110,190`
- total rows: `271,667`
- route counts: `adaptive_baseline=2`, `cfar_sidelobe=2`

Comparison:

| path | elapsed s | nodes | edges | rows |
|---|---:|---:|---:|---:|
| v9 anchor | 240.69 | 143,623 | 95,090 | 238,713 |
| full CFAR+sidelobe cap900 | 562.64 | 162,586 | 110,412 | 272,998 |
| hybrid cap900 | 349.12 | 161,477 | 110,190 | 271,667 |

Deltas:

- Hybrid vs full CFAR+sidelobe:
  - elapsed: `-213.52s`
  - nodes: `-1,109`
  - edges: `-222`
- Hybrid vs v9 anchor:
  - elapsed: `+108.43s` (`1.45x` v9 runtime)
  - nodes: `+17,854`
  - edges: `+15,100`

Interpretation:

- Hybrid routing is the first CFAR branch that looks structurally plausible: it preserves nearly all full-CFAR output volume while cutting runtime substantially.
- It is still not ready for official submission because runtime remains about `1.45x` the v9 visible-test envelope, and output expansion still needs sparse-quality justification.
- Next calibration should compare hybrid cap900 against v9 on sparse-labeled train samples using the same image-only router, not just visible-test counts.


## 2026-07-03 - Hybrid vs v9-Style Sparse Train Gate (Hard Pair, 100tp)

Purpose: test whether hybrid's visible-test output expansion is supported by sparse-label quality evidence on the two hard train samples.

Implementation:

- Added `scripts/run_hybrid_train_evaluation.py`.
- Comparator routes:
  - `v9_style_adaptive`: image-only adaptive routing with merged samples using `local_maxima + motion_mutual`
  - `hybrid_cfar_sidelobe`: same image-only router, but merged samples use CFAR+sidelobe cap900

Artifacts:

- `submissions/train_hardpair_hybrid_cap900_eval.json`
- `submissions/train_hardpair_hybrid_cap900_eval_summary.json`

Summary:

| route | elapsed s | nodes | edges | mean sparse recall | mean sparse edge recall | mean quality | quality/sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| v9_style_adaptive | 173.92 | 77,835 | 56,684 | 0.6928 | 0.6881 | 0.6905 | 0.00794 |
| hybrid_cfar_sidelobe | 483.38 | 96,699 | 70,770 | 0.7316 | 0.7069 | 0.7193 | 0.00298 |

Per-sample interpretation:

- `44b6_40c45f5a`:
  - hybrid regressed sparse recall (`0.9650 -> 0.8750`) while only slightly improving sparse edge recall (`0.6919 -> 0.6962`)
  - this sample does not justify CFAR replacement
- `6bba_05db0fb1`:
  - hybrid improved sparse recall (`0.4207 -> 0.5883`) and sparse edge recall (`0.6843 -> 0.7176`)
  - this sample does justify selective CFAR exploration

Decision:

- Hybrid cap900 has real quality signal, but it is not uniformly positive across merged samples.
- Do not submit yet.
- Next calibration should split merged routing more finely: keep v9-style local maxima for `44b6`-like merged samples, and route only dim/dense `6bba`-like samples to CFAR+sidelobe.


## 2026-07-03 - Refined Hybrid Router: CFAR Only for Merged 6bba-Like Samples

Purpose: implement the sample-family split suggested by the hard-pair sparse gate:

- keep v9-style local maxima for `44b6` merged samples
- route only merged `6bba` samples through CFAR+sidelobe cap900

Implementation update:

- `scripts/run_hybrid_submission.py` now supports `--cfar-route-policy`:
  - `merged_all`
  - `merged_6bba_only`
- `scripts/run_hybrid_train_evaluation.py` supports the same policy.
- Corrected fallback behavior so merged samples not routed to CFAR use v9-style `motion_mutual`, not latent recovery.

Corrected sparse hard-pair gate artifacts:

- `submissions/train_hardpair_hybrid_6bbaonly_cap900_eval_rerun.json`
- `submissions/train_hardpair_hybrid_6bbaonly_cap900_eval_rerun_summary.json`

Sparse hard-pair summary:

| route | elapsed s | nodes | edges | mean sparse recall | mean sparse edge recall | mean quality | quality/sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| v9_style_adaptive | 98.77 | 77,835 | 56,684 | 0.6928 | 0.6881 | 0.6905 | 0.01398 |
| hybrid 6bba-only | 188.48 | 94,026 | 69,045 | 0.7766 | 0.7048 | 0.7407 | 0.00786 |

Per-sample behavior:

- `44b6_40c45f5a` is identical to v9-style routing:
  - sparse recall `0.9650`
  - sparse edge recall `0.6919`
- `6bba_05db0fb1` gets the intended CFAR rescue:
  - sparse recall `0.4207 -> 0.5883`
  - sparse edge recall `0.6843 -> 0.7176`

Full visible-test 100tp artifacts:

- `submissions/visible_test_v18_hybrid_6bbaonly_cap900_submission.csv`
- `submissions/visible_test_v18_hybrid_6bbaonly_cap900_report.json`
- `submissions/visible_test_v18_hybrid_6bbaonly_cap900_summary.json`

Full visible-test comparison:

| path | elapsed s | nodes | edges | rows |
|---|---:|---:|---:|---:|
| v9 anchor | 240.69 | 143,623 | 95,090 | 238,713 |
| hybrid all-merged | 349.12 | 161,477 | 110,190 | 271,667 |
| hybrid 6bba-only | 251.90 | 159,814 | 107,451 | 267,265 |

Deltas:

- Hybrid 6bba-only vs v9:
  - elapsed: `+11.21s` (`1.047x` v9 runtime)
  - nodes: `+16,191`
  - edges: `+12,361`
- Hybrid 6bba-only vs all-merged hybrid:
  - elapsed: `-97.22s`
  - nodes: `-1,663`
  - edges: `-2,739`

Interpretation:

- This is the closest branch to a submission candidate so far.
- It keeps runtime close to the v9 visible-test envelope while preserving most of the useful CFAR output expansion.
- Sparse hard-pair evidence supports the routing split: do not apply CFAR to `44b6` merged samples, but do apply it to the difficult `6bba_05db0fb1`-like case.

Readiness:

- Near-candidate, but still not submitted yet.
- Final gate before considering submission should be a CSV/schema sanity check plus one rerun or checksum-style confirmation of the v18 artifact.


## 2026-07-03 - Final Gate: v18 CSV Sanity + v19 Reproducibility Rerun

Purpose: run the two final checks before treating refined hybrid `merged_6bba_only` cap900 as a serious submission candidate.

Candidate policy:

- script: `scripts/run_hybrid_submission.py`
- route policy: `--cfar-route-policy merged_6bba_only`
- CFAR cap: `--max-detections-per-timepoint 900`
- full visible window: first 100 timepoints

Gate 1: CSV/schema/reference sanity check on v18

- artifact checked: `submissions/visible_test_v18_hybrid_6bbaonly_cap900_submission.csv`
- rows: `267,265`
- nodes: `159,814`
- edges: `107,451`
- datasets:
  - `44b6_0113de3b`
  - `44b6_0b24845f`
  - `6bba_05b6850b`
  - `6bba_05db0fb1`
- result: pass
  - expected columns present
  - zero-based contiguous `id`
  - row counts match summary artifact
  - edge source/target references resolve within each dataset
  - no malformed row types found

Gate 2: reproducibility rerun

- rerun artifacts:
  - `submissions/visible_test_v19_hybrid_6bbaonly_cap900_submission.csv`
  - `submissions/visible_test_v19_hybrid_6bbaonly_cap900_report.json`
  - `submissions/visible_test_v19_hybrid_6bbaonly_cap900_summary.json`
- v19 summary:
  - elapsed: `251.76s`
  - nodes: `159,814`
  - edges: `107,451`
  - rows: `267,265`
  - route counts: `adaptive_baseline=2`, `v9_style_adaptive=1`, `cfar_sidelobe=1`

CSV checksum comparison:

| artifact | SHA256 |
|---|---|
| v18 submission CSV | `ED1C87ECD5140B1404ADFD8ABA733E8BB54A0A06CE4D1C18F75A7E08ECD4DDB9` |
| v19 submission CSV | `ED1C87ECD5140B1404ADFD8ABA733E8BB54A0A06CE4D1C18F75A7E08ECD4DDB9` |

Decision:

- The refined hybrid `merged_6bba_only` cap900 branch passes the local final gates.
- It is now a serious submission candidate.
- It should be submitted only with the explicit understanding that sparse labels are partial and visible-test runtime/output are proxy evidence, not the official metric.


## 2026-07-03 - Kaggle Kernel Packaging Gate and Push

Purpose: ensure `kaggle_kernel/run.py` contains the same refined hybrid policy as v19 before pushing to Kaggle.

Kernel updates:

- Ported CFAR+sidelobe detector into the self-contained Kaggle script.
- Added refined routing:
  - clean samples: adaptive component baseline
  - merged `44b6_*`: v9-style local maxima + `motion_mutual`
  - merged `6bba_*`: CFAR+sidelobe cap900 + `motion_mutual`

Local package validation:

- one-timepoint smoke test passed all four visible samples and routed as expected
- full local kernel run wrote `267,265` rows
- full local kernel output hash matched the validated v19 artifact exactly:
  - `submissions/visible_test_v19_hybrid_6bbaonly_cap900_submission.csv`
  - `submissions/kernel_v19_candidate_full.csv`
  - SHA256: `ED1C87ECD5140B1404ADFD8ABA733E8BB54A0A06CE4D1C18F75A7E08ECD4DDB9`

Push:

- command: `kaggle kernels push -p kaggle_kernel`
- result: Kernel version 12 successfully pushed
- Kaggle page: `https://www.kaggle.com/code/drakus74/atabey-adaptive-baseline`

Metadata note:

- Added a local `description` field to `kaggle_kernel/kernel-metadata.json` describing the refined hybrid v12 policy and byte-for-byte v19 packaging validation.
- The installed Kaggle CLI accepts the field in JSON, but its kernel push request only sends title/code/settings, not description/subtitle.
- The visible Kaggle page description may therefore need to be set through the authenticated Kaggle web UI.

Private rerun note:

- Competition scoring privately reruns the selected notebook version with hidden test data substituted into the competition dataset, then extracts the chosen output file.
- Pulled completed v12 Kaggle output with `kaggle kernels output drakus74/atabey-adaptive-baseline -p kaggle_kernel/remote_output_v12`.
- Confirmed Kaggle v12 wrote `/kaggle/working/submission.csv` and `adaptive_runtime_report.json`.
- Confirmed visible-test Kaggle output CSV matched the local validated v19 CSV exactly:
  - `submissions/visible_test_v19_hybrid_6bbaonly_cap900_submission.csv`
  - `kaggle_kernel/remote_output_v12/submission.csv`
  - SHA256: `ED1C87ECD5140B1404ADFD8ABA733E8BB54A0A06CE4D1C18F75A7E08ECD4DDB9`

Implication:

- For official scoring, select kernel version 12 and choose `submission.csv` as the output file.
- The visible-test output is verified, but hidden-test behavior still depends on the same script routing correctly over substituted hidden `.zarr` samples within Kaggle's runtime limit.


## 2026-07-04 - Slow-Variant Probe (Cap 1200) vs Candidate Cap 900

Purpose: test the hypothesis that allowing slower CFAR routing (higher candidate cap) might improve hidden-test quality, even at higher runtime risk.

Policy under test:

- script: `scripts/run_hybrid_submission.py`
- route policy: `--cfar-route-policy merged_6bba_only`
- only change: CFAR cap `900 -> 1200`

Visible-test comparison (100tp):

- cap900 reference: `submissions/visible_test_v19_hybrid_6bbaonly_cap900_summary.json`
  - elapsed `251.76s`
  - nodes `159,814`
  - edges `107,451`
  - rows `267,265`
- cap1200 probe: `submissions/visible_test_v20_hybrid_6bbaonly_cap1200_summary.json`
  - elapsed `349.58s`
  - nodes `159,814`
  - edges `107,451`
  - rows `267,265`

CSV identity check:

| artifact | SHA256 |
|---|---|
| v19 cap900 CSV | `ED1C87ECD5140B1404ADFD8ABA733E8BB54A0A06CE4D1C18F75A7E08ECD4DDB9` |
| v20 cap1200 CSV | `ED1C87ECD5140B1404ADFD8ABA733E8BB54A0A06CE4D1C18F75A7E08ECD4DDB9` |

Interpretation:

- Cap 1200 produced a byte-identical submission file to cap 900.
- Runtime increased by `+97.82s` (about `+38.9%`) with no node/edge/count gain.

Sparse train hard-sample sequential check (`6bba_05db0fb1`, 100tp):

- cap900 (`submissions/train_6bba_hybrid_6bbaonly_cap900_seq_eval_summary.json`):
  - elapsed `175.79s`
  - sparse recall `0.5883`
  - sparse edge recall `0.7176`
  - quality `0.6530`
- cap1200 (`submissions/train_6bba_hybrid_6bbaonly_cap1200_seq_eval_summary.json`):
  - elapsed `261.47s`
  - sparse recall `0.5883`
  - sparse edge recall `0.7176`
  - quality `0.6530`

Decision:

- Do not submit a slower cap1200 variant.
- For the current refined hybrid route, cap 900 is strictly better operationally: same predictions, lower runtime, lower timeout risk.


## 2026-07-04 - Profile-Based Routing + Guardrail + Tight 6bba Sweep Winner

Purpose: replace prefix-based routing with image-profile gating, add a CFAR spike guardrail fallback, and select the best nearby CFAR parameters from a narrow 6bba-only sweep.

Routing change:

- `merged_6bba_only` now routes by foreground profile, not sample-id prefix.
- CFAR is used only for merged/dim profiles in the observed 6bba-like range.
- If per-timepoint CFAR detections spike beyond a recent-median-based limit, the runner falls back to the local-maxima detector for that frame.

Guardrail details:

- fallback trigger uses recent CFAR counts over a short history window
- fallback detector: local maxima with `threshold=0.65`, `min_distance_voxels=(1, 5, 5)`
- purpose: prevent CFAR explosions from dominating runtime or output volume

Tight 6bba-only sparse sweep (`6bba_05db0fb1`, 100tp, cap900, merged_6bba_only):

| variant | threshold | k-sigma | sparse recall | sparse edge recall | quality | elapsed s |
|---|---:|---:|---:|---:|---:|---:|
| `thr050_k11` | 0.50 | 1.1 | 0.6298 | 0.7278 | 0.6788 | 211.45 |
| `thr052_k10` | 0.52 | 1.0 | 0.5891 | 0.7181 | 0.6536 | 197.07 |
| `base_t052_k11` | 0.52 | 1.1 | 0.5883 | 0.7176 | 0.6530 | 196.11 |
| `thr052_k12` | 0.52 | 1.2 | 0.5883 | 0.7176 | 0.6530 | 145.68 |
| `thr054_k11` | 0.54 | 1.1 | 0.5598 | 0.7231 | 0.6415 | 244.10 |

Visible-test confirmation for the new winner:

- artifact: `submissions/visible_test_v22_hybrid_profile_thr050_k11_cap900_submission.csv`
- total elapsed: `251.31s`
- total predicted nodes: `162,820`
- total predicted edges: `109,696`
- total rows: `272,516`
- route counts: `adaptive_baseline=2`, `v9_style_adaptive=1`, `cfar_sidelobe=1`
- CSV hash differs from the previous profile-based cap900 candidate, so this is a real change rather than a no-op

Decision:

- Keep the profile-based router and guardrail fallback.
- Promote `cfar_threshold=0.50`, `cfar_k_sigma=1.1`, `sidelobe_floor=0.85`, cap900 as the new default refined hybrid setting.
- Cap1200 remains rejected: no output gain, worse runtime.
