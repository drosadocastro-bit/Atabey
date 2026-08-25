# V23 Track-Seed Ranking Preregistration

Status: **development-only, read-only diagnostic**.

## Question

Can the small subset of graph-derived tracks that enable the four K=1 echo
recoveries be surfaced before proposal assignment using inference-only evidence?

## Frozen Inputs

- V19/CFAR graph and the fixed echo profile (`floor=0.35`, `k=0.80`, footprint
  `(1,3,3)`).
- Router radius `14 um`, primary deduplication radius `3 um`, and proposal budget
  `K=1`.
- The same 11-event development battery.

## Seed Labels

All seeds are generated and scored without GT. After K=1 assignment, GT is used
only to identify which seed supplied a parent or daughter proposal participating
in registered fork recovery. Controls with primary geometry already available
are not treated as positive echo-seed examples.

## Inference-Only Ranking Signals

- `best_echo_score`: strongest local proposal score already used by assignment.
- `gap_score`: clipped distance from motion prediction to the nearest frozen
  primary detection; larger means a less-resolved continuation.
- `combined_score`: 45% echo support, 30% gap, 15% missing-child capacity, and
  10% usable velocity history.
- `density_penalized_score`: combined score divided by the square root of local
  echo count, testing whether sparse local support is more trustworthy.

Ranks are computed independently within each event and stage. Ties use stable
seed identifiers. No score is calibrated from the positive ranks.

## Measurements and Decision

Report the best useful-seed rank per recovered event and signal, plus top-5,
top-10, top-25, and top-50 capture across the four recoveries.

- `GO_TO_TRACK_QUALIFIER_SHADOW`: one inference-only signal captures at least
  3/4 recoveries in top 25 and covers both sample families.
- `HOLD`: best evidence captures at least 2/4 in top 50.
- `NO_GO`: every signal captures fewer than 2/4 in top 50.

This audit cannot authorize candidate emission, graph mutation, score fitting,
or a full-cohort run.
