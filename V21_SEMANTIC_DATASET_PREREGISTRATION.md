# V21 Semantic Development And Calibration Pre-Registration

Date: 2026-07-23
Status: locked before semantic-feature or projected-official-outcome inspection

No model fitting, score construction, confidence calibration, assignment solve, graph mutation, or
submission behavior is authorized by this document.

## Purpose

Phase 0 proved that the joint semantic extractor can represent all 14 fixed registered pairs while
remaining unscored, abstaining, and zero-perturbation. It also showed that registered sparse pair
identity is not a valid binary label: the 14 projected pairs split into seven official TPs and seven
official FPs in current topology.

The next gate is therefore label availability, not model quality:

> Do independent, sample-blocked development and calibration pools each contain at least 20 unique
> GT divisions for which the current graph can form an action that the patched official scorer
> recognizes as a true division?

The answer is measured before any semantic model is fitted.

## Population Accounting

The competition training labels contain:

- 87 samples with at least one GT division;
- 151 GT divisions total.

The following are excluded before splitting:

- 20 samples and 39 divisions in the locked independent validation cohort from
  `V21_JOINT_SEMANTIC_ASSIGNMENT_DESIGN.md`;
- 13 samples and 19 divisions used by the fixed 14-case development/regression battery.

The remaining eligible population is used in full:

- 54 samples;
- 93 GT divisions;
- 10 `44b6` samples with 12 divisions;
- 44 `6bba` samples with 81 divisions.

No eligible sample is dropped.

## Locked Split Method

The machine-readable source of truth is:

`tests/fixtures/v21_semantic_dataset_split.json`

Selection salt:

`v21-joint-semantic-development-calibration-v1`

Within each family:

1. samples are sorted by descending GT division count;
2. ties are ordered by SHA-256 of `<salt>:<sample_id>`;
3. samples are assigned greedily to balance GT division totals;
4. equal sample quotas are enforced;
5. remaining ties use hash parity.

Only sample identity, family, and GT division count are used. No image feature, detector route,
candidate feature, sparse EdgeRecall, official projected result, or model outcome participates.

## Development Split

The development split contains 27 samples and 46 GT divisions:

- `44b6`: 5 samples, 6 divisions;
- `6bba`: 22 samples, 40 divisions.

Samples:

`44b6_5f15d135`, `44b6_706092f0`, `44b6_74d0c52e`, `44b6_aaf8b0ea`,
`44b6_c50204e0`, `6bba_2312ac41`, `6bba_2819ca14`, `6bba_3abfe10a`,
`6bba_3c5691b6`, `6bba_3fda6b25`, `6bba_57b7cc1e`, `6bba_5c039895`,
`6bba_5c824876`, `6bba_6321a359`, `6bba_67ebd073`, `6bba_7d3058ae`,
`6bba_87289e13`, `6bba_8b7818bf`, `6bba_907271db`, `6bba_9e23430b`,
`6bba_cdcfe533`, `6bba_d2b9fc0c`, `6bba_d3da753b`, `6bba_debd7bfa`,
`6bba_ef7b4f7e`, `6bba_fc5f39dc`, `6bba_fe670320`.

Development may later be used for feature debugging and sample-blocked model fitting. It may not be
used to change the locked calibration or validation membership.

## Calibration Split

The calibration split contains 27 samples and 47 GT divisions:

- `44b6`: 5 samples, 6 divisions;
- `6bba`: 22 samples, 41 divisions.

Samples:

`44b6_267148e4`, `44b6_7a302da0`, `44b6_d2f34f90`, `44b6_deabac95`,
`44b6_eb2880fc`, `6bba_062c8d37`, `6bba_07e24132`, `6bba_0e7c0d07`,
`6bba_1d0d8384`, `6bba_20852818`, `6bba_268e1230`, `6bba_3db54e20`,
`6bba_474be664`, `6bba_4f99ce20`, `6bba_61ecbe65`, `6bba_6ca87370`,
`6bba_74686d6a`, `6bba_78a7bd97`, `6bba_7af54fde`, `6bba_80d12824`,
`6bba_969618f6`, `6bba_9a41d029`, `6bba_ab78413d`, `6bba_aeee7805`,
`6bba_afb141ff`, `6bba_bb9f20c3`, `6bba_df673a83`.

Calibration membership and the confidence-eligibility threshold are frozen before projected
official labels are opened.

## Positive-Availability Audit

For each sample:

1. build one frozen V19 pre-firewall graph through the latest labeled division plus the fixed
   continuity horizon;
2. store the actual returned detector and link strategy;
3. enumerate each GT division independently;
4. identify predicted parent detections within the official 7 um radius at the GT parent frame;
5. identify distinct predicted daughter detections within 7 um of the two GT daughters;
6. retain only parent/daughter combinations inside the frozen 14 um formation radius;
7. extract the corresponding unscored semantic evidence action;
8. project that action on a graph copy;
9. score it against only the patched official GT division window;
10. count the GT division once if at least one projected action is an official TP.

Candidate combinations are ordered by total role-matching distance and stable node IDs. The first
official TP is retained as the canonical positive action. Multiple alternatives for one GT division
do not inflate the positive count.

The audit reports separate failures:

- no parent detection inside 7 um;
- one or both daughters absent inside 7 um;
- nodes present but no pair inside the 14 um formation radius;
- action present but no projected official TP;
- official positive action available.

No failure is converted into a verified negative training row during this pass.

## GO Rules

Semantic model work may proceed only if all hold:

1. development contains at least 20 unique official-positive division actions;
2. calibration contains at least 20 unique official-positive division actions;
3. each split contains at least one official-positive action from each sample family;
4. every source graph passes zero perturbation;
5. the locked 20-sample validation cohort remains unopened;
6. no label depends on the old local Division Jaccard implementation.

If calibration has fewer than 20 positives, no output may be called calibrated confidence. Ranking
research may continue in development, but every candidate remains abstaining.

## Guardrails

- Split membership never changes after outcome inspection.
- No model or threshold is fitted during the availability audit.
- Calibration features may be extracted for eventual frozen calibration, but may not guide feature
  selection.
- The locked validation cohort is not built, measured, or inspected.
- Sparse unsupported candidates remain unknown.
- Appearance and mass remain disabled scoring groups.
- Assignment remains disabled.
- No source graph or production path is mutated.

## Decision State

The split and audit contract are pre-registered. The next permitted action is the read-only
official-positive availability run. Only its aggregate availability result may decide whether model
development and confidence calibration are statistically supportable.
