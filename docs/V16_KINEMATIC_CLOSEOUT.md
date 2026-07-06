# V16 Kinematic Soft-Linking Close-Out

Status: **NO-GO**.

This branch tested the V16 kinematic soft-linking layer as an opt-in, CFAR-only
recovery mechanism behind a default-off gate. The goal was to reuse the exact
real train-eval metric from the earlier V15 comparison on the same routed CFAR
cohort:

- routed CFAR cohort: 66 samples
- at-risk cohort: 51 samples with `collapse_risk_by_pfa["1e-03"] == true`
- outside cohort: 15 routed-but-not-at-risk samples

Validation artifact:

- [submissions/v16_kinematic_validate.json](../submissions/v16_kinematic_validate.json)

Metric used:

$$
quality\_score = 0.5 \cdot sparse\_recall + 0.5 \cdot sparse\_edge\_recall
$$

## What Was Shipped

- Added `src/atabey/tracking/kinematic_recovery.py` with a real-node-to-real-node
  recovery module.
- Wired the new path into the CFAR route in both hybrid runners behind
  `--enable-kinematic-recovery`.
- Added `scripts/run_v16_kinematic_validation.py` to run OFF vs ON against the
  exact 66-sample CFAR validation cohort and split the results into the 51/15
  subcohorts.

## Validation Result

The recovered path did not improve the real metric on the target cohort.

- Routed 66-sample cohort: mean quality delta `-0.01027`
- At-risk 51-sample cohort: mean quality delta `-0.01117`
- Outside 15-sample cohort: mean quality delta `-0.00721`

Sparse recall was unchanged in aggregate. The degradation came from sparse edge
recall:

- Routed cohort: mean sparse edge recall delta `-0.02054`
- At-risk cohort: mean sparse edge recall delta `-0.02234`
- Outside cohort: mean sparse edge recall delta `-0.01442`

Per-cohort counts from the validation run:

- At-risk cohort: 0 improved, 19 regressed, 32 unchanged
- Outside cohort: 0 improved, 5 regressed, 10 unchanged

## Decision

NO-GO for V16 promotion.

The layer is bounded, default-off, and auditable, but it does not improve the real
target cohort and it also regresses outside-cohort samples. The branch stays as
documented experimental history, not a submission candidate.

## Follow-Up

If this line of work is revisited, the next candidate should narrow the recovery
trigger or revisit the cost model before any broader integration.