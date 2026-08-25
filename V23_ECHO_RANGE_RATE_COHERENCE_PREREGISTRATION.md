# V23 Echo Range-Rate Coherence Preregistration

Status: **development-only, read-only diagnostic**.

## Purpose

Test a Doppler-like refinement of the anchored echo channel. Instead of asking
only whether two distinct returns exist at `t+2`, ask whether those returns carry
the parent track's pre-division motion and preserve the daughter-pair separation
vector. This directly addresses the 97.4%-99.9% non-TP return prevalence found
by the temporal-persistence audit.

## Frozen Scope

- The two anchored events in `v23_split_echo_paths.json`.
- The parent-present link-identity failure and missing-parent failure remain
  quarantined and cannot affect the score or decision.
- Frozen V19/CFAR graph, echo profile (`floor=0.35`, `k=0.80`, footprint
  `(1,3,3)`), `14 um` formation radius, `3 um` deduplication radius, and `9 um`
  return gate.
- Existing parent and child edges remain immutable.

Ground truth is used only after proposal construction and scoring to identify
registered-valid ranks and score percentiles.

## Range-Rate Construction

For each parent with exactly one retained child:

1. estimate parent velocity from its unique `t-1 -> t` predecessor; use zero
   velocity only when that predecessor is unavailable;
2. form each distinct frame-`t+1` echo counterpart inside `14 um`;
3. project retained child and counterpart to `t+2` by adding parent velocity;
4. enumerate return pairs inside `9 um` of those projections;
5. require exclusive returns and choose the highest fixed coherence score.

## Fixed Coherence Score

`score = 0.45 * anchored_pair_score`
`      + 0.20 * retained_velocity_coherence`
`      + 0.20 * counterpart_velocity_coherence`
`      + 0.10 * separation_vector_coherence`
`      + 0.05 * mean_return_evidence`

- velocity coherence is `max(0, 1 - velocity_residual / 9 um)`;
- separation coherence compares the daughter separation vectors at `t+1` and
  `t+2` with the same `9 um` residual scale;
- primary return evidence is `1.0`; echo evidence is its clipped CFAR margin.

No weight, gate, or fallback is fitted from either event.

## Measurements

- parent, counterpart, and global proposal rank before versus after coherence;
- correct-proposal return sources and velocity residuals;
- percentile of the correct proposal within the non-TP coherence distribution;
- family and velocity-mode breakdown;
- zero perturbation.

## Decision Contract

- `GO_TO_LARGER_RANGE_RATE_SHADOW`: both events have exclusive coherent returns,
  both correct proposals are at or above the non-TP p90, neither parent nor
  counterpart rank regresses, and at least one parent improves by 25% or reaches
  top 25.
- `HOLD_RANGE_RATE_SIGNAL`: both events have returns and both correct proposals
  exceed the non-TP median, but the GO ranking conditions are not met.
- `NO_GO_RANGE_RATE`: a correct proposal lacks exclusive returns, falls at or
  below the non-TP median, or its counterpart rank regresses by more than 25%.

No outcome authorizes graph mutation, threshold tuning, or full-cohort work.
