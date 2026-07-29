# V23 Up/Downconversion-Inspired CFAR Replacement Shadow

## Status

Design only. No production detector change, route deletion, threshold tuning,
assignment, or graph mutation is authorized.

## Question

Can a learned anisotropy-aware encoder-decoder detector replace the current
CFAR/sidelobe route on its difficult samples while preserving official-positive
availability and normal tracking behavior?

The radar analogy is architectural, not literal RF processing:

- **Downconversion analogue:** encode and compress local 3D intensity context
  into multiscale features while preserving physical voxel anisotropy.
- **Upconversion analogue:** decode those features back to voxel-level object
  heatmaps and confidence maps, restoring fine spatial detail.
- **Decision output:** detector-native peaks and uncertainty, not a committed
  lineage graph.

The encoder-decoder is therefore a candidate CFAR replacement, not a post-hoc
CFAR filter and not a reason to remove CFAR before comparison.

## Shadow design

Use the frozen E016 U-Net checkpoint or a separately identified detector
checkpoint only as a feature/detection shadow. Keep the following fixed:

- the same raw volumes and physical voxel scale;
- the same 14 um candidate-formation action contract;
- the same positive/unknown/official-FP label policy;
- no future-frame reassociation during detector scoring;
- no graph mutation and no Track A changes.

Export, per peak or proposed peak:

- pre-threshold decoder heatmap/logit;
- local uncertainty or margin;
- pooled bottleneck/decoder embedding;
- crop-boundary and missing-feature flags;
- deterministic physical coordinates.

The shadow must compare three outputs on CFAR-routed samples:

1. existing CFAR/sidelobe peaks;
2. encoder-decoder peaks at a preregistered operating point;
3. a union diagnostic, without allowing the union to enter production.

## Required evidence

The replacement cannot be judged by visual peak count alone. Report separately
for CFAR samples, family, fold, sample, and event:

- official-positive availability and complete-triplet availability;
- official TP/FP action counts under the patched scorer;
- action and event retrieval at fixed top-k budgets;
- peak count and candidate-density change relative to CFAR;
- normal continuation/edge-recall perturbation, with zero graph mutation;
- missing-role and formation-loss categories from the six-case audit.

CFAR is a meaningful route: 66/199 samples overall and 7/39 development
events. A replacement that improves only components/greedy is not a CFAR
replacement.

## Preregistered gate

The encoder-decoder shadow is eligible for a larger route-specific experiment
only if all of these hold on the bounded CFAR development set:

- no decrease in official-positive availability beyond 5% relative to CFAR;
- at least 0.70 event recall@50 for the CFAR route, or a documented increase
  in availability that explains why ranking is not yet comparable;
- no more than 10% increase in candidate density at matched availability;
- no measurable graph mutation and no degradation in normal edge-recall shadow;
- no fold with event recall@50 below 0.50;
- results are reported separately for 44b6 and 6bba.

Failure means **HOLD**, not automatic deletion of CFAR. CFAR remains the
fallback route until a replacement passes this contract on independent samples.

## First bounded battery

Start with the fixed controls and CFAR-heavy known cases, then add independent
CFAR samples before any 199-sample run. The first battery must include the
official-positive controls, the 6bba division cases, and at least one 44b6
CFAR event. The battery is detector-only and cannot alter the official action
table.

## Decision semantics

- **GO:** encoder-decoder becomes a candidate CFAR replacement for a larger
  shadow audit only.
- **HOLD:** representation or availability is promising but not generalized;
  keep CFAR active and investigate the failure mode.
- **NO-GO:** no evidence of improvement or normal-tracking safety; retain CFAR
  unchanged and close this replacement path.
