# V23 Pair-Level Track Qualifier Preregistration

Status: **development-only, read-only diagnostic**.

## Purpose

Test whether coherent daughter-pair geometry can qualify the four frozen K=1
echo recoveries more effectively than single-echo or single-track signals.

## Frozen Population and Inputs

- The four events already established as K=1 recoveries by
  `v23_per_track_echo_budget_shadow.json`.
- Frozen V19/CFAR graph and echo profile (`floor=0.35`, `k=0.80`, footprint
  `(1,3,3)`).
- Router radius `14 um`, primary deduplication radius `3 um`, and broken-parent
  proposal budget `K=1`.

No GT coordinate creates a seed, proposal, pair, or score.

## Pair Construction

- Under-resolved parent: combine frozen primary daughters with local echo
  daughters inside the 14 um parent-centered formation radius.
- Broken endpoint: use its K=1 assigned echo parent, then form local daughter
  pairs around that proposed parent.
- Daughter candidates are deduplicated before pairing and must be distinct.

## Fixed Pair Score

`pair_score = 0.45 * midpoint_closeness`
`           + 0.25 * radial_balance`
`           + 0.15 * separation_support`
`           + 0.15 * candidate_evidence`

- midpoint closeness compares the daughter midpoint with the track motion
  prediction over 14 um;
- radial balance compares the two parent-to-daughter distances;
- separation support rises to one at 3 um and only rejects near-duplicates;
- candidate evidence averages frozen-primary confidence `1.0` and clipped echo
  CFAR margins.

A second signal divides the best pair score by the square root of local pair
count to test density pressure. No weight is fitted from GT.

## Measurements

For each event:

- best valid seed rank among all pair-bearing seeds;
- rank of the first registered-valid pair inside that seed;
- top-5/10/25/50 seed capture;
- top-1/5/10/25 within-seed pair capture;
- family breakdown and zero perturbation.

## Decision Contract

- `GO_TO_PAIR_ASSIGNMENT_SHADOW`: at least 3/4 events have a useful seed in the
  top 25 and a registered-valid pair in that seed's top 10, covering both
  families.
- `HOLD`: at least 2/4 satisfy both conditions.
- `NO_GO`: fewer than 2/4 satisfy both conditions.

No result authorizes graph mutation, candidate emission, fitting, or a
full-cohort run.
