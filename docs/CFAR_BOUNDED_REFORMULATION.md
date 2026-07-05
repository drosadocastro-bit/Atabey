# CFAR Bounded-Domain Reformulation — Experimental Findings

Status: **EXPERIMENTAL / NO-GO**. Nothing in this investigation touches
production defaults, `run.py`, or the protected V13 hybrid submission track. All
code lives in isolated new files and is gated behind an explicit
`--enable-bounded-cfar` opt-in.

## Motivation

The V14 diagnostics (`docs/V14_DIAGNOSTICS.md`) confirmed that the production
CA-CFAR `pfa` mode uses a multiplicative threshold `T = alpha * background_mean`
on a signal robust-normalized to `[0,1]`. Because `alpha = N*(pfa^(-1/N) - 1)`
grows large at small `pfa`, `T` can exceed the `[0,1]` ceiling. When it does, no
voxel can clear the threshold and every peak is rejected — the zero-node collapse
observed on `44b6_0c582fdc`. This work (a) quantifies how widespread that failure
mode is and (b) trials three bounded-domain formulations that cannot annihilate
all detections.

## Artifacts (all new, isolated)

- `src/atabey/detection/cfar_bounded.py` — bounded formulations + SAT background stats.
- `scripts/run_cfar_bounded_experiment.py` — gated `scan` (Part 1) / `validate` (Part 3) runner.
- `tests/test_cfar_bounded.py` — SAT-vs-brute-force correctness + collapse-avoidance guards.
- `submissions/cfar_bounded_scan_fulltrain.json` — full 199-sample scan.
- `submissions/cfar_bounded_validate.json` — 3-sample + collapse-sample validation.

## Part 1 — How common is the collapse? (full train set)

Scanned all **199** train samples. **66** route to the CFAR path under the
production `merged_6bba_only` gate. Background level was measured as the median
SAT box-ring mean of the normalized signal at the middle timepoint.

Background-mean distribution (normalized `[0,1]`):

| cohort | count | p25 | median | p75 | p95 | max |
|---|---|---|---|---|---|---|
| all samples | 199 | 0.049 | 0.093 | 0.226 | 0.370 | 0.492 |
| CFAR-routed | 66 | 0.162 | 0.239 | 0.313 | 0.410 | 0.429 |

Collapse condition (`background_mean * alpha > 0.999`), counted over the
CFAR-routed cohort:

| pfa | routed samples at collapse risk | fraction of routed (66) |
|---|---|---|
| 1e-3 | 51 | 77% |
| 1e-2 | 40 | 61% |
| 2e-2 | 29 | 44% |
| 5e-2 | 13 | 20% |

**`44b6_0c582fdc` is representative, not an outlier.** The routing gate selects
merged / high-foreground samples, which are exactly the high-background samples
prone to collapse: the routed cohort's median background (0.239) is ~2.6× the
overall median (0.093). At the aggressive `pfa` values where CFAR is most
selective, a majority of routed samples would collapse. The unbounded
multiplicative threshold is a structural defect of applying CA-CFAR to a bounded
signal, not a single bad sample.

## Part 2 — Bounded formulations trialed

All three are bounded-safe by construction (threshold can never exceed the
signal ceiling), and all evaluate the expensive threshold transform only at
candidate peak voxels.

1. **`alpha_clip`** — standard CA-CFAR `alpha`, but the multiplicative threshold
   is clamped to a ceiling `< 1`. Cheapest; a bounded-safe patch of the existing
   formula rather than a distributional change.
2. **`logit`** — map `s -> log(s/(1-s))`, run a Gaussian-clutter CFAR
   (`mean + z(pfa)*std`) in the unbounded logit space, compare there. Never hits a
   ceiling.
3. **`beta`** — model local background as `Beta(a,b)` (method of moments), take the
   `1 - pfa` quantile as the threshold. Distributionally correct on `[0,1]`.

Background statistics use a single-pass summed-area-table (integral image)
instead of four `uniform_filter` passes.

## Part 3 — Validation (3 samples + collapse sample, 12 timepoints)

`collapse_avoided_all_pfa = True`. Every formulation produced non-zero detections
at every `pfa` on `44b6_0c582fdc`, so the zero-node annihilation is eliminated.

Baseline reference (production adaptive route per sample):

| sample | route | baseline nodes | baseline recall | baseline ms |
|---|---|---|---|---|
| 44b6_0113de3b | components | 2160 | 0.0577 | 4355 |
| 44b6_0b24845f | local_maxima | 6013 | 0.0196 | 6043 |
| 44b6_0c582fdc | local_maxima | 4835 | **0.0000** | 7059 |

Bounded results (sparse recall / node count / detection ms for 12 tp):

| sample | mode | pfa | nodes | recall | detect ms |
|---|---|---|---|---|---|
| 0113de3b | alpha_clip | 1e-3…5e-2 | ~672 | 0.0000 | ~36000 |
| 0113de3b | logit | 1e-2 | 1306 | 0.0385 | 66659 |
| 0113de3b | beta | 5e-2 | 2374 | 0.0385 | 35418 |
| 0b24845f | alpha_clip | any | 292 | 0.0000 | ~36000 |
| 0b24845f | logit | 1e-2 | 7485 | 0.0196 | 66430 |
| 0b24845f | beta | 1e-2 | 7193 | 0.0196 | 35408 |
| 0c582fdc | alpha_clip | any | 894 | 0.0000 | ~42000 |
| 0c582fdc | logit | 5e-2 | 5462 | 0.0000 | 81070 |
| 0c582fdc | beta | 5e-2 | 5458 | 0.0000 | 42173 |

Observations:

- **Collapse fixed, quality not recovered.** On the actual collapse sample the
  surviving detections score **0.0 recall for every formulation** — the same as
  the baseline on that sample. Avoiding the zero-node collapse did not put
  detections in the right places; the sample is hard regardless of threshold form.
- **No quality gain on peers.** Best bounded recall is at parity (`0b24845f`,
  0.0196) or below baseline (`0113de3b`, 0.0385 vs baseline 0.0577), always with
  far more nodes (up to 9k vs 6k).
- **`alpha_clip` degenerates** on high-background samples: results are identical
  across `pfa` because the clip binds (threshold pinned at the ceiling), so only
  near-saturated voxels survive — a near-collapse rather than a useful detector.
- **Runtime regressed.** Bounded detection ran 35–82 s / 12 tp versus ~4–7 s for
  the baseline and ~16 s for the existing hybrid detection. The integral-image
  estimator as written (per-voxel clamped `np.ix_` gathers) materializes many
  full-volume temporaries and is **slower** than scipy's separable
  `uniform_filter`; `logit` (two SATs) is worst. The intended background-stats
  speedup was **not** achieved with this SAT implementation.

## Go / No-Go

**NO-GO.** Promotion requires BOTH (a) no collapse across the full train set AND
(b) a quality gain over baseline.

- (a) Collapse avoidance: **met** — all formulations, all `pfa`.
- (b) Quality gain: **not met** — parity at best, worse typically; the collapse
  sample itself stays at 0.0 recall.
- Runtime: **regressed**, not competitive.

The bounded reformulations correctly remove the catastrophic failure mode, but
CFAR routing does not demonstrate a quality advantage on these samples even once
the collapse is removed, and the SAT optimization did not deliver a runtime win.
Do not promote to the submission track. The protected V13 path is unchanged.

## If CFAR is ever revived

- Replace the clamped `np.ix_` SAT gather with a slice-based integral image
  (shifted-view subtraction, borders handled by explicit padding) — that is the
  real `uniform_filter` replacement; the current gather is not.
- The quality ceiling here is a peak-localization problem, not a threshold-form
  problem: on high-background bounded data the raw-volume local maxima are
  noise-dominated, so a better foreground/peak model is the prerequisite before
  any CFAR threshold refinement is worth pursuing.
