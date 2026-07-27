# V22 Out-of-Fold Continuation Head Preregistration

Status: **PREREGISTERED; NO MODEL FIT OR HELD-OUT RESULT OPENED**

## Objective

Fit the first route-neutral continuation-compatibility head on the completed
27-sample feature table and determine whether weak-reference ranking transfers
consistently across samples, folds, families, and the two decision-supported
routes.

This is not a biological continuation classifier. It learns a compatibility
utility from weak V19 preferences for later read-only joint semantic shadow
evaluation. It does not run assignment or mutate a graph.

## Why Generalization Is A Hard Gate

Track B previously produced an apparently promising rank on one calibration
case and failed on the other two. The continuation head therefore cannot advance
because of a strong pooled result or one strong fold.

Three outcomes are frozen:

- **GO_TO_JOINT_SEMANTIC_SHADOW:** every hard fold and route gate passes and no
  flagged concern fires;
- **HOLD_GENERALIZATION_CONCERN:** hard minima pass, but cross-fold or
  cross-route degradation exceeds a warning threshold;
- **NO_GO:** any hard generalization gate fails.

A HOLD is not silently promoted to GO by a strong aggregate.

## Population And Labels

Training pairs compare the weak V19 reference child with each local alternative
inside the same reference group.

- The reference is a weak preferred action, not ground truth.
- Alternatives are unknown competitors, not biological negatives.
- Groups with no alternatives are excluded from training and all decision
  metrics because their top-1 result is trivial.
- Singleton groups are reported separately for population accounting.

## Outer And Inner Splits

The existing three sample-blocked folds are the only outer validation folds.
For each outer round:

1. one fold is held out and never guides preprocessing, feature selection,
   regularization, or threshold choices;
2. the other two folds are swapped as inner train/validation folds;
3. the L2 strength is selected by the mean equal-sample-weighted nontrivial
   group top-1 across those two inner directions;
4. ties select stronger regularization;
5. the selected model is refit on both outer training folds and evaluated once
   on the untouched outer fold.

There is no privileged calibration fold.

## Model And Missingness

The decision-eligible model is an L2-regularized pairwise logistic ranker with
`C` in `{0.01, 0.1, 1.0, 10.0}`. A nonlinear model may be diagnostic only.

Standardization and median imputation are fit on outer training samples only.
Every imputed feature retains its explicit availability mask. Route, family,
sample ID, and frame ID are prohibited model features.

Training and evaluation use the frozen hierarchy:

```text
equal sample -> equal parent frame -> equal reference -> equal pair
```

Raw row weighting is invalid.

## Metrics

Decision metrics use only reference groups with at least one alternative:

- equal-sample-weighted strict reference top-1;
- equal-sample-weighted pairwise preference accuracy;
- equal-sample-weighted reference mean reciprocal rank.

Score ties within `1e-12` do not count as top-1 success. Metrics are reported by
fold, family, route, sample, and parent frame before any pooled result.
Within every reported fold, family, and route stratum, samples receive equal
weight before frame/reference/pair averaging; dense routes cannot carry their
own metric through raw row count.

## Cross-Fold Generalization Gates

### Hard NO-GO thresholds

- pooled reference top-1 must be at least **0.85**;
- every fold must have reference top-1 of at least **0.80**;
- maximum top-1 spread across folds must be no greater than **0.10**;
- pooled pairwise accuracy must be at least **0.90**;
- every fold must have pairwise accuracy of at least **0.85**;
- maximum pairwise-accuracy spread across folds must be no greater than
  **0.08**;
- every fold must have MRR of at least **0.90**;
- no fold may fall more than **0.10** below the mean of the other two folds.

Any failure is a **NO-GO**, regardless of pooled performance.

### Flagged concern thresholds

Even when the hard minima pass, the result is held for review when:

- top-1 fold spread exceeds **0.05**;
- pairwise-accuracy fold spread exceeds **0.04**;
- any fold falls more than **0.05** below the mean of the other two.

Any such result is **HOLD_GENERALIZATION_CONCERN**, not GO.

## Route-Specific Generalization Gates

One pooled route-neutral model is fit. CFAR and components are evaluated
independently; neither route may be hidden by the other.

### Hard NO-GO thresholds

For both `cfar_sidelobe/bipartite` and `components/greedy`:

- route-level reference top-1 must be at least **0.80**;
- route-level pairwise accuracy must be at least **0.85**;
- the CFAR/components top-1 gap must be no greater than **0.10**;
- the CFAR/components pairwise-accuracy gap must be no greater than **0.08**;
- every route-by-fold top-1 must be at least **0.70**;
- no route-by-fold top-1 may fall more than **0.15** below that route's full
  out-of-fold top-1.

### Flagged concern thresholds

The result is held when:

- the CFAR/components top-1 gap exceeds **0.05**;
- the pairwise-accuracy gap exceeds **0.04**;
- any route-by-fold top-1 falls more than **0.10** below its route-level
  out-of-fold result.

The fold-3 CFAR stratum contains only one sample, so its metric is explicitly
reported with its sample count. The threshold still detects catastrophic
transfer, but it is not presented as a precise population estimate.

## Local-Maxima

Local-maxima appears only in `44b6_5f15d135` in fold 3. When fold 3 is held
out, the route is absent from training; its result is zero-shot-only.

Every local-maxima metric must be separate and labeled **unproven
generalization**. It is excluded from route hard gates, cannot carry a pooled
GO, and cannot be used for route-specific fitting or calibration.

## Teacher-Imitation Boundary

The weak references were selected using motion-predicted and mutual-nearest
criteria. Prediction error, ownership margins, and local ranks therefore contain
teacher-derived signal.

The full model must be accompanied by a diagnostic ablation removing those
teacher-derived features. A high weak-reference recovery score demonstrates
held-out imitation consistency, not biological truth or official division
performance. This head can advance only to joint semantic shadow evaluation,
where its interaction with U-Net division actions and ownership constraints is
measured independently.

## Closed Scope

This preregistration does not authorize:

- assignment or graph projection;
- confidence alignment with the division head;
- production graph mutation;
- local-maxima-specific fitting;
- locked validation;
- full 199-sample fitting or evaluation.

Machine contract:
`tests/fixtures/v22_continuation_head_preregistration.json`
