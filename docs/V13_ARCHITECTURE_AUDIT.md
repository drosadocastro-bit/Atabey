# V13 Full Architecture Audit — Why It Works

Status: completed (read-only audit).

This document audits the frozen V13 path end-to-end. It explains why V13 has remained robust against successive challenger branches, and where latent risks still exist.

## Scope and Guardrail

- This is a documentation-only pass.
- No code-path modifications were made.
- V13 frozen defaults are read from src/atabey/hybrid_config.py.

## 1) Full Pipeline Trace (Frozen V13)

### 1.1 Entry and routing

Primary runtime path is scripts/run_hybrid_submission.py:

1. discover_zarr_samples(...) enumerates sample directories.
2. build_hybrid_graph_for_sample(...) profiles each sample via choose_settings_for_sample(...).
3. Route gate applies cfar_route_policy=merged_6bba_only:
   - only adaptive local_maxima samples with 6bba-like merged profile are routed to CFAR+sidelobe,
   - otherwise path falls back to adaptive baseline graph builder.

Frozen values (src/atabey/hybrid_config.py):

- cfar_threshold: 0.50
- cfar_training_radius_voxels: (1, 6, 6)
- cfar_guard_radius_voxels: (0, 1, 1)
- cfar_threshold_mode: sigma
- cfar_k_sigma: 1.1
- cfar_pfa: 1e-4 (configured but inactive while mode=sigma)
- sidelobe_mode: isotropic
- sidelobe_radius_voxels: (1, 12, 12)
- sidelobe_floor_ratio: 0.85
- max_detections_per_timepoint: 900
- cfar_route_policy: merged_6bba_only
- cfar_link_strategy: motion_mutual
- cfar_max_link_distance_um: 9.0

Guardrail defaults:

- spike_multiplier: 1.8
- min_history: 6
- history_window: 12
- min_absolute_count: 1200
- fallback_threshold: 0.65

Safety relative to challenger branches:

- V13 uses sigma mode (bounded normalized-domain compatible) and does not rely on pfa mode in production.
- V13 keeps isotropic sidelobe suppression (axial path is experimental and parked by gate).
- V13 constrains CFAR routing to merged_6bba_only, preventing broad spillover into already-clean regions.

### 1.2 Zarr ingestion and timepoint streaming

Functions:

- open_competition_array(...) in src/atabey/io/zarr_reader.py
- read_timepoint(array, t) for per-frame streaming

Behavior:

- One timepoint is read at a time; no full 4D load is required.
- This keeps memory bounded and stage costs explicit.

Safety:

- Streaming-first processing avoids large-state side effects and supports stable reproducibility.

### 1.3 Detection (CFAR sigma route)

Functions:

- threshold_local_maxima_cfar_sidelobe(...)
- threshold_local_maxima_cfar(...)
- _cfar_background_stats_box(...)

Behavior:

1. robust_normalize(...) maps frame intensities to [0,1].
2. Local maxima candidates are computed.
3. CFAR adaptive threshold in sigma mode is applied:
   adaptive_threshold = bg_mean + k_sigma * bg_std.
4. Global floor threshold (0.50) is jointly enforced.

Safety:

- Sigma mode avoids dependence on unbounded CA-CFAR alpha scaling assumptions that were problematic in pfa mode experiments.
- Combined global floor + local adaptive gate is conservative in dense/high-background regions.

### 1.4 Sidelobe suppression

Behavior:

- isotropic sidelobe suppression with radius (1,12,12), floor ratio 0.85.
- weaker nearby peaks are suppressed relative to stronger retained peaks.

Safety:

- This reduces local duplicate/near-duplicate candidates before linking.
- The production path does not use axial suppression defaults that were part of parked experimental combinations.

### 1.5 Guardrail fallback

Behavior in build_graph_cfar_sidelobe(...):

- Tracks recent detection counts.
- If counts spike over median-window baseline * multiplier (and absolute floor), switches that frame to fallback threshold_local_maxima(...) at threshold 0.65.

Safety:

- Prevents runaway over-detection in transient high-noise frames.
- Adds bounded fail-safe behavior without changing global route policy.

### 1.6 Coordinate normalization and physical units

Detection coordinates are converted with DEFAULT_VOXEL_SCALE_UM:

- z: 1.625 um
- y: 0.40625 um
- x: 0.40625 um

Safety:

- Linking operates in physical microns rather than raw voxel indices, reducing anisotropy bias and improving spatial consistency.

### 1.7 Temporal linking and lineage graph construction

Functions:

- link_adjacent_timepoints(..., strategy=motion_mutual)
- link_adjacent_timepoints_motion_mutual(...)

Behavior:

- Adjacent-frame only links (t -> t+1).
- Motion-predicted nearest target is accepted only if mutual nearest identity gate agrees.
- One-to-one greedy assignment finalizes edges.

Safety:

- No production frame-skip injection in V13 path.
- This avoids the direct-link vs frame-skip competition failure mode that surfaced in kinematic soft-linking experiments.

### 1.8 Submission writer

Functions:

- graph_to_submission_rows(...)
- write_submission(...)

Behavior:

- Internal string node IDs are remapped to stable per-dataset integer IDs.
- Edge rows reference exported node IDs.
- Output schema matches Kaggle columns.

Safety:

- Clean separation between internal tracking IDs and export schema avoids coupling errors.

### 1.9 Disabled-by-default experimental layers in V13 state

In frozen V13 path these are OFF:

- correlation recovery (default false)
- latent shadow (default false)
- mitosis shadow (default false)
- unsafe pfa+axial combination (blocked unless explicitly overridden)

Safety:

- Keeps production behavior narrow and auditable.

## 2) Cohort-wide V13 behavior (full train)

Full-cohort route and metric distributions were generated to:

- submissions/v13_architecture_audit_fulltrain_eval.json
- submissions/v13_architecture_audit_fulltrain_eval_summary.json

Known full-train route exposure baseline from submissions/cfar_bounded_scan_fulltrain.json:

- total samples: 199
- samples routing to CFAR profile class: 66 (33.17%)
- samples outside CFAR profile class: 133 (66.83%)

Interpretation:

- Roughly one-third of full-train samples are exposed to CFAR-specific behavior.
- Roughly two-thirds ride non-CFAR adaptive behavior, limiting global impact of CFAR-only failure modes.

Route definitions in this section:

- adaptive_baseline: hybrid records where detector is not cfar_sidelobe
- cfar_sidelobe: hybrid records where detector is cfar_sidelobe

### 2.1 Route exposure and runtime

| route | samples | cohort fraction | mean runtime (s) | median runtime (s) | p90 runtime (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| adaptive_baseline | 133 | 66.83% | 60.62 | 59.55 | 84.44 |
| cfar_sidelobe | 66 | 33.17% | 207.65 | 227.72 | 251.25 |

Takeaway: the CFAR route is a minority of samples but has much higher per-sample runtime cost.

### 2.2 Quality distributions by route

| route | metric | mean | median | p10 | p90 | min | max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_baseline | quality_score | 0.7816 | 0.8143 | 0.6056 | 0.9173 | 0.3320 | 0.9962 |
| adaptive_baseline | sparse_recall | 0.7366 | 0.8038 | 0.4291 | 0.9421 | 0.0529 | 1.0000 |
| adaptive_baseline | sparse_edge_recall | 0.8266 | 0.8500 | 0.6378 | 0.9605 | 0.3651 | 1.0000 |
| cfar_sidelobe | quality_score | 0.7304 | 0.7460 | 0.6062 | 0.8739 | 0.3021 | 0.9508 |
| cfar_sidelobe | sparse_recall | 0.7697 | 0.8045 | 0.5712 | 0.9487 | 0.1213 | 0.9860 |
| cfar_sidelobe | sparse_edge_recall | 0.6911 | 0.6937 | 0.5416 | 0.8606 | 0.4286 | 0.9512 |

Takeaway: CFAR-route node recall is competitive, but edge recall is materially lower than adaptive-baseline route, which explains lower overall quality_score despite strong detection coverage in dense scenes.

### 2.3 Node and edge load (inflation view)

Node inflation metric uses predicted_to_estimated_node_ratio from sparse evaluator.

| route | node inflation mean | node inflation median | p10 | p90 |
| --- | ---: | ---: | ---: | ---: |
| adaptive_baseline | 0.8517 | 0.8178 | 0.5736 | 1.1675 |
| cfar_sidelobe | 1.1952 | 1.1328 | 0.9228 | 1.5416 |

Edge-load proxies (because sparse edge denominator is not directly emitted in TrainHybridEvalRecord):

- edges_per_predicted_node is similar across routes (adaptive mean 0.7055, CFAR mean 0.7040).
- edges_per_sparse_node is much higher on CFAR route (adaptive mean 36.31, CFAR mean 123.31), reflecting much denser candidate graph load in merged/high-background samples.

### 2.4 Full-cohort aggregate (all 199 hybrid records)

- quality_score: mean 0.7646, median 0.7789
- sparse_recall: mean 0.7475, median 0.8038
- sparse_edge_recall: mean 0.7817, median 0.8126
- runtime: mean 109.38 s, median 62.87 s, p90 235.50 s

This quantifies why V13 remains robust in aggregate: most samples run on the lower-risk adaptive path, while the higher-risk CFAR path is bounded to the subset where it is most needed.

## 3) Why V13 survived each prior NO-GO

### 3.1 V14 bounded-CFAR / pfa stress branch

Observed challenger issue:

- pfa-mode CA-CFAR behavior under bounded [0,1] normalized signal exhibited collapse-risk characteristics on the CFAR-routed cohort.

V13 design choice that avoided it:

- production V13 is sigma-mode CFAR by default, not pfa mode.
- unsafe pfa+axial path is parked behind explicit override gate.

### 3.2 V15 correlation/track-continuity branch

Observed challenger issue:

- real node recovery existed, but identity collision and wrong-edge extrapolation capped real metric gains on target at-risk cohorts.

V13 design choice that avoided it:

- V13 does not inject synthetic recovery nodes by default.
- no merge-gated continuity synthesis in production path means no synthetic identity-theft channel.

### 3.3 V16/V17 kinematic soft-linking branch

Observed challenger issue:

- frame-skip competition against valid direct links created regressions; hard exclusion removed most but not all regression.

V13 design choice that avoided it:

- baseline production linking is adjacent-frame only, no kinematic frame-skip recovery in the default path.
- this removes direct-vs-skip competition by construction.

### 3.4 V18 bounded global optimization branch

Observed challenger issue:

- global short-window scorer produced behavioral divergence in ambiguous subsets, but evaluable evidence was strongly capped by sparse GT coverage.

V13 design choice that avoided promotion risk:

- V13 remains on simpler local motion_mutual adjacent linking with known behavior envelope.
- it avoids adding a second optimization layer without strong evaluable lift.

## 4) Latent untested assumptions and risks (flag only)

These are awareness flags, not proposed fixes.

1. Guardrail fallback sensitivity:
   - Spike thresholds (history median * 1.8 and absolute 1200) are stable in known cohorts, but may be brittle under rare distribution shifts.
2. Route gate heuristic boundary risk:
   - merged_6bba_only profile gate could misclassify edge-case morphology near threshold boundaries.
3. motion_mutual under extreme density:
   - strict mutual identity improves precision but may under-link in very dense or rapidly deforming regions.
4. Detection cap pressure:
   - max_detections_per_timepoint=900 bounds runtime, but could truncate true candidates in rare extreme frames.
5. Sparse GT observability ceiling:
   - validation conclusions can be limited by sparse annotation coverage in ambiguous regions.

## 5) Close-out statement

V13 robustness is not accidental. It is largely a consequence of conservative defaults and explicit scope control:

- sigma-mode CFAR (not pfa) in production,
- isotropic sidelobe suppression,
- strict route gating to merged_6bba_only profiles,
- adjacent-only motion_mutual linking,
- default-off experimental recovery layers.

The full-cohort metric section above completes the quantitative evidence for this architecture-level conclusion.
