# V17.1 Criteria Alignment Attempt (Exclusion Gate vs Baseline Linker)

Status: **NO-GO (REGRESSION VS V17)**.

## Objective

Test whether the V17 residual set was primarily caused by a criteria mismatch between:

- the hard-exclusion direct-candidate precheck in `enqueue_kinematic_tracks(...)`, and
- the baseline adjacent linker criteria used in the streaming CFAR route.

Guardrail respected: no changes to production `run.py` defaults or V13 path.

## Mismatch Analysis

### Baseline direct-link criteria in CFAR route

In `scripts/run_hybrid_submission.py`, adjacent linking is executed as:

- `previous =` all detections at time `t`
- `current =` all detections at time `t+1` after CFAR/sidelobe filtering
- `strategy = cfar_link_strategy` (default `motion_mutual`)
- `max_link_distance_um = cfar_max_link_distance_um`
- `predecessor_by_node_id =` full mapping for motion strategies

This is implemented via `link_adjacent_timepoints(previous, current, ...)`.

### V17 exclusion precheck criteria

V17 precheck in `enqueue_kinematic_tracks(...)` used singleton queries:

- `previous = [source]` only
- `current =` current detections
- same `strategy`, same `max_link_distance_um`
- `predecessor_by_node_id = {source: predecessor}` only

So strategy/radius/frame-window matched nominally, but candidate context differed (singleton source vs frame-level source pool).

### Practical discrepancy observed in residuals

For 9/10 V17 residual edges, the singleton precheck returned no direct candidate while the original diagnostic had marked direct-candidate availability in the frame-level analysis. This is a context/eligibility mismatch, not a pure radius/strategy mismatch.

The 10th residual remained a distinct ambiguous-target case (direct edge exists but to a different target), treated as a separate limitation.

## V17.1 Fix Attempt

Implemented an alignment attempt in `src/atabey/tracking/kinematic_recovery.py`:

- Switched direct-candidate precheck from singleton `[source]` query toward frame-level unmatched-source context.
- Reused the same underlying `link_adjacent_timepoints(...)` path and same runtime parameters to reduce logic drift.

Focused tests remained green:

- `tests/test_kinematic_recovery.py`: 4 passed.

## Validation Method (same rigor as prior phases)

- Script: `scripts/run_v16_kinematic_validation.py`
- Cohorts: routed 66 / at-risk 51 / outside 15
- Metric:

$$
quality\_score = 0.5 \cdot sparse\_recall + 0.5 \cdot sparse\_edge\_recall
$$

Artifacts:

- `submissions/v17_1_criteria_alignment_validate.json`
- `submissions/v17_1_criteria_alignment_edge_followup.json`

## Results

### Cohort comparison vs V17

V17 baseline (from `submissions/v17_hard_exclusion_validate.json`):

- routed mean quality delta: `-0.0008137769999022116`
- at-risk mean quality delta: `-0.0008840900458504615`
- outside mean quality delta: `-0.0005747126436781621`

V17.1 criteria-alignment attempt:

- routed mean quality delta: `-0.0022170155922167233`
- at-risk mean quality delta: `-0.002531012740705076`
- outside mean quality delta: `-0.0011494252873563242`

Sparse edge recall deltas also worsened vs V17:

- routed: `-0.004434031184433441` (vs V17 `-0.0016275539998044232`)
- at-risk: `-0.005062025481410146` (vs V17 `-0.001768180091700923`)
- outside: `-0.0022988505747126484` (vs V17 `-0.0011494252873563242`)

Regression counts worsened vs V17:

- routed regressed: 9 (vs 7)
- at-risk regressed: 8 (vs 6)
- outside regressed: 1 (same)

### Original 66-edge carryover check

Edge-level carryover from the original V16 regressed set:

- V17 fixed: 56/66, still regressed: 10/66
- V17.1 fixed: 47/66, still regressed: 19/66

So this attempt did not fix the 9 mismatch cases; it increased residuals.

## Case #10 Handling

The distinct ambiguous-target case remains a separate association ambiguity class (dense local competition), not solved by criteria alignment. It is logged as a known limitation rather than forced in this pass.

## Go/No-Go

**NO-GO for V17.1 criteria-alignment attempt.**

Reasoning:

- Aggregate at-risk quality delta did not approach flat/positive; it moved farther negative vs V17.
- Edge-recall regression worsened.
- Residual carryover from the original 66-edge set increased from 10 to 19.

## Recommendation

1. Keep V17 hard-exclusion behavior as the best current state on this branch.
2. Do not pursue this exact criteria-alignment variant further.
3. If revisiting alignment, do so as a narrowly-instrumented diagnostic patch first (per-source gate audit), not as a behavior change.
4. Treat ambiguous-target residuals as a separate future workstream (dense-region association quality), distinct from direct-edge suppression tuning.
