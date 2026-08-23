# V24 Score-First Tracking Preregistration

Status: **contract frozen; resumable runner and Kaggle notebook implemented; smoke not yet run**.

## Purpose

V24 changes the optimization target. V21-V23 established that division recovery is sparse, structurally fragile, and frequently blocked before semantic ranking. V24 asks a narrower question:

> Can the held-out temporal U-Net checkpoint improve official adjusted edge tracking over the frozen V19 reference, either through Atabey's physical-coordinate linker or through its own native edge head?

This is a score-first experiment, not a claim that divisions are solved. CFAR remains intact, and V23's pair-field ranker remains closed.

## Leakage Boundary

The E016 secondary checkpoint was trained on 172 competition samples while excluding the frozen 27-sample development cohort. Development labels were not used for fitting or checkpoint selection.

V24 uses exactly those 27 held-out samples and evaluates their complete sequences. The cohort is derived from the 46-event V22 development fixture, but the endpoint is whole-sample official tracking rather than division-event availability.

| Family | Held-out samples |
|---|---:|
| `44b6` | 5 |
| `6bba` | 22 |
| Total | 27 |

No training sample may enter V24 evaluation. No V24 result may be used to retrain, select, or fine-tune the frozen checkpoint.

The checkpoint is accepted only at SHA-256 `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`. Its configuration must report a two-frame window, downsample `(1,4,4)`, 32 output channels, and a `5.0 um` pooling kernel.

## Frozen Arms

### A. V19 Frozen Reference

Build the complete graph through `_build_v19_prefirewall_with_route()` and the frozen hybrid defaults. Preserve and record the actual detector, link strategy, node count, edge count, and elapsed time per sample.

### B. E016 Detections With Atabey Relinking

Run the frozen E016 checkpoint once over every frame with no detection TTA, retain detections at threshold `0.97` with a `5.0 um` pooling kernel, discard model edges, and relink adjacent frames using:

- `motion_mutual`;
- `9.0 um` maximum step and prediction-error gates;
- physical coordinates;
- no division-edge injection;
- no pruning or candidate rescue.

This isolates learned detection plus Atabey association. Results remain stratified by V19 reference route.

### C. E016 Native Graph

Reuse the exact detections from Arm B's single inference pass and retain the public predictor's native adjacent-frame edge head with pinned inference defaults. Record the predictor SHA-256, edge threshold, model configuration, and support-pack identity before scoring.

No Atabey relinking, division repair, pruning, or graph cleanup is allowed in this arm.

## Explicitly Absent Arms

The first experiment contains no union, intersection, confidence router, route-specific threshold, fallback, division firewall, pair-field ranker, local assignment, or CFAR/U-Net hybrid. A hybrid may be designed only after complete-arm results demonstrate complementary errors.

## Smoke Battery

Before the 27-sample run, all arms must complete on:

| Sample | Reference route role |
|---|---|
| `44b6_5f15d135` | local-maxima control |
| `44b6_74d0c52e` | CFAR control |
| `6bba_3c5691b6` | components control |

The smoke checks execution, coordinate scaling, deterministic conversion, official-metric availability, and serialization. Smoke scores cannot alter any frozen choice.

## Official Evaluation

Every graph is evaluated with `evaluate_official_tracking()`. Run-level values come only from `summarize_official_tracking()`.

Primary endpoint:

- official adjusted edge Jaccard.

Secondary endpoints:

- official edge Jaccard and total score;
- node recall and total-node ratio;
- edge TP, FP, and FN;
- division TP, FP, FN, and Jaccard, reported separately;
- predicted node and edge counts;
- runtime and peak GPU memory where available.

Report metrics per sample and through official aggregation, then separately by family, V19 reference route, and three deterministic sample folds defined by SHA-256 ordering within family. Classify challenger deltas as improved, flat, or regressed with tolerance `1e-6`.

## Decision Contract

A challenger earns `GO_TO_FULL_199_SCORE_VALIDATION` only if all conditions pass:

1. Pooled official adjusted edge Jaccard improves over V19 by at least `0.02`.
2. Pooled official total score does not regress.
3. Adjusted edge Jaccard does not regress by more than `0.01` in either family.
4. Adjusted edge Jaccard does not regress by more than `0.02` in any fold.
5. Improved samples outnumber regressed samples.
6. No more than two samples regress by more than `0.10` adjusted edge Jaccard.
7. Median predicted-node ratio relative to V19 is at most `1.25`; p90 is at most `1.75`.
8. All 27 samples complete with full route/family reporting.
9. Repeated inference on one sample produces byte-identical coordinates and edges.
10. No checkpoint, threshold, or arm was selected using V24 outcomes.

Outcomes:

- `GO_TO_FULL_199_SCORE_VALIDATION`: at least one challenger passes every gate.
- `HOLD_SCORE_GAIN_WITH_STRATUM_OR_INFLATION_CONCERN`: pooled gain passes but another hard gate fails.
- `NO_GO_V24_CHALLENGERS`: no challenger reaches the pooled gain or metric integrity fails.

If both challengers pass, choose the larger adjusted-edge improvement. A difference below `0.005` is a tie, resolved by lower median node ratio and then runtime. Division Jaccard cannot break the tie because V24 is score-first on ordinary tracking.

## Interpretation Guardrails

- The result is held-out development evidence, not a leaderboard estimate.
- Sparse labels are the official competition yardstick, not exhaustive biological truth.
- A U-Net win does not invalidate CFAR; it authorizes separate full-cohort validation.
- A loss rejects these frozen arms and checkpoint, not learned detection generally.
- Per-route observations cannot authorize tuning in this pass.
- No production graph, submission notebook, or V19/V23 artifact is modified.

## Current Authorization

The resumable three-arm runner, fail-closed graph conversion tests, and
`notebooks/V24_score_first_tracking_kaggle.ipynb` are implemented. Authorized next: run the
three-sample Kaggle smoke, then run the frozen 27-sample evaluation only after the smoke passes.

Not authorized: full 199 execution, hybrid construction, threshold tuning, retraining, submission, or production mutation.
