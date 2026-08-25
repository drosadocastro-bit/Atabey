# V23 Independent Parent-Isolation Preregistration

Status: **development-only, read-only independent validation**.

## Purpose

Validate or reject the diagnostic observation that correct anchored parents were
locally isolated (inverse-density rank `6/6`) in the two discovery events.

## Frozen Cohort

- Exactly 20 GT divisions from CFAR-routed samples: 10 `44b6`, 10 `6bba`.
- At most one event per sample; the earliest GT division is used.
- Samples are selected lexicographically within family from the route census.
- Discovery samples `44b6_aaf8b0ea` and `6bba_fc5f39dc` are excluded.
- The complete frozen list is
  `v23_parent_isolation_independent_fixture.json`.

No event may be replaced after outcomes are known.

## Eligibility

An event is evaluable only when the actual V19 graph:

- returns `cfar_sidelobe/bipartite`;
- contains a frame-`t` detection within `7 um` of the GT parent;
- that detection has exactly one existing frame-`t+1` child;
- the retained child is within `7 um` of either GT daughter.

Every failure remains in the denominator and is classified as route mismatch,
missing parent, missing single-child anchor, or linked-child identity failure.

## Frozen Signal

For every frame-`t` parent with exactly one frame-`t+1` child:

- count other eligible parent seeds within `14 um`;
- rank lower density first with stable node-ID tie handling;
- report the best registered parent seed's rank and normalized percentile.

Track age is reported only as a diagnostic control. It cannot affect the
decision. Ground truth is applied only after density and ranks are computed.

## Decision Contract

All statistics are equal-event weighted and family-stratified.

- `GO_TO_ISOLATION_CONSTRAINED_SHADOW`: at least 12/20 events evaluable, at
  least 4 per family, family median percentile at least 0.90, and top-10 capture
  at least 75% in each family.
- `HOLD_PARENT_ISOLATION`: at least 8/20 evaluable, at least 3 per family,
  family median percentile at least 0.75, and top-25 capture at least 75% in
  each family.
- `NO_GO_PARENT_ISOLATION`: otherwise.

No result authorizes threshold tuning, candidate filtering, graph mutation, or
full-cohort execution.
