# V22 Sample-Blocked Positive-Unlabeled Semantic Ranker Preregistration

Status: **PREREGISTERED; TRAINING NOT RUN**

## Objective

Test whether the five raw-image features that passed the official-positive evidence audit can retrieve patched-official division actions from the complete 268,822-action development pool. This phase fits a semantic ranker only. It does not solve ownership constraints or mutate a graph.

## Epistemic Boundary

The 64 `official_tp` actions are positives and the 518 directly scored `official_fp` actions are reliable negatives. The 2,664 unsupported and 265,576 unscored actions remain unknown:

- unknowns are excluded from supervised loss;
- unknowns remain in every held-out candidate pool;
- unknowns can outrank or bury positives;
- sparse absence is never a negative label.

This is positive-unlabeled retrieval with reliable FP anchors, not a conventional fully labeled classifier. Scores are utilities, not biological probabilities.

## Frozen Primary Features

The primary ranker uses only:

- minimum daughter contrast;
- mean daughter contrast;
- contrast conservation error;
- daughter mass balance;
- mean daughter anisotropy.

These were frozen after the preceding read-only audit. Geometry, motion, ownership margins, rank, identifiers, route, family, and any GT-distance field are prohibited inputs.

Because feature selection used these same 39 development-positive events, outer cross-validation estimates fit stability conditional on this frozen feature choice. It is not independent validation of the feature-discovery step and must not be described that way.

## Training

The decision model is an L2 within-event pairwise logistic ranker. Each official TP is preferred to each same-event official FP. Weighting is equal event, then equal positive, then equal TP/FP pair, preventing dense events or events with multiple positives from dominating.

For each outer fold, preprocessing and `C` selection occur only in the other two folds. Those folds are swapped for inner train/validation, using equal-event positive-event recall@50 over the complete inner-held-out action pool. Ties choose stronger regularization.

No unknown action participates in loss, regularization selection labels, or calibration. Nevertheless, all unknowns remain present when top-k ranks are measured.

## Pessimistic Retrieval

Ranks are pessimistic: every score tie counts ahead of the positive. Metrics are reported at top 1, 5, 10, and 50:

- action-level official-TP recall;
- positive-event recall, where an event succeeds if any official TP is retrieved;
- positive ranks and MRR;
- fold, family, route, sample, and event breakdowns.

Decision pooling uses CFAR and components only. Local-maxima is one fold-3 sample, zero-shot and unproven; it is reported separately and cannot carry a GO.

## Baselines And Ablations

Two fold-safe univariate baselines are mandatory: mean daughter contrast and mean U-Net confidence, with favorable direction selected only from training folds.

Mandatory fitted diagnostics are:

- contrast-only;
- mass-plus-shape only;
- raw features plus confidence.

Only the five-feature raw primary head determines the decision. Confidence cannot rescue a raw-feature failure.

## GO Contract

A GO to preregister a read-only local constraint shadow requires all of:

- supported-route action recall@50 >= 0.80;
- supported-route positive-event recall@50 >= 0.85;
- every fold positive-event recall@50 >= 0.70;
- CFAR action/event recall@50 >= 0.60/0.70;
- components action/event recall@50 >= 0.80/0.85;
- each family event recall@50 >= 0.70;
- event recall@50 at least 0.03 above the best univariate baseline;
- fold event-recall spread <= 0.20;
- route event-recall gap <= 0.25;
- zero source graph mutations.

No value is rounded into passing. Pooled retrieval cannot conceal a CFAR or fold failure.

## Closed Scope

This preregistration does not authorize assignment, calibration, graph projection, locked validation, a full-199 run, or production integration. Passing would authorize only a separately preregistered read-only local constraint shadow.

Machine contract: `tests/fixtures/v22_positive_unlabeled_semantic_ranker.json`
