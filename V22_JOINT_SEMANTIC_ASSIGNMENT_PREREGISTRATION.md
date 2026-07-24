# V22 Joint Semantic Ranking With Local Assignment Constraint

Date: 2026-07-24
Status: pre-registered design only; no scorer fit, assignment solve, or graph mutation

## Objective

Design a development-only experiment that ranks the 268,822 V22 U-Net division
actions and includes local ownership constraints from the beginning. The target
is to surface the 64 patched-official positive actions across 39/46 registered
events without converting sparse absence or unsupported actions into convenient
negative labels.

This experiment does not open calibration, locked validation, or the full 199
samples. It does not authorize production graph mutation.

Machine-readable contract:

`tests/fixtures/v22_joint_semantic_assignment_development.json`

## Why Semantics And Constraints Must Be Jointly Evaluated

Two earlier Atabey experiments already showed that local evidence alone is not
enough:

- Track B ranking buried true divisions among geometric lookalikes;
- counterfactual future continuity demoted known wrong pairs but also promoted
  unrelated smooth trajectories;
- local Hungarian ownership improved aggregate rank but regressed 3/14 known
  pairs because exclusivity is not biological evidence.

V22 makes the scale problem explicit: 268,822 actions, median 1,569 and p90
21,146 per event. A semantic scorer that ignores competing claims can repeat the
same failure at a larger scale. Conversely, an assignment solver without a
semantic scorer repeats the prior Hungarian failure.

The experiment therefore evaluates one architecture with two deliberately
separate responsibilities:

1. the semantic model estimates parent-centered action preference;
2. the constraint layer projects those preferences onto a feasible local joint
   action.

The constraint layer may remove conflicts. It may never increase semantic
confidence or contribute an ownership bonus to the score.

## Charged-Particle-Tracking Transfer

The architectural reference is Kortus et al.,
[Constrained Optimization of Charged Particle Tracking with Multi-Agent
Reinforcement Learning](https://arxiv.org/abs/2501.05113). The paper uses local
policies to score candidate hits and a centralized safety layer that solves an
LSAP during training and inference to enforce unique hit ownership. The 2026
follow-up is available from
[Machine Learning: Science and Technology](https://iopscience.iop.org/article/10.1088/2632-2153/ae352b).

The transferable principle is separation of preference from feasibility. The
literal solver is not transferable unchanged:

- a particle track consumes one next hit;
- an Atabey division action atomically consumes two daughters;
- Atabey must also represent continuation and abstention;
- sparse biological labels create an explicit unsupported/unknown state.

A plain one-to-one Hungarian solve is therefore prohibited. Atabey uses a local
coupled binary assignment problem that preserves the LSAP safety-layer role but
supports two-daughter hyperedges.

## Frozen Development Split

The experiment uses only the 27 development samples and 46 registered events
already opened by V21/V22. Source CSVs and their SHA-256 hashes are pinned in the
machine contract.

Three sample-blocked folds are frozen before feature fitting. Each fold contains
nine samples and exactly 13 official-positive events. Each fold also contains
one of the three positive `44b6` samples.

### Fold 1

15 events, 13 official-positive:

- `44b6_74d0c52e`
- `44b6_aaf8b0ea`
- `6bba_3abfe10a`
- `6bba_3c5691b6`
- `6bba_5c824876`
- `6bba_8b7818bf`
- `6bba_d3da753b`
- `6bba_debd7bfa`
- `6bba_fe670320`

### Fold 2

16 events, 13 official-positive:

- `44b6_706092f0`
- `44b6_c50204e0`
- `6bba_57b7cc1e`
- `6bba_5c039895`
- `6bba_6321a359`
- `6bba_67ebd073`
- `6bba_9e23430b`
- `6bba_d2b9fc0c`
- `6bba_ef7b4f7e`

### Fold 3

15 events, 13 official-positive:

- `44b6_5f15d135`
- `6bba_2312ac41`
- `6bba_2819ca14`
- `6bba_3fda6b25`
- `6bba_7d3058ae`
- `6bba_87289e13`
- `6bba_907271db`
- `6bba_cdcfe533`
- `6bba_fc5f39dc`

All normalization, feature selection, regularization, calibration, and decision
thresholds are fit inside the two training folds. The held-out fold cannot guide
changes.

## Label Contract

Every supervised action label comes from the pinned patched official scorer.
The action states are:

- `official_tp`: positive training/evaluation action;
- `official_fp`: eligible negative action;
- `official_unsupported` or not evaluated: unknown, excluded from supervised
  loss and calibration.

Sparse absence is never a negative label. Candidate count is never FP count.
Unknown actions remain in the held-out ranking and constrained solve, where they
can outrank or block known positives; excluding them from the loss does not make
them disappear from the real evaluation.

### Negative sampling

Running the official scorer 268,822 times is not the first experiment. The
training label set contains:

1. all 64 known official-positive actions;
2. directly scored conflict actions sharing an anchor, parent peak, or daughter
   with a positive action, capped at 64 per positive by deterministic hash;
3. 32 score-independent hash-sampled background actions per event.

Only actions returned as `official_fp` become negatives. Unsupported actions are
retained in the candidate table but excluded from supervised loss. Sampling is
performed independently inside each training fold.

## Action Space

For each V19 anchor at `t-1`, the local semantic action set contains:

- `continue(anchor, parent, child)`;
- `divide(anchor, parent, child_1, child_2)`;
- `terminate(anchor)`;
- `abstain(anchor)`.

Division actions are the frozen U-Net actions already enumerated inside 14 um.
Continuation actions are required because legitimate competing ownership cannot
be represented by division actions alone. Abstention is always feasible and is
the required outcome for missing evidence or low-margin assignment changes.

## Semantic Features

The primary scorer uses only pre-registered, parent-centered evidence:

- anchor-to-parent prediction error and parent velocity;
- parent-to-daughter distances, distance ratio, and daughter separation;
- split angle and pair-midpoint prediction error;
- U-Net confidence for parent and daughters;
- local parent/daughter density;
- immediate continuation and divergence when the feature is available;
- competing-claim margins as diagnostics of ambiguity, not positive evidence;
- explicit feature-availability masks and reason codes.

Appearance, mass, and intensity are disabled because they have not passed the
existing independent ablation contract. Missing features are never replaced by
a favorable zero.

## Primary Semantic Model

The decision-eligible model is an L2-regularized pairwise logistic ranker. It is
chosen because 64 positive actions do not support a large opaque model and
because coefficients, masks, and fold stability remain inspectable.

Training pairs compare official TP actions only with directly scored official
FP actions from the same event or local conflict component. Event weights are
equalized before action weights so the 48,686-action CFAR event cannot dominate
the loss.

A nonlinear model may be reported as exploratory only. It cannot determine the
GO decision in this experiment.

### Continuation compatibility

The constraint layer also needs a semantic utility for legitimate continuation
claims. A separate L2-regularized pairwise continuation head is trained only
from high-confidence V19 reference continuations that are mutual nearest,
single-in/single-out, and persist for at least three frames. References within
two frames of a registered division are excluded.

These are weak compatibility references, not ground truth. The head estimates
which U-Net parent/daughter continuation is more compatible with an anchor; it
does not produce biological confidence. Its training remains sample-blocked.

Division and continuation heads are aligned only through a temperature and
margin selected inside nested training folds. If their action utilities are not
separated by the training-fold margin, the local component abstains. Assignment
may not repair an uncalibrated scale mismatch.

Confidence calibration uses nested training-fold Platt scaling on officially
evaluable division actions only, with inverse sampling weights for the frozen
conflict/background sampling design. Calibration is reported conditionally on
the officially evaluable action population. It is called official-action
confidence, not biological truth probability. No fixed 0.60 threshold is
inherited.

## Retrieval And Computational Bound

All 268,822 actions receive a vectorized semantic score. Retrieval is reported
at top 1, 5, 10, and 50 before assignment.

The local solver receives the union of:

- top 16 actions per anchor;
- top 16 actions per claimed daughter;
- all required continuation and abstain actions.

Any truncation is logged. Positive-action retention at this boundary is a
primary metric; a pruned positive is a retrieval failure, not an assignment
failure.

## Local Coupled Assignment Layer

A conflict component is limited to one sample and one event frame. It contains
only actions connected by a shared anchor, parent peak, or daughter peak.
Components are solved independently.

For binary action variable `x_a`, enforce:

- each anchor selects at most one action;
- each parent peak is consumed at most once;
- each daughter peak is consumed at most once;
- a division consumes two daughters atomically;
- a continuation consumes one daughter;
- terminate and abstain consume no daughter;
- time direction, distinct daughter identity, and finite coordinates are hard
  validity constraints.

The objective is the sum of semantic action utilities. Assignment displacement,
conflict count, and ownership cost are not semantic features and cannot raise a
division score.

Each connected component is solved deterministically with
`scipy.optimize.milp`, which supports the coupled two-daughter action directly.
The frozen time limit is 2.0 seconds per component. Timeout, numerical failure,
or an incomplete feasible solution produces abstention for the component; it
never falls back to greedy ownership.

If assignment changes the unconstrained winner and the replacement lacks the
training-fold confidence and margin, the component abstains. No forced repair is
allowed. The three prior Hungarian regression cases remain permanent safety
fixtures.

## Required Paired Evaluation

Although the constraint is built from the start, the same out-of-fold semantic
scores are evaluated in two read-only modes:

1. unconstrained semantic ranking;
2. semantic ranking plus the local coupled constraint.

This is an ablation of responsibility, not a staged fallback. It reveals whether
the safety layer prevents conflicting ownership without hiding a weak scorer.
Neither mode mutates the source graph.

## Metrics

### Retrieval

- action-level official-TP recall at top 1/5/10/50;
- positive-event recall at top 1/5/10/50;
- rank of all 64 known positive actions;
- rank and retention by fold, family, route, and density stratum;
- positive retention after the top-16 union shortlist.

### Constraint behavior

- ownership violations before and after constraint;
- constrained official TP, FP, unsupported, and abstain counts;
- positive events retained or lost solely by the constraint;
- number and size of conflict components;
- solver timeout or candidate-set truncation counts;
- the three historical Hungarian regressions.

Unsupported actions are reported separately and never folded into FP.

## Decision Contract

The top-50 boundary is an explicit review/retrieval budget: it is about 3.2% of
the median 1,569 actions per event and prevents a claim of success based on
placing positives somewhere inside thousands of candidates. The absolute and
per-fold recall floors require broad recovery rather than one dense sample
carrying the aggregate.

A **GO for shadow graph projection design only** requires all of the following:

1. action-level official-TP recall@50 is at least 80%;
2. positive-event recall@50 is at least 85%;
3. every fold has positive-event recall@50 of at least 70%;
4. all 12 anchorable positive controls appear within top 50;
5. at least 75% of positive actions survive the solver shortlist;
6. the constrained solution has zero ownership violations;
7. the constraint loses at most one positive event relative to the same
   unconstrained semantic scores;
8. constrained official division Jaccard does not regress relative to the
   unconstrained mode;
9. both families contribute non-regressing held-out evidence;
10. every source graph passes zero perturbation.

Failure of semantic retrieval cannot be rescued by assignment. Failure of
constraint behavior cannot be excused by semantic rank. A mixed result remains
NO-GO for graph projection.

Passing authorizes only a separately pre-registered shadow projection onto graph
copies. It does not authorize production integration, locked validation, or a
199-sample run.

## Closed And Open Boundaries

Closed for this experiment:

- detector threshold and peak suppression;
- 14 um action formation;
- development membership and folds;
- patched official metric version;
- negative-label and unknown-label policy;
- Track A and Track B behavior.

Open only inside training folds:

- L2 regularization strength;
- feature standardization parameters;
- Platt calibration parameters;
- confidence and ambiguity margins selected by nested training validation.

Still prohibited:

- GT features at inference;
- labeling unsupported actions as negative;
- frame-wide/global assignment;
- ownership bonuses in semantic scores;
- appearance/mass features without their ablation gate;
- forced decisions under missing evidence;
- locked validation or full-199 access.
