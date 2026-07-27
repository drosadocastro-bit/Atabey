# V22 E016 Joint Semantic Ranking With Local Assignment Constraint

Date: 2026-07-27
Status: preregistered design only; no scorer fit, assignment solve, or graph mutation

## Purpose

This is the E016 clean-checkpoint successor to the earlier V22 semantic-action
experiment. It uses only the downloaded 46-event development artifact produced
by the frozen U-Net checkpoint. The earlier 268,822-action/39-positive-event
contract is not reused because the new checkpoint produces a different candidate
population and different official-positive availability.

## Frozen E016 Population

- 27 sample-blocked development samples and 46 registered events.
- 211,328 division actions.
- 40 events with at least one patched-official positive action.
- 55 patched-official TP actions.
- 25 previously unavailable baseline events, of which 20 become available.
- 13 positive controls, of which 12 are preserved; the missed `t=0` control has
  no prior-frame anchor under the formation contract.
- Source graph mutation, semantic scoring, assignment, and edge inference remain
  disabled in the source artifact.

## Fold Contract

Three folds contain nine complete samples each. The deterministic frozen split
uses seed `v22-e016-semantic-fold-220727`, pins the only local-maxima sample
`44b6_5f15d135` to fold 3, and yields 14/13/13 official-positive events and
16/15/15 registered events. This replaces the obsolete 13/13/13 expectation
from the prior checkpoint. Local-maxima metrics remain separate and carry the
explicit caveat **unproven generalization**.

The machine-readable contract is:

`tests/fixtures/v22_e016_joint_semantic_assignment_development.json`

## Scoring And Labels

The semantic model is an interpretable, L2-regularized pairwise ranker trained
only on patched-official TP versus directly scored patched-official FP actions
within training folds. Unsupported and unevaluated actions remain unknown: they
are retained in held-out ranking and assignment pools but never become convenient
negative labels. Event weighting is equalized before action weighting.

Features remain parent-centered and explicitly masked when unavailable. Geometry,
continuity, detector confidence, local density, and validated non-motion evidence
may be reported according to the existing feature contract. No ownership cost or
assignment outcome may be used as a semantic feature.

## Constraint Layer

The assignment stage is shadow-only and local. It operates on connected conflict
components within one sample and event frame, with division actions consuming two
daughters atomically, continuation actions consuming one daughter, and explicit
terminate/abstain outcomes. It must enforce exclusive anchor, parent-peak, and
daughter-peak ownership. A timeout, numerical failure, missing feature, or
uncalibrated semantic margin produces abstention rather than a forced choice.
No source graph is mutated.

## Validation Contract

Report out-of-fold results by fold, family, route, sample, and event. Local-maxima
results are descriptive only and excluded from pooled GO decisions. Required
comparisons are semantic ranking without the constraint versus the same scores
with the local constraint. The constraint may not increase semantic confidence.

A successful shadow result must satisfy the existing retrieval floors, retain
both families, preserve all source graphs, produce zero ownership violations,
and lose no more than one positive event relative to unconstrained semantic
scores. Any failure is HOLD or NO-GO for shadow projection; it never authorizes
production graph mutation or a full-199 run.

## Boundary

This experiment measures conditional retrieval among officially evaluable action
labels. It does not estimate biological truth probability, full-candidate
precision, or competition score. The 199-sample scope remains locked until this
contract passes its development-only gates.
