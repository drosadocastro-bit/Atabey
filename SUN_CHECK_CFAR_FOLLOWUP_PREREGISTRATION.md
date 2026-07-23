# Independent CFAR-Only Sun Check Follow-Up

Date: 2026-07-23
Status: pre-registered shadow audit only; no measurements have been run

No image correction, detector tuning, route change, graph mutation, submission behavior, or
threshold adaptation is authorized by this document.

## Research Question

The original 12-sample Atabey Sun Check audit found apparent route-level differences in background
and SNR proxies. Its strongest exploratory association with tracking behavior weakened when the
analysis was restricted to the seven CFAR-routed samples:

- full panel: `q90_end_to_start_ratio` versus V20-minus-V13 sparse EdgeRecall,
  `rho=-0.732`, `p=0.007`;
- CFAR-only subset: `rho=-0.536`, `p=0.215`.

This demonstrated route confounding and did not establish an independent QC signal.

The pre-registered question is:

> Within samples already routed to CFAR, does a bead-free temporal-intensity proxy add predictive
> value for the official benefit or harm of the CFAR route beyond the foreground-density profile
> that already determines routing?

This is a routing/QC question, not a claim about instrument calibration, biological truth, or image
quality in an absolute sense.

## Interpretation Boundary

The term "Sun Check" is an analogy to the WSR-88D use of a stable external reference. The
competition data contain no solar reference, bead field, instrument telemetry, or independent PSF
standard. Atabey therefore measures only retrospective, image-internal self-consistency proxies.

The audit may support:

- sample-state QC research;
- uncertainty flags;
- future route-review hypotheses.

It may not support:

- gain correction;
- stage-drift correction;
- deconvolution or PSF correction;
- changing CFAR thresholds;
- automatic rerouting;
- claims that bulk biological motion is instrument motion.

## Frozen Source Artifacts

Route membership is taken only from:

`submissions/cfar_bounded_scan_fulltrain.json`

The frozen file has SHA-256:

`d9a6016f05d8682d7a41fc7452849291643c5c398551962e1fb23d3bf656e922`

It contains 199 samples and identifies 66 as CFAR-routed. The 12 samples from the original Sun Check
panel are excluded before selection.

Selection does not use Sun Check measurements, official scores, sparse EdgeRecall, division
outcomes, or any feature/model result. Historical tracking outcomes may exist elsewhere in the
repository, so this is an independent measurement panel rather than a claim that all outcomes are
previously unseen.

## Locked Cohorts

Eligible samples were stratified by:

1. frozen route (`CFAR` or `non-CFAR`);
2. sample family (`44b6` or `6bba`).

Within each stratum, samples were ordered by ascending SHA-256 of:

`sun-check-cfar-followup-v1:<sample_id>`

The first 15 samples from each CFAR family and first 6 from each non-CFAR family were locked. No
sample may be substituted after measurements begin. An unreadable or incomplete sample remains in
the report as unavailable and reduces the evaluable count.

### Primary CFAR cohort

The primary cohort contains 30 samples: 15 `44b6` and 15 `6bba`.

| Family | Sample |
|---|---|
| `44b6` | `44b6_18ced818` |
| `44b6` | `44b6_40c45f5a` |
| `44b6` | `44b6_c50204e0` |
| `44b6` | `44b6_668e0cc7` |
| `44b6` | `44b6_b2c44266` |
| `44b6` | `44b6_d5e7d891` |
| `44b6` | `44b6_144b256d` |
| `44b6` | `44b6_267148e4` |
| `44b6` | `44b6_abf82518` |
| `44b6` | `44b6_8f5ab931` |
| `44b6` | `44b6_74d0c52e` |
| `44b6` | `44b6_cf2536e8` |
| `44b6` | `44b6_551a5dba` |
| `44b6` | `44b6_0db75fae` |
| `44b6` | `44b6_87bba6c4` |
| `6bba` | `6bba_474be664` |
| `6bba` | `6bba_6479435d` |
| `6bba` | `6bba_767a1e17` |
| `6bba` | `6bba_4ffd3da3` |
| `6bba` | `6bba_3db54e20` |
| `6bba` | `6bba_b1ae37b9` |
| `6bba` | `6bba_78a7bd97` |
| `6bba` | `6bba_5dfe9ad1` |
| `6bba` | `6bba_6db0e9b4` |
| `6bba` | `6bba_d82a4fc6` |
| `6bba` | `6bba_3abfe10a` |
| `6bba` | `6bba_786893ac` |
| `6bba` | `6bba_ab78413d` |
| `6bba` | `6bba_0e7c0d07` |
| `6bba` | `6bba_6feb10f0` |

With `n=30`, the primary cohort is sized to detect only a large correlation, approximately
`|rho| >= 0.49` at two-sided alpha `0.05` and 80% power. Smaller effects remain inconclusive rather
than negative proof.

### Non-CFAR route controls

The 12 controls are not part of the primary incremental-value test. They provide a route-separation
and measurement-sanity check only.

| Family | Sample |
|---|---|
| `44b6` | `44b6_cf8fed6b` |
| `44b6` | `44b6_341df25f` |
| `44b6` | `44b6_3a861e03` |
| `44b6` | `44b6_5740d24b` |
| `44b6` | `44b6_71a4179f` |
| `44b6` | `44b6_7e557709` |
| `6bba` | `6bba_372c8cb8` |
| `6bba` | `6bba_312f0dc3` |
| `6bba` | `6bba_d6ecebbb` |
| `6bba` | `6bba_6ca87370` |
| `6bba` | `6bba_d3da753b` |
| `6bba` | `6bba_a90a0b9c` |

Control outcomes cannot be used to tune a threshold or rescue a failed CFAR-only hypothesis.

## Frozen Measurements

The existing read-only implementation in `src/atabey/diagnostics/sun_check.py` is used unchanged.
For each sample it reads five deterministic anchor frames:

`0`, `T/4`, `T/2`, `3T/4`, and `T-2`

Each anchor is paired with its immediate successor for bulk-shift estimation.

### Primary proxy

The pre-registered primary proxy is:

`temporal_intensity_log_ratio = log(q90_last / q90_first)`

The signed transform makes equal proportional increases and decreases comparable while preserving
the direction of the original observation. The directional hypothesis is negative: larger temporal
intensity increase predicts less benefit, or more harm, from the CFAR route.

### Existing route-profile covariates

The frozen baseline covariates are:

- `log(median_foreground_fraction)`;
- `log(median_largest_component_voxels)`;
- sample family (`44b6` versus `6bba`).

These are the density/profile variables against which incremental value must be demonstrated.

### Secondary Sun Check proxies

The following remain secondary and cannot rescue a failed primary test:

- median background;
- background temporal spread;
- median SNR proxy;
- median and p90 bulk-shift magnitude;
- median Z-profile spread;
- median XY-shading spread;
- compact-object sigma by axis;
- maximum saturation fraction.

Bulk shift remains biologically confounded. Compact-object widths remain biological footprint
proxies, not bead-derived PSF estimates.

## Frozen Tracking Comparators

Each sample is built in shadow as two independent graph copies over at most 100 timepoints:

1. frozen V13 adaptive graph from `_build_v9_style_graph`;
2. frozen V19 hybrid graph from `_build_hybrid_graph` with watershed refinement and
   `cfar_link_strategy="bipartite"`, without the V20 firewall.

V20 is excluded because its firewall is closed in its current form and suppresses all four official
V19 division TPs in the fixed battery.

The source image, GT graph, and either graph copy are never mutated by the diagnostic. Actual
detector/link strategy returned by each builder must be stored per sample. A primary-CFAR sample
that no longer returns the CFAR route is reported as route drift and is not silently reclassified.

## Outcomes

The primary outcome is:

`official_adjusted_edge_jaccard(V19 CFAR) - official_adjusted_edge_jaccard(V13 adaptive)`

Both terms must come directly from the pinned official host through
`summarize_official_tracking()`. Sparse EdgeRecall is diagnostic only and cannot replace the
official outcome.

Secondary outcomes are reported without changing the decision:

- official node Jaccard delta;
- official edge Jaccard delta before node-count adjustment;
- official Division Jaccard TP/FP/FN;
- sparse EdgeRecall delta for historical continuity only;
- runtime and route stability.

## Pre-Registered Analysis

Only the 30 CFAR samples enter the primary analysis.

### Baseline model

`M0` predicts the official adjusted-edge-Jaccard delta from:

- family;
- standardized log foreground fraction;
- standardized log largest-component size.

### Incremental model

`M1` adds standardized `temporal_intensity_log_ratio` to the exact same baseline.

Continuous variables are standardized inside each training fold. No regularization strength,
feature subset, interaction, polynomial term, breakpoint, or threshold is tuned.

Evaluation uses leave-one-sample-out predictions and reports:

- mean absolute error for `M0` and `M1`;
- relative MAE improvement from `M0` to `M1`;
- signed temporal-intensity coefficient fitted on all 30 samples;
- Spearman correlation between the primary proxy and outcome;
- the same coefficient and correlation separately by family.

A two-sided, 10,000-draw permutation test shuffles the primary proxy within family using fixed seed
`20260723`. Its p-value is confirmatory for this bounded audit.

### Secondary multiplicity

Secondary proxy associations use Spearman correlations and Benjamini-Hochberg false-discovery-rate
control at `q=0.10`. They are hypothesis-generating even when they pass that bound.

Missing primary proxy or official outcome makes a sample unevaluable. Missingness and reason are
reported; no imputation and no replacement sample are allowed.

## Decision Rules

The temporal-intensity proxy is a **GO for continued shadow QC/routing research only** if all of the
following hold:

1. `M1` reduces leave-one-sample-out MAE by at least 10% relative to `M0`;
2. the fitted primary coefficient is negative;
3. the within-family permutation test has `p < 0.05`;
4. both families show the same coefficient direction;
5. at least 24 of the 30 primary samples are evaluable;
6. all source graphs pass zero-perturbation checks.

The result is **inconclusive** if the MAE improvement is 5-10%, the permutation p-value is
`0.05-0.10`, or one family lacks directional stability. Inconclusive does not authorize expansion
or integration.

The primary proxy is a **NO-GO as an incremental routing signal** if MAE improves by less than 5%,
the coefficient has the wrong direction, or `p >= 0.10`.

No result from this bounded audit authorizes production routing. A GO would justify a later,
separately pre-registered validation cohort or a review-priority flag only.

## Required Report

The future result document must include:

- all 42 registered samples, including failures;
- frozen and actual route per sample;
- all Sun Check proxy values and availability;
- official V13 and V19 metrics separately;
- primary outcome delta;
- `M0` and `M1` fold predictions;
- primary decision criteria one by one;
- family-stratified results;
- control-panel summaries kept separate from the primary test;
- source graph identity/zero-perturbation evidence;
- an explicit GO, INCONCLUSIVE, or NO-GO call.

## Guardrails

- No measurements were inspected while selecting this cohort.
- No threshold or feature selection on these 42 samples.
- No reuse of the original 12-sample panel in confirmatory statistics.
- No sparse EdgeRecall substitution for the official metric.
- No use of division-candidate counts as verified negatives.
- No image correction, drift correction, detector change, or rerouting.
- No production graph mutation.
- No claim that an internal proxy is an external calibration reference.

## Decision State

The follow-up is fully pre-registered and not yet run. The next permitted action is implementation
of a read-only runner that reproduces this contract exactly, followed by the locked 42-sample shadow
audit. Any deviation must be documented before outcomes are opened.
