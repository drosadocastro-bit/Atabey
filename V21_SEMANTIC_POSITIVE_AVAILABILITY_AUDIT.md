# V21 Semantic Positive Availability Audit

Status: read-only prerequisite audit; no model fit, threshold tuning, assignment solve, or graph mutation

## Contract

Each row represents one distinct known GT division. A division counts as available only
when at least one parent-centered action projects as a true positive through the patched
official scorer. Candidate multiplicity never increases the positive count. Sparse absence
is not treated as a negative label.

## Split Results

| Split | Samples | GT divisions | Official positives | 44b6 positives | 6bba positives | Zero perturbation | Minimum met |
|---|---:|---:|---:|---:|---:|---:|---:|
| `development` | 27 | 46 | 13 | 0 | 13 | True | False |
| `calibration` | 27 | 47 | 7 | 1 | 6 | True | False |

## Failure Modes

| Split | Status | Count |
|---|---|---:|
| `development` | `fewer_than_two_daughter_lineages_within_7um` | 12 |
| `development` | `no_pair_inside_14um_formation_radius` | 2 |
| `development` | `no_parent_detection_within_7um` | 11 |
| `development` | `official_positive` | 13 |
| `development` | `projected_actions_not_official_tp` | 8 |
| `calibration` | `fewer_than_two_daughter_lineages_within_7um` | 16 |
| `calibration` | `no_pair_inside_14um_formation_radius` | 4 |
| `calibration` | `no_parent_detection_within_7um` | 11 |
| `calibration` | `official_positive` | 7 |
| `calibration` | `projected_actions_not_official_tp` | 9 |

## Aggregate Interpretation

Across both sample-blocked pools, only **20/93 (21.5%)** known GT divisions have at least one
currently representable action that the patched official scorer recognizes as a TP:

- development: **13/46 (28.3%)**;
- calibration: **7/47 (14.9%)**.

The shortfall is not one confidence-threshold problem:

- **28/93** divisions have fewer than two daughter lineages detected within the official 7 um
  matching radius;
- **22/93** have no parent detection within 7 um;
- **6/93** have the required detections but no pair inside the frozen 14 um formation radius;
- **17/93** produce at least one projected action, but none is an official TP;
- **20/93** have an official-positive action.

The route and family distribution is also material. Development contains **0/6** positive `44b6`
divisions and **13/40** positive `6bba` divisions, so it fails the preregistered family-coverage rule
independently of the 20-positive minimum. All 13 development positives come from
`components/greedy`. Calibration contains one `44b6` and six `6bba` positives; its seven positives
span `cfar_sidelobe/bipartite` (2), `components/greedy` (4), and
`local_maxima/motion_mutual` (1).

These route counts are descriptive, not causal. The pools were blocked by sample and balanced by GT
division count, not powered for route-specific inference.

## Decision

**NO-GO for calibrated semantic scoring:** the complete preregistered gate has not been satisfied.

No calibrated confidence, semantic model fit, assignment solve, or production integration is
authorized. The result redirects the next diagnostic upstream: parent/daughter detection and
officially valid action formation must improve before a confidence model can be supported. The 20
available positives may support bounded exploratory feature inspection in development, but
calibration outcomes may not guide feature selection and every candidate remains abstaining.

The locked 20-sample validation cohort was not opened or used. This audit does not
authorize production graph mutation; it only determines whether enough official-positive
actions exist to begin development under the preregistered contract.
