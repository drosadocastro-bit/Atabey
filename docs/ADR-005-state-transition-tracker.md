# ADR-005: State Transition Tracker

## Status

Proposed.

## Decision

Atabey may add explicit cell states such as stable, moving, pre-division, occluded, lost,
uncertain, and latent after the deterministic graph path works.

## Rationale

State can make lineage behavior reviewable: why a track continued, paused, branched, or
was marked uncertain.

## Boundaries

- State labels are interpretive, not biological diagnosis.
- State must not hide weak evidence or contradictions.
- State should explain decisions rather than replace measurable evidence.
