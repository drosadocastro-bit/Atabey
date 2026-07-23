# V21 Joint Semantic Scorer And Local Assignment Constraint

Date: 2026-07-23
Status: design plus Phase 0 evidence extraction; no semantic scorer or assignment integration

No scorer, solver, graph mutation, production integration, or submission behavior is authorized by
this document.

## Objective

Design a local division-recovery architecture that combines parent-centered biological evidence with
exclusive daughter ownership. Semantic evidence must decide whether a parent-to-two-daughter event is
plausible. Assignment may only enforce feasibility among already-scored alternatives.

The architecture must support:

- parent-centered split geometry;
- daughter continuity and divergence;
- appearance or mass evidence only after independent validation;
- explicit feature availability and missingness;
- calibrated confidence when sufficient positive evidence exists;
- local ownership constraints as a safety layer, not a scorer;
- one-child continuation and two-child division capacity;
- reject, abstain/flagged, and commit-eligible outcomes.

## Evidence Boundary

This design responds to four established findings:

1. Under the patched official scorer, V19 has `TP=4, FP=6, FN=10` and V20 has
   `TP=0, FP=0, FN=14` in the fixed registered windows. The target is an official division failure,
   not raw candidate volume.
2. All 12 observed wrong-winner events had competing-parent evidence, but the local Hungarian shadow
   regressed on 3/14 correct pairs. Exclusivity is informative but not semantic proof.
3. Future continuity demoted two known wrong pairs, but unrelated smooth tracks often outranked true
   daughters. Continuity is supporting evidence, not shared-parent evidence.
4. The current simple ranking has strongly overlapping TP/FP feature distributions. Volume was
   non-separating and intensity was weak/inconsistent. No current ranking score is calibrated
   confidence.

All four official V19 TPs are already formed correctly by V19, and none requires ownership repair.
This architecture therefore cannot justify itself by claiming to recover those four through LSAP.
It must improve official behavior on currently missed or incorrectly formed divisions while
preserving those existing TPs.

## Failure Target

The primary target is:

> Increase officially matched directed parent-to-two-daughter forks without reducing official
> adjusted edge Jaccard or reopening official division FP at V19 scale.

The architecture is not successful merely because it:

- reduces thousands of sparse-unsupported candidates;
- ranks a known TP above one hand-selected wrong pair;
- satisfies one-to-one ownership;
- produces smooth daughter trajectories;
- improves a local sparse EdgeRecall diagnostic.

Unsupported candidates remain unknown. Official TP/FP/FN and adjusted edge Jaccard are the decision
metrics.

## Local Action Space

For each focal parent `p` at frame `t`, a shadow candidate enumerator observes detections at `t+1`
inside `14 um`. This radius is candidate observation only and does not change normal continuation
linking.

The parent action set is:

1. `continue(p, c)`: one daughter/continuation target;
2. `divide(p, c1, c2)`: two distinct daughter targets;
3. `terminate(p)`: no child in the observed neighborhood;
4. `abstain(p, evidence)`: retain the evidence record without selecting an event.

All daughter pairs inside the observation radius are represented before semantic scoring. If a
resource cap is ever required, truncation must be logged as `candidate_set_incomplete`; it cannot be
treated as a biological rejection.

Candidate formation records whether the sparse GT parent and both daughters are representable during
validation. A missing candidate is an upstream coverage failure, not a scorer FN.

## Semantic Evidence Model

### Parent-centered geometry

Geometry is expressed relative to the parent, not as independent child quality:

- parent-to-child distances and their ratio;
- daughter-to-daughter separation;
- split angle;
- daughter-pair midpoint offset from the parent's predicted position;
- alignment of the split axis with parent velocity, when parent history exists;
- signed radial displacement of each daughter away from the parent;
- immediate separation growth.

No single angle, ratio, or distance becomes a universal hard gate based on the four known TPs.
Physically impossible values may be rejected; plausible-but-unusual values remain scoreable.

### Joint daughter continuity

Continuity is measured for the pair as a parent-conditioned event:

- per-daughter continuation coverage over a bounded horizon;
- constant-velocity prediction error;
- branch-axis drift;
- pair separation growth and non-collapse;
- persistence of both daughters;
- whether smooth continuations belong more naturally to another predecessor.

The scorer must retain the distinction between:

- both daughters continuing coherently from the focal parent;
- two individually smooth cells with unrelated predecessors.

Continuity cannot enter as a standalone pass/fail rule.

### Appearance and mass

Candidate records may contain:

- parent intensity versus daughter intensity sum;
- parent component volume versus daughter volume sum;
- daughter intensity/volume balance;
- detector confidence;
- route and detector provenance.

Current status: **no appearance or mass feature is validated for active scoring**. Volume was
non-separating in the bounded ranking audit, and intensity overlapped substantially. These fields
remain logged but disabled by default.

An appearance group may enter the scorer only if a sample-blocked ablation on development data:

1. improves held-out log loss or Brier score over geometry plus continuity;
2. does not worsen any of the three fixed Hungarian regression cases;
3. has documented availability by route and sample family; and
4. reproduces directionally on the locked independent cohort.

### Missing-feature handling

Every feature group carries:

- a value vector;
- an availability mask;
- a reason code such as `no_parent_history`, `daughter_track_ends`, `no_component_volume`, or
  `route_does_not_emit_feature`;
- the horizon actually observed.

Missing values are never replaced with a favorable zero. Fallback and multi-frame candidates are not
force-ranked through one feature vector as if absent evidence were negative evidence.

The first implementation must use separate mechanism/availability strata or a model that consumes
explicit masks. If a candidate lacks a feature group required by its calibrated stratum, its maximum
outcome is `abstain`.

## Semantic Outputs

The semantic scorer produces, before ownership constraints:

- `division_logit`;
- `continuation_logit`;
- `semantic_margin` between the best and second-best parent actions;
- `feature_availability_pattern`;
- `calibrated_division_confidence`, or `None`;
- complete feature provenance.

The scorer is evaluated before assignment. Displaced-parent count, ownership conflict count, and
Hungarian cost are not semantic features and may not increase division confidence.

## Confidence Calibration

The prior 0.60 Track B threshold is not inherited. It came from a different domain and no current
Atabey score is calibrated.

Calibration requirements:

1. split by sample, never by candidate row;
2. fit only on officially evaluable division labels;
3. report Brier score, log loss, reliability bins, and expected calibration error;
4. preserve mechanism and feature-availability strata;
5. lock the calibration method and decision thresholds before independent validation.

At least 20 officially positive division actions are required before a probability may be called
calibrated. With fewer positives, confidence remains `None`; ranking may be studied, but every
otherwise plausible division routes to `abstain/flagged`.

## Local Ownership Constraint

### Conflict scope

For one focal parent hypothesis, construct a local conflict graph containing:

- the focal parent;
- its proposed daughter detections;
- only parents that currently own or mutually claim one of those daughters;
- their plausible continuation or division alternatives;
- explicit null/abstain actions.

No frame-wide or cohort-wide assignment is authorized.

### Capacitated formulation

Let `x[p,a]` indicate that parent `p` selects action `a`.

Constraints:

- each parent selects at most one action;
- each daughter detection is consumed by at most one selected action;
- a continuation consumes one daughter;
- a division action atomically consumes two daughters;
- terminate and abstain consume no daughter;
- every action must satisfy time direction and finite-coordinate validity.

A plain one-to-one Hungarian solve is insufficient because a division is a coupled two-target
hyperedge. Acceptable future implementations include a small binary optimization, a coupled
min-cost-flow formulation, or duplicated parent slots with an explicit pair-coupling constraint.
Uncoupled duplicated slots are prohibited.

### Objective boundary

The optimizer maximizes the sum of precomputed semantic action scores subject to feasibility. It may
discard a lower-scored conflicting combination, but it may not create an ownership bonus or promote a
biologically weak division merely because it frees a cell.

If the feasible optimum differs from the unconstrained semantic optimum and the replacement lacks a
locked confidence and margin, the outcome is `abstain`, not forced reassignment.

## Decision Outcomes

### Commit-eligible proposal

All conditions must hold:

- candidate set is complete;
- required feature groups for its calibration stratum are available;
- calibrated confidence exceeds the locked threshold;
- semantic margin exceeds the locked ambiguity threshold;
- the local constrained optimum retains the action;
- the solution is stable under removal of any single weak diagnostic feature group;
- no fixed safety invariant fails.

This label remains shadow-only until the full validation contract passes.

### Abstain/flagged

Used when:

- confidence is unavailable or below the commit threshold;
- top actions are semantically near-tied;
- assignment changes the preferred action without strong semantic support;
- required features are missing;
- candidate enumeration was truncated;
- continuation and division evidence conflict.

The full evidence record is emitted without graph mutation.

### Reject

Reserved for structural impossibility, such as duplicate daughter identity, wrong time direction,
non-finite coordinates, or a locked high-confidence non-division decision. Lack of evidence is not
rejection.

## How The Design Avoids The Three Hungarian Regressions

The prior regressions were:

| Case | Base rank | Hungarian rank | Displaced parents | Added cost |
|---|---:|---:|---:|---:|
| `P2-12DF` | 2 | 4 | 1 | 0.000 |
| `P2-2A2E` | 7 | 8 | 1 | 0.000 |
| `P2-4FFD` | 4 | 6 | 1 | 0.000 |

The old lexicographic rank penalized a correct pair for displacing a plausible continuation even when
the added continuation cost was zero. The proposed architecture changes that behavior:

1. semantic rank is computed without ownership penalties;
2. assignment only checks whether simultaneous actions are feasible;
3. a displaced plausible continuation does not make a division more or less biological;
4. when feasibility forces a semantic downgrade without a locked confidence margin, the system
   abstains;
5. each of these three cases is a permanent regression test, and correct-pair semantic rank may not
   worsen relative to its pre-assignment rank.

This does not assume the correct pair must win. It requires the system to flag ambiguity rather than
force the wrong ownership resolution.

## Pre-Registered Validation Contract

### Development and regression battery

The fixed 14 cases from the local-assignment audit remain the development/regression set:

- Phase 1: `P1-05DB`, `P1-B329`, `P1-EBDF-EARLY`, `P1-EBDF-LATE`;
- Phase 2: `P2-12DF`, `P2-207C`, `P2-F8FF`, `P2-4FFD`, `P2-587A`, `P2-D754`,
  `P2-32DB`, `P2-2A2E`, `P2-55B7`, `P2-705E`.

These cases may guide feature debugging and therefore cannot provide the final generalization claim.
The four official V19 TPs must remain representable and officially credited in any projected shadow
graph.

### Locked independent cohort

Before implementation, 20 samples were selected from the 74 non-development samples containing at
least one GT division. Selection used ascending SHA-256 order of
`joint-semantic-assignment-validation-v1:<sample_id>` and did not use route, metric, feature, or model
outcomes.

The locked samples are:

- `6bba_784a78c9`
- `44b6_996155de`
- `6bba_09961292`
- `6bba_085bf656`
- `44b6_d5e7d891`
- `6bba_c328f2fd`
- `6bba_f20478e9`
- `44b6_341df25f`
- `6bba_12665c0e`
- `6bba_7f87b3d8`
- `44b6_9be80b04`
- `44b6_a21120c2`
- `6bba_e16ffc58`
- `44b6_c8e2a523`
- `6bba_337b1b3a`
- `6bba_b204cac7`
- `6bba_786893ac`
- `6bba_d1acb6ff`
- `6bba_48816121`
- `44b6_e28840c6`

The cohort contains 39 registered GT divisions across 13 `6bba` and 7 `44b6` samples. No sample may
be substituted after implementation begins.

### Phase 0: structural tests

Required before real-data scoring:

- source graph zero perturbation;
- deterministic feature extraction;
- explicit missingness for every unavailable field;
- no daughter owned by more than one selected action;
- atomic two-daughter division capacity;
- null and abstain actions always feasible;
- no frame-wide expansion;
- the three Hungarian regression fixtures abstain rather than force a semantic downgrade;
- append-only adversarial battery passes.

### Phase 1: fixed development battery

Report:

- correct-pair rank before and after semantic scoring;
- constrained outcome and abstention reason;
- candidate-formation coverage;
- all four official V19 TP identities;
- official division TP/FP/FN on projected graph copies;
- official adjusted edge Jaccard on projected graph copies;
- zero perturbation of every source graph.

Development advancement requires:

1. no correct-pair rank regression in `P2-12DF`, `P2-2A2E`, or `P2-4FFD`;
2. all four official V19 TPs remain official TPs;
3. no increase above V19's six official FP in the registered windows;
4. no decrease in official adjusted edge Jaccard;
5. every constraint-forced low-margin change abstains.

Passing Phase 1 authorizes only the locked independent shadow run.

### Phase 2: locked independent cohort

All thresholds, feature groups, calibration transforms, horizons, and abstention rules are frozen
before opening results.

Primary metrics:

- official division TP, FP, FN, and Jaccard;
- official adjusted edge Jaccard using `summarize_official_tracking()`;
- per-sample improved/flat/regressed breakdown;
- source zero perturbation.

Secondary diagnostics:

- candidate-formation coverage of registered divisions;
- semantic top-1/top-5/top-10 capture;
- abstention rate and reasons;
- ownership-conflict rate;
- calibration metrics, only if the positive-count requirement is met;
- feature availability by route and sample family.

The architecture is a **GO for integration consideration** only if:

1. every source graph passes zero perturbation;
2. official adjusted edge Jaccard does not decrease in aggregate;
3. official division Jaccard exceeds both frozen V19 and V20 comparators on the same cohort;
4. official division TP is at least V19's TP with no increase in official FP;
5. no sample loses an already-correct official division without gaining a larger official benefit;
6. both sample families contain evaluable non-regressing evidence;
7. no GO claim depends on sparse-unsupported candidate counts;
8. commit-eligible confidence is calibrated under the stated positive-count rule.

If confidence cannot be calibrated, the result may be a GO for continued shadow ranking research but
cannot be a GO for graph integration.

## Reporting Requirements

Every result must separate:

- candidate absent upstream;
- candidate present but semantically rejected;
- candidate semantically plausible but ownership-infeasible;
- candidate abstained for uncertainty or missing features;
- candidate commit-eligible;
- official sparse-unsupported/ignored;
- official TP, FP, or FN.

No raw candidate count may be labeled official FP. Local sparse EdgeRecall remains diagnostic and is
reported separately from official adjusted edge Jaccard.

## Guardrails

- Track A and Track B remain frozen.
- No production graph mutation.
- No threshold selection on the locked independent cohort.
- No frame-wide Hungarian or global correspondence solver.
- No appearance/mass contribution before its ablation contract passes.
- No borrowed confidence threshold.
- No forced decision when evidence is missing or assignment changes a low-margin optimum.
- No full-199 run before the fixed and locked cohorts pass in order.

## Decision State

The read-only Phase 0 extractor is implemented and validated in
[V21_JOINT_SEMANTIC_PHASE0_AUDIT.md](V21_JOINT_SEMANTIC_PHASE0_AUDIT.md). Across the fixed
battery it emitted 585 abstaining evidence rows, represented all 14 registered pairs, preserved
all four original official V19 TPs, kept all three Hungarian regressions visible without forcing a
decision, and passed 14/14 source zero-perturbation checks.

The 14 projected pairs split into seven official TPs and seven official FPs in current ownership
context, confirming that sparse pair identity is not a sufficient training label. No semantic score,
calibration, assignment solve, or graph integration exists. The next action is to pre-register a
sample-blocked development/calibration pool outside the locked 20-sample validation cohort, then
measure whether at least 20 official positive actions are available before fitting any model.
