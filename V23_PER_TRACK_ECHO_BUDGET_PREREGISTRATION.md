# V23 Per-Track Echo Proposal Budget Preregistration

Status: **development-only, read-only shadow**.

## Purpose

Replace the failed union-of-windows router with a bounded proposal mechanism.
The frozen CFAR graph remains unchanged. The low-confidence echo profile remains
fixed at global floor `0.35`, adaptive multiplier `0.80`, and footprint
`(1,3,3)`.

## Inference-Available Seeds

- Missing-parent path: broken endpoints at `t-1`, projected to `t` by the
  existing constant-velocity rule, with stationary fallback when history is
  unavailable.
- Missing-daughter path: parents at `t` with fewer than two outgoing children,
  using their position for the 14 um formation gate and their motion prediction
  for ranking.
- Echo parents selected from broken endpoints may themselves seed daughter
  proposals at `t+1`.

GT coordinates never create or rank a proposal. They are used only afterward to
measure registered fork availability.

## Proposal Scoring and Constraint

Within each 14 um gate:

`score = 0.70 * prediction_closeness + 0.30 * clipped_cfar_margin`

where prediction closeness is `max(0, 1 - prediction_error / 14)` and the CFAR
margin is clipped to `[0,1]`.

A linear-sum assignment layer enforces:

- candidate ownership capacity `1`;
- per-track proposal budgets `K=1` and `K=2` evaluated separately;
- daughter capacity equal to the number of missing child slots, capped by K;
- explicit dummy assignments, allowing abstention.

Echo peaks within 3 um of a frozen primary detection are duplicates and are not
eligible as new proposals.

## Population and Measurements

Use the fixed 11-event battery: seven failures and four production controls.
Report by budget, family, and event:

- recovered registered fork geometry;
- selected parent and daughter echoes;
- proposal reduction relative to the full echo pool;
- ownership uniqueness and zero perturbation;
- the three previously seedless events separately.

## Decision Contract

- `NO_GO`: neither budget recovers any failed event.
- `HOLD`: recovery exists but K=2 offers no meaningful recovery gain over K=1,
  or proposal counts remain operationally broad.
- `GO_TO_SEMANTIC_SHADOW`: a bounded budget recovers at least two failures,
  preserves all controls, and selects a median of at most two new echoes per
  event-frame.

No result authorizes candidate emission, edge creation, graph mutation, or a
full-cohort run.
