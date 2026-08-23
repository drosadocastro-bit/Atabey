# V23 Pair-Conditioned 3D Field Availability Preregistration

Status: availability gate only; model fitting prohibited

## Purpose

Determine whether the existing E016 development labels can support a pair-conditioned spatiotemporal representation without repeating the route and family generalization failure of the V22/V23 scalar semantic rankers.

## Representation Contract

Each action would be represented on a fixed isotropic `33 x 33 x 33` field centered on the proposed parent:

- normalized raw image at `t`;
- normalized raw image at `t+1`;
- parent-location mask;
- one symmetric two-daughter candidate mask;
- crop-coverage mask for padded boundaries.

The physical half-extent is 16 um and isotropic spacing is 1 um. Daughter ordering is symmetric. Sample ID, event ID, family, route, official label, GT distance, rank, ownership outcome, and scalar distance/angle/velocity features are prohibited model inputs.

The candidate masks make the representation pair-conditioned. A future experiment would require mask-only, image-shuffled, static-image, and geometry-only controls to prove incremental image evidence. None is fitted in this pass.

## Label Boundary

- positive: patched-official TP actions;
- reliable negative: patched-official FP actions only;
- unsupported and unevaluated actions: unknown, never negatives;
- split unit: sample;
- local-maxima: descriptive only and never decision-bearing.

## Availability Gates

Before any crop extraction or GPU work:

- at least 99% representation availability for official TP and FP actions;
- at least six CFAR-positive samples;
- at least three positive samples in each family;
- in every held-out fold, at least two CFAR and two `44b6` positive events;
- in every training complement, at least four CFAR and four `44b6` positive events.

Failure yields `NO_GO_CURRENT_E016_PAIR_FIELD_TRAINING`. It does not show that full-field evidence is useless; it shows the current labels cannot test its required generalization claim.

Passing would authorize only bounded crop extraction and storage estimation. It would not authorize model fitting, assignment, graph mutation, routing changes, or a full 199-sample run.
