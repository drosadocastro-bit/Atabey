# V23 Bounded Pair-Field Model Preregistration

Status: **model design frozen; implementation, extraction, and fitting not yet run**.

## Purpose

The metadata preflight reduced the proposed experiment to 2,264 local actions backed by 54 reusable parent fields. It reproduced all 90 patched-official TP variants across 29 events and passed every extraction and resource gate.

This document freezes the smallest model capable of testing the remaining question: does the parent-centered two-frame image field add repeatable division-ranking signal beyond candidate geometry and masks?

A successful ranker is not a mitosis probability estimator. It is a bounded retrieval mechanism over CFAR candidates, evaluated only on the development events supported by the patched official metric.

## Dataset Readiness Gate

Before fitting, all 2,264 actions must be projected through the patched official scorer and assigned one of three epistemic states:

- TP: supervised positive;
- FP: reliable supervised negative;
- unsupported/not evaluated: unknown, excluded from loss but retained in held-out ranking.

Sparse absence is never a negative. The 29 TP events and 90 TP variants must reproduce exactly.

Training requires at least 18 events containing both a TP and official FP, at least 4 such events per family, and at least 10 in every outer-training complement. Failure enters `HOLD_DATASET_LABEL_SUPPORT`; it cannot be repaired by relabeling unknowns.

## Frozen Architecture

The model is a fixed low-capacity 3D CNN taking the five-channel `33 x 33 x 33` pair field.

| Block | Channels | Kernel | Stride | Normalization |
|---|---:|---:|---:|---|
| 1 | 5 -> 8 | 3 | 1 | GroupNorm(4) + SiLU |
| 2 | 8 -> 12 | 3 | 2 | GroupNorm(4) + SiLU |
| 3 | 12 -> 16 | 3 | 2 | GroupNorm(4) + SiLU |
| 4 | 16 -> 24 | 3 | 2 | GroupNorm(4) + SiLU |

Adaptive average and maximum pooling are concatenated, followed by `Linear(48,16)`, SiLU, dropout 0.1, and `Linear(16,1)`.

The exact trainable parameter count is 20,145, with a hard ceiling of 25,000. Architecture search and pretrained weights are forbidden. The output is an unbounded ranking score, not a calibrated probability.

Coordinates, family, route, sample, node, and frame identifiers cannot enter the model.

## Objective And Weighting

Each patched-official TP is preferred to each hash-sampled official FP from the same event using pairwise softplus loss. Official FP sampling is capped at 64 per event with seed `v23-pair-field-fp-v1`.

Weights follow sample -> event -> label side -> action. Raw pair count cannot dominate optimization, and multiple valid TP variants still count as one event in decision metrics.

The optimizer is AdamW with learning rate 3e-4, weight decay 1e-3, pair batch size 16, gradient clipping at 1.0, and at most 60 epochs. Mixed precision is allowed.

Only deterministic XY D4 transformations are allowed, applied identically to every channel. Z-axis permutations, time-channel swapping, and intensity jitter are forbidden.

## Fold-Safe Early Stopping

Outer validation uses the existing three sample-blocked folds. For each outer fold, the other two folds swap training and inner validation roles.

Early stopping minimizes equal-event-weighted pairwise log loss with patience 8 and minimum delta 1e-4. Recall is not an early-stopping signal. The outer held-out fold cannot influence architecture, epoch count, thresholds, or controls.

Final refitting uses both outer-training folds for the floor of the median best epoch from the two swaps.

Three seeds are frozen: 314159, 271828, and 161803. At least two seeds must pass every hard gate, and any seed with pooled recall@10 below 0.65 blocks GO.

## Controls

Five controls are mandatory:

- unfitted nearest-distance ranking;
- a fold-safe geometry-only logistic ranker;
- the same 3D architecture with both image channels zeroed;
- the fitted main checkpoint with held-out parent fields deterministically shuffled within fold, family, and crop-coverage quartile;
- the fitted main checkpoint with `t+1` replaced by `t`.

The shuffle control must move at least 80% of events; unmoved singleton strata are reported explicitly.

## Decision Gates

The median-seed main model must achieve:

- pooled recall@10 >= 0.80;
- every fold recall@10 >= 0.625;
- each family recall@10 >= 0.65;
- fold spread <= 0.25;
- pooled MRR >= 0.40;
- TP-versus-official-FP pairwise accuracy >= 0.75.

Independent image evidence additionally requires recall@10 margins of at least:

- 0.10 over the better nearest-distance/geometry-only control;
- 0.10 over shuffled images;
- 0.05 over the static-image control.

No fold may lose more than one event versus the best non-image control.

## Outcomes

- `GO_TO_READ_ONLY_LOCAL_ASSIGNMENT_SHADOW_PREREGISTRATION`: readiness, quality, controls, folds, families, and seed stability all pass.
- `HOLD_PAIR_FIELD_SIGNAL_INCONCLUSIVE`: absolute quality passes but temporal contribution, shuffle coverage, or seed stability remains uncertain.
- `NO_GO_PAIR_FIELD_RANKER`: readiness, absolute quality, fold/family generalization, or independent image-signal evidence fails.

A GO authorizes only design of a read-only local assignment shadow. It does not authorize graph mutation, CFAR replacement, threshold tuning, a full-199 evaluation, or submission.

## Current Boundary

Real tensor extraction, model implementation, fitting, assignment, and locked validation remain disabled. The next authorized artifact is the locked extractor and action-label manifest builder, followed by integrity verification before fitting.
