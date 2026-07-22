# V21 Local Assignment Shadow Audit

## Scope

This is a read-only shadow diagnostic. It does not alter Track A, Track B, graph edges,
candidate formation, or production linking. Each focal daughter-pair hypothesis reserves
only its two proposed cells; Hungarian assignment is then solved only for parents that
already own or mutually claim either reserved cell.

Ranking is lexicographic: (1) fewer displaced competing parents, (2) lower added
continuation prediction cost, and (3) the existing balanced Track B score. This avoids
mixing physical distance and Track B confidence in an arbitrary weighted scalar.

## Why 10 of 20 Phase 2 cases were unevaluable

The sparse centroid matcher uses same-timepoint detections, a 7 um radius, greedy
one-to-one matching, and no lineage edges. Therefore a daughter claimed by another parent
or a parent outside the bounded future window cannot make a detection disappear from this
evaluation. Across 12 missing GT nodes in the 10 cases:

- 7 were localization gaps between 7 and 14 um.
- 2 were detection/localization gaps beyond 14 um.
- 2 were recovered by a global distance-ordered matcher, proving standard match-order artifacts.
- 1 was one-to-one evaluator contention; that sample also had a parent beyond 14 um.

At sample level, 8/10 were primarily detection/localization failures and 2/10 were matcher-order
artifacts. This is separate from lineage ownership contention, although both can occur in the
same sample.

## Pre-registered decision rule

Proceed beyond this bounded shadow experiment only if the median correct-pair rank improves,
no correct-pair case regresses, and at least 10/14 correct pairs rank first. Passing does not
authorize Track A/B integration.

## Results

- Correct-pair ranks improved/flat/regressed: **9/2/3**.
- Top-1 correct pairs: **2/14 before, 6/14 after**.
- Median correct-pair rank: **6 before, 3 after**.
- Zero perturbation: **14/14**.
- Decision: **NO-GO for broader rollout**.

| Case | Phase | Base rank | Local rank | Pairs | Competitors | Disputed targets | Displaced | Cost increase um |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P2-12DF | phase2 | 2 | 4 | 9 | 2 | 2 | 1 | 0.000 |
| P2-2A2E | phase2 | 7 | 8 | 11 | 1 | 1 | 1 | 0.000 |
| P2-587A | phase2 | 5 | 3 | 5 | 2 | 2 | 1 | 0.000 |
| P2-D754 | phase2 | 2 | 1 | 3 | 0 | 0 | 0 | 0.000 |
| P1-05DB | phase1 | 6 | 1 | 11 | 0 | 0 | 0 | 0.000 |
| P2-207C | phase2 | 6 | 3 | 15 | 1 | 1 | 0 | 0.000 |
| P2-32DB | phase2 | 16 | 6 | 17 | 2 | 2 | 0 | 5.932 |
| P2-4FFD | phase2 | 4 | 6 | 7 | 1 | 1 | 1 | 0.000 |
| P2-55B7 | phase2 | 1 | 1 | 1 | 0 | 0 | 0 | 0.000 |
| P2-705E | phase2 | 1 | 1 | 9 | 0 | 0 | 0 | 0.000 |
| P1-B329 | phase1 | 11 | 1 | 21 | 0 | 0 | 0 | 0.000 |
| P1-EBDF-EARLY | phase1 | 6 | 1 | 21 | 0 | 0 | 0 | 0.000 |
| P1-EBDF-LATE | phase1 | 11 | 3 | 23 | 0 | 0 | 0 | 0.000 |
| P2-F8FF | phase2 | 18 | 6 | 21 | 1 | 1 | 0 | 0.301 |

## Interpretation

A GO means only that local ownership contention is informative in this fixed battery.
A NO-GO means Hungarian assignment, in this scoped formulation, does not reliably identify
the true daughter pair and should not be expanded into a frame-wide solver.
