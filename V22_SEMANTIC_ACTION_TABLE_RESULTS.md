# V22 Semantic Action Table Results

Status: **GO TO CONTINUATION-REFERENCE AVAILABILITY AUDIT**

This document records the completed frozen 27-sample development evidence build.
It does not report semantic-model or constrained-assignment performance.

## Contract Integrity

- Completed samples: **27/27** across folds 1, 2, and 3.
- Actions: **268,822/268,822**.
- Registered official-positive actions: **64/64**.
- Positive events: **13 per fold**, 39 total.
- Duplicate action IDs: **0**.
- Shard hash failures: **0**.
- Unregistered official TP discovered by sampled labeling: **0**.
- Source zero perturbation: **true**.
- Semantic scores present: **0**.
- Assignment selections: **0**.
- Graph mutations: **0**.

The action, peak, and experiment-contract hashes match the pinned inputs.

## Label Population

Of 268,822 actions, 3,246 were selected by the frozen direct-scoring design:

| State | Count | Interpretation |
|---|---:|---|
| `official_tp` | 64 | Eligible supervised positive |
| `official_fp` | 518 | Eligible supervised negative |
| `official_unsupported` | 2,664 | Unknown; excluded from supervised loss |
| `not_evaluated` | 265,576 | Retained for ranking/assignment; excluded from loss |

Unsupported actions are **82.1%** of the directly scored sample. This confirms
that sparse absence cannot be treated as a negative. The 64 TP and 518 FP form
the officially evaluable supervised population; their sampled ratio is not a
biological prevalence or precision estimate.

Conflict sampling was materially more efficient than background sampling:

- conflict sample: 442 FP and 1,377 unsupported;
- background sample: 90 FP and 1,331 unsupported;
- 58 actions carried both selection reasons.

The overlap explains why reason totals exceed the 3,246 unique scored actions.

## Fold Distribution

| Fold | Actions | Selected | TP | FP | Unsupported | Positive events |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 44,402 | 957 | 20 | 144 | 793 | 13 |
| 2 | 192,869 | 1,229 | 24 | 161 | 1,044 | 13 |
| 3 | 31,551 | 1,060 | 20 | 213 | 827 | 13 |

Positive events are perfectly balanced, but raw action volume is not: fold 2
contains **71.7%** of all actions. The three events from `6bba_57b7cc1e` alone
contain 134,880 actions, **50.2%** of the full table. The pre-registered equal
event weighting and within-event pairwise training are therefore mandatory.
Action-level random splitting or unweighted loss would be invalid.

## Family And Route

| Group | Actions | TP | FP | Unsupported |
|---|---:|---:|---:|---:|
| `44b6` | 55,917 | 7 | 77 | 430 |
| `6bba` | 212,905 | 57 | 441 | 2,234 |
| `cfar_sidelobe/bipartite` | 218,024 | 15 | 138 | 903 |
| `components/greedy` | 44,180 | 45 | 341 | 1,609 |
| `local_maxima/motion_mutual` | 6,618 | 4 | 39 | 152 |

All routes and both families retain officially evaluable positives. Route and
family must remain reporting strata because their candidate populations differ
substantially.

The local-maxima row comes entirely from one sample in fold 3. It is descriptive
availability evidence, not route-generalization evidence. Any future performance
metric involving this route must be reported separately as **unproven
generalization**: folds 1 and 2 have no held-out local-maxima sample, and the
fold-3 held-out evaluation is zero-shot because local-maxima is absent from its
training folds.

## Decision

The evidence-table build is a **GO**. It satisfies the pinned population and
zero-perturbation contracts and provides enough official TP/FP actions to begin
fold-safe ranking research.

Model fitting is not the immediate next step. The coupled assignment design also
requires a continuation-compatibility head, and its independent weak-reference
population has not yet been measured. The next bounded task is a read-only V19
continuation-reference availability audit using the pre-registered criteria:

- mutual-nearest continuation;
- single incoming and single outgoing ownership;
- persistence for at least three frames;
- exclusion within two frames of every registered division;
- counts by fold, family, route, and sample;
- candidate-alternative counts inside the 14 um local ownership radius.

Only after that audit confirms sufficient, balanced references should the
continuation table be built and the out-of-fold semantic ranker be fit. The full
199-sample scope remains locked.