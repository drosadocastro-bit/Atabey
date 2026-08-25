# V23 Temporal Echo Persistence Preregistration

Status: **development-only, read-only diagnostic**.

## Purpose

Test whether a second-daughter echo that completes an anchored fork at frame
`t+1` also produces a coherent, distinct return at frame `t+2`. The experiment
targets the remaining parent-seed ranking bottleneck without changing CFAR,
candidate formation, ownership, edges, or graphs.

## Frozen Population

- The two genuinely anchored events established by
  `v23_split_echo_paths.json`:
  - `44b6_aaf8b0ea t61`;
  - `6bba_fc5f39dc t24`.
- The parent-present link-identity failure and the missing-parent failure remain
  quarantined and are not scored.
- Frozen V19/CFAR graph and low-confidence echo profile:
  `floor=0.35`, `k=0.80`, footprint `(1,3,3)`.
- `14 um` formation/router radius, `3 um` primary deduplication radius, and
  `9 um` temporal-return gate.

Ground truth is used only after all hypotheses and scores exist to locate the
registered-valid proposal. It does not create or select any return.

## Return Construction

For every eligible parent with exactly one existing frame-`t+1` child:

1. retain that child unchanged;
2. construct each distinct frame-`t+1` echo counterpart inside `14 um`;
3. search frame `t+2` for one return near the retained child and one return near
   the echo counterpart;
4. require the two returns to be distinct;
5. prefer primary detections over low-confidence echoes only through fixed
   evidence values (`1.0` for primary, clipped CFAR margin for echo).

The search is passive and read-only. "Echo" denotes track-conditioned evidence,
not an emitted physical signal.

## Fixed Temporal Score

`temporal_score = 0.50 * anchored_pair_score`
`               + 0.20 * counterpart_return_closeness`
`               + 0.15 * retained_child_return_closeness`
`               + 0.10 * mean_return_evidence`
`               + 0.05 * distinct_return_support`

Return closeness is `max(0, 1 - distance / 9 um)`. A missing return contributes
zero. Distinct-return support is one only when both paths can use different
frame-`t+2` returns. No weights or gates are fitted from the two known events.

## Measurements

Report for both events:

- correct counterpart return availability at `t+2`;
- parent-seed rank and counterpart rank before versus after persistence;
- global proposal rank before versus after persistence;
- TP-versus-non-TP persistence distributions;
- primary-versus-echo return source;
- zero perturbation.

## Decision Contract

This two-event audit cannot authorize production integration.

- `GO_TO_LARGER_TEMPORAL_SHADOW`: both correct counterparts have distinct
  `t+2` returns, neither parent rank nor counterpart rank regresses, and at least
  one parent rank improves by 25% or reaches the top 25.
- `HOLD_TEMPORAL_SIGNAL`: temporal returns exist for at least one event but the
  ranking condition is not met.
- `NO_GO_TEMPORAL_ECHO`: neither correct counterpart has a usable distinct
  return, or either correct counterpart is demoted by more than 25%.

The quarantined paths stay quarantined under every outcome. No result authorizes
graph mutation or a full-cohort run.
