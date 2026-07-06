# V17 Hard Exclusion for Frame-Skip Competition

Status: **PARTIAL IMPROVEMENT, NOT YET GO**.

## Objective

V16 diagnostic (`submissions/v16_diagnostic_root_cause.json`) showed the regression set was dominated by Type 1 edge competition: frame-skip recovery behavior competing with available direct `t -> t+1` links. V17 applies a hard exclusion rule so recovery is not enrolled for a source track when a valid direct adjacent candidate exists under the existing linker gate.

## Implementation

Changes were kept local to the kinematic path and validation harnessed through the same V16 methodology.

- Updated `src/atabey/tracking/kinematic_recovery.py`:
  - Added direct-candidate precheck in `enqueue_kinematic_tracks(...)`.
  - If a direct adjacent candidate exists (same `link_strategy` and `max_link_distance_um` gate), the track is excluded from recovery enrollment.
  - Retained Phase-2 clutter trigger as an independent condition for the remaining tracks.
  - Added telemetry counter `suppressed_by_direct_candidate`.
- Updated `scripts/run_hybrid_submission.py`:
  - Passed `current`, `max_link_distance_um`, and `link_strategy` into `enqueue_kinematic_tracks(...)` so exclusion runs in the CFAR hybrid path.
- Added/updated tests in `tests/test_kinematic_recovery.py`:
  - Assert recovery enrollment is blocked when a direct adjacent candidate exists, even with trigger-satisfying context.
  - Assert genuine-gap behavior is preserved when no direct candidate exists and trigger condition holds.

Guardrail respected: production `run.py` path untouched.

## Validation Method

Reused the exact V16 cohort and metric discipline:

- Script: `scripts/run_v16_kinematic_validation.py`
- Output: `submissions/v17_hard_exclusion_validate.json`
- Cohorts:
  - routed CFAR: 66
  - at-risk: 51
  - outside: 15
- Metric:

$$
quality\_score = 0.5 \cdot sparse\_recall + 0.5 \cdot sparse\_edge\_recall
$$

## Before/After vs V16

Mean quality delta (ON minus OFF):

- Routed 66:
  - V16: `-0.010271660974730087`
  - V17: `-0.0008137769999022116`
- At-risk 51:
  - V16: `-0.011172147867127648`
  - V17: `-0.0008840900458504615`
- Outside 15:
  - V16: `-0.007210005540578379`
  - V17: `-0.0005747126436781621`

Mean sparse edge recall delta:

- Routed 66:
  - V16: `-0.02054332194946017`
  - V17: `-0.0016275539998044232`
- At-risk 51:
  - V16: `-0.022344295734255296`
  - V17: `-0.001768180091700923`
- Outside 15:
  - V16: `-0.014420011081156751`
  - V17: `-0.0011494252873563242`

Regression counts (quality delta):

- Routed 66:
  - V16: 24 regressed
  - V17: 7 regressed
- At-risk 51:
  - V16: 19 regressed
  - V17: 6 regressed
- Outside 15:
  - V16: 5 regressed
  - V17: 1 regressed

V16 regressed set carryover:

- V16 regressed samples: 24
- Fixed in V17 (non-negative): 17
- Still regressed in V17: 7

Edge-level follow-up on the original V16 diagnostic set (`submissions/v16_diagnostic_root_cause.json`):

- Original V16 regressed Type-1 edges: 66
- Fixed in V17: 56
- Still regressed in V17: 10
- Missing eval due to unmatched nodes: 0
- Artifact: `submissions/v17_hard_exclusion_edge_followup.json`

## Residual Analysis: The 10 Still-Regressed Edges

I re-ran the exact V17 singleton direct-link query used by `enqueue_kinematic_tracks(...)` against the 10 still-regressed edges.

The V16 diagnostic had marked all 66 original regressions as having a direct adjacent candidate within link radius. However, the V17 gate-level check did not behave uniformly on the 10 residuals:

- 9/10 residual edges returned no direct edge from the hard-exclusion singleton query.
- 1/10 residual edges returned a direct edge, but to a different target than the regressed edge (`6bba_786893ac`, `t4 -> t5`).

Classification summary:

- Sub-case A, upstream detection gap: 0/10
- Sub-case B, direct-link criteria mismatch or exclusion-eligibility mismatch: 10/10
- Sub-case C, multiple competing frame-skip candidates: 0/10

Interpretation:

- These residuals are not explained by a frame-skip-vs-frame-skip scoring problem.
- Option 2 (steeper frame-skip discount vs. direct edges) is not the right next lever for these 10 cases, because the remaining failures are already outside that competition pattern.
- The next fix should target the direct-link eligibility / criteria alignment between the baseline linker and the hard-exclusion precheck before considering any further penalty shaping.

## Activation Behavior Under Hard Exclusion

Hard exclusion did not collapse recovery activity to near-zero:

- Hybrid samples with nonzero recovered edges: 65/66
- Total recovered edges (hybrid route): 3821
- Mean recovered edges per hybrid sample: 57.89393939393939

Interpretation: the exclusion gate removed much of harmful competition while recovery still activates broadly for gaps that pass the trigger.

## Go/No-Go Decision

**No-Go for promotion at this stage.**

Reasoning:

- V17 removes most of the V16 regression magnitude and resolves the majority of previously regressed samples.
- However, aggregate deltas remain slightly negative across routed, at-risk, and outside cohorts.
- The branch should not be promoted as a submission candidate until deltas are at least flat-to-positive on the target at-risk cohort.

## Next Step Recommendation

Fix the direct-link criteria alignment first, then reassess any penalty shaping:

- The residual 10 edges are not a clean frame-skip-vs-frame-skip scoring case.
- Option 2 may still help the broader cohort, but it is not the immediate fix for these residuals.
- The higher-value next step is to align the hard-exclusion precheck with the baseline linker's direct-candidate eligibility so the gate and the diagnostic mean the same thing.

If that alignment does not clear the remaining negatives, then revisit **Option 2** as a broader scoring refinement before moving to **Option 3** (explicit two-pass linking).
