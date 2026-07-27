# V22 Continuation Feature Table Preregistration

Status: **PREREGISTERED BUILD ONLY; NO TABLE RESULTS OPENED**

## Question

Can the validated 27-sample weak V19 continuation-reference population be
converted into a fold-safe, route-neutral feature table suitable for the
planned continuation-compatibility head without changing its epistemic status,
allowing dense samples to dominate, or mutating any graph?

This pass builds evidence rows only. It does not fit a model, calibrate
confidence, solve ownership, score division actions, or modify a lineage graph.

## Frozen Population

The source is the completed continuation-reference availability audit:

- 27 development samples in three frozen sample-blocked folds;
- 182,996 weak reference continuations;
- 1,024,536 local alternative children;
- exactly 1,207,532 candidate rows when every reference and every alternative
  inside 14 um is retained.

No candidate cap is applied. The largest observed reference has 77 alternatives,
which remains tractable and avoids introducing a selection rule before any
continuation model exists.

## Candidate Meaning

Each candidate group is anchored by one validated three-frame chain:

```text
anchor(t-1) -> parent(t) -> candidate child(t+1)
```

The V19 child is marked `weak_reference_preferred`. Every other child inside
14 um of the same parent is marked `weak_alternative_unknown`.

This is a pairwise compatibility preference, not a biological label:

- the reference is not ground truth;
- an alternative is not a negative;
- sparse absence is not used;
- route agreement is not treated as truth;
- no official division labels are joined into this table.

## Feature Contract

Only route-neutral geometry and local ownership diagnostics are model-eligible:

- anchor-to-parent and parent-to-child distances;
- constant-velocity prediction error;
- step-distance ratio and radial speed change;
- turning angle;
- forward and reverse competitor margins;
- local forward and reverse ranks;
- 10 um parent/child density;
- 14 um local target and competing-source counts.

Missing values carry explicit availability masks and reason codes. Route,
family, detector confidence, appearance, intensity, and volume are prohibited
model features. Route and family remain reporting strata only.

## Weighting Contract

Each sample receives equal total mass through:

```text
sample -> parent frame -> reference -> candidate
```

Within a sample, every represented parent frame receives equal mass, every
reference in that frame receives equal mass, and every candidate in that
reference receives equal mass. Raw candidate-count weighting is prohibited.
Fold-specific training must then weight the samples in its two training folds
equally.

## Integrity Gates

A GO to out-of-fold continuation-head fitting requires:

1. exactly 27 samples, 182,996 references, 1,024,536 alternatives, and
   1,207,532 candidate rows;
2. exact fold, family, and route totals pinned in the machine contract;
3. one and only one weak-reference row per reference group;
4. unique deterministic candidate IDs;
5. exact source reference-ID reproduction;
6. source reference geometry and mutual-nearest metrics reproduced within
   numerical tolerance;
7. per-sample hierarchical weight sums equal to 1 within 1e-9;
8. finite values for every feature marked available;
9. zero semantic scores, assignment selections, graph mutations, or GT labels;
10. zero source-graph perturbation.

## Local-Maxima Guardrail

Local-maxima contributes 167,512 rows but all come from the single fold-3 sample
`44b6_5f15d135`. Its row volume is not generalization evidence.

All local-maxima results must be separate and labeled **unproven
generalization**. Folds 1 and 2 contain no held-out local-maxima observation;
the fold-3 held-out round is zero-shot because local-maxima is absent from
training. Route-specific fitting or calibration remains prohibited.

## Artifacts

- Machine contract:
  `tests/fixtures/v22_continuation_feature_table.json`
- Feature extractor:
  `src/atabey/tracking/continuation_features.py`
- Builder:
  `scripts/build_v22_continuation_feature_table.py`
- Generated shards:
  `v22_continuation_feature_shards/` (ignored by git)
- Aggregate summary:
  `v22_continuation_feature_table_summary.json`
