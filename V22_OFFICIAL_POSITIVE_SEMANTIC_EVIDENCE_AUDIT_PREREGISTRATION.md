# V22 Official-Positive Semantic Evidence Audit Preregistration

Status: **PREREGISTERED; RESULTS NOT OPENED**

## Objective

Determine whether the frozen U-Net action population contains genuinely non-motion evidence capable of distinguishing patched-official TP actions from patched-official FP actions before fitting a positive-unlabeled ranker or activating assignment.

## Population And Labels

The audit is limited to the frozen 27-sample, 46-event development split: 268,822 actions, including 64 official TP and 518 official FP actions. Unsupported and unscored actions remain unknown and are excluded from discriminability calculations, never relabeled as negatives.

## Raw-Image Evidence

For each of the 21,520 exported U-Net peaks, read only its event frame and extract physical-radius descriptors from the raw microscopy volume:

- local core contrast against a robust surrounding shell;
- background-subtracted core signal mass;
- thresholded effective volume;
- intensity-weighted shape anisotropy;
- patch boundary coverage.

Action features compare parent and daughters through conservation, balance, and morphology change. No distance, angle, velocity, prediction error, ownership margin, rank, or GT-distance feature is permitted. U-Net confidence is retained as a separate baseline, not mixed into the raw morphology claim. Per-view TTA variance is unavailable because only the aggregated U-Net output was exported.

## Fold-Safe Diagnostic

For each frozen feature, its favorable direction is selected using only the two training folds. Held-out performance is equal-event-weighted AUC over officially evaluable TP/FP actions. Results are reported by fold, family, and route. Local-maxima remains zero-shot/unproven and cannot carry a decision.

## GO Criteria

A GO to design a positive-unlabeled ranker requires:

- at least 99% peak descriptor completeness;
- at least 95% complete official TP and FP actions;
- at least two distinct raw feature groups with pooled OOF AUC >= 0.65;
- a passing feature with every fold AUC >= 0.55, both family AUCs >= 0.58, and both supported route AUCs >= 0.55;
- best raw morphology AUC at least 0.02 above the best confidence-only baseline.

No model is fit, no assignment is solved, and no graph is mutated. Even a GO establishes conditional discrimination among officially evaluable sampled actions, not biological truth or full-candidate precision.
