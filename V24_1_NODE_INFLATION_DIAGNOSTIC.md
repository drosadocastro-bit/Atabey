# V24.1 Node-Inflation Diagnostic

Status: **complete; descriptive shadow audit only**.

V24.1 investigates why the V24 E016 plus Atabey relink arm failed the median
predicted-node ratio gate. It consumes the completed V24 full-27 per-sample
table and does not rerun inference, mutate graphs, filter detections, tune a
threshold, or authorize full-199 evaluation.

## Frozen Input

- Input: Kaggle V5 `per_sample.csv` from the complete V24 full-27 run.
- Cohort: the same 27 checkpoint-held-out samples, with full sequences.
- Reference: `v19_frozen_reference` predicted-node counts.
- Challenger: `e016_atabey_relink` predicted-node counts.

## Diagnostic Question

Is the node inflation concentrated by family, V19 reference route, or score
outcome? A concentration supports a targeted follow-up hypothesis; diffuse
inflation means a global detector-volume or calibration issue remains more
plausible. This audit is descriptive and cannot select a suppression rule.

The report computes per-sample challenger/reference node ratio and adjusted-edge
delta, then summarizes strata by family, route, and whether the sample exceeds
the frozen median-ratio ceiling of `1.25`. It also reports Pearson correlation
between node ratio and score delta when both quantities vary.

## Result

The audit found 16 of 27 samples above the `1.25` ratio ceiling. Inflation was
concentrated in the `6bba` family (15/22 samples; median ratio `1.37746`) and
the `components` route (15/19; median ratio `1.41652`). The `44b6` family had
1/5 inflated samples, while `cfar_sidelobe` had 1/7 and a median ratio of
`1.01813`.

The relationship between node ratio and adjusted-edge delta was weak
(Pearson `r=0.08239`). Samples within the ceiling had 11 improvements and no
regressions; samples above it had 13 improvements and 3 regressions. Therefore
the detector-overproduction hypothesis is supported as a localized volume
problem, but a global node suppression rule is not justified by this audit.
The next experiment, if pursued, must test a route/family-bounded candidate
mechanism against the complete cohort with an explicit precision safeguard.

The generated machine-readable report is
`v24_1_node_inflation_27_report.json`.

The approved follow-up is documented in
`V24_2_INTERIOR_ORPHAN_SHADOW_PREREGISTRATION.md`.

## Boundaries

- No inference, training, threshold selection, or graph construction occurs.
- No result from this audit changes the frozen V24 arm or promotion decision.
- A suppression or recalibration experiment requires a separate preregistration
  and must be evaluated against the complete frozen cohort.