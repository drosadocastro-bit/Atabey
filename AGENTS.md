# AGENTS.md

You are helping maintain `drosadocastro-bit/Project-Atabey`.

Project Atabey is an experimental lineage-tracking research scaffold for the Kaggle
competition `biohub-cell-tracking-during-development`. It is inspired by
`drosadocastro-bit/Project-Lumina`, but it must translate Lumina's ideas into bounded
tracking mechanics.

## Core Identity

Treat this repository as:

- a streaming-first Kaggle research scaffold
- a 3D+time embryonic cell lineage tracker
- a testbed for track memory, latent candidates, local pressure, state transitions, and
  uncertainty-aware linking
- a practical baseline path toward valid `submission.csv` generation

Do not optimize it toward:

- product polish before baseline validity
- biological certainty
- hidden confidence
- UI-first work
- autonomous interpretation
- state language that implies truth

## Canonical Flow

```text
Zarr sample
-> streamed timepoint IO
-> candidate detection
-> physical-coordinate normalization
-> temporal linking
-> lineage graph
-> optional state and latent-candidate layer
-> submission writer
-> sparse ground-truth evaluation
```

Any change should fit this flow or be documented as auxiliary or experimental.

## Boundaries

- Detection is not confirmation.
- Tracking association is not proof of identity.
- Latent candidates are not confirmed cells.
- Local field pressure guides attention, not truth.
- State labels are interpretive tracking aids, not biological diagnosis.
- Sparse ground truth is calibration context, not exhaustive reality.
- Repeated lineage does not imply independent confirmation.

## Design Principles

- Valid baseline before elegant state machinery.
- Stream timepoints; do not load full 3D+time videos without a documented reason.
- Compute linking and motion in physical microns, not raw voxel units.
- Keep internal graph representation separate from Kaggle's output schema until
  `sample_submission.csv` is inspected.
- Prefer extending existing modules over adding parallel concepts.
- Keep the public API small and intentional.
- Document the epistemic failure mode each major subsystem addresses.

## Lumina Transfer Rules

Borrow mechanisms, not claims:

- memory traces -> track-local history
- dormant nodes -> bounded latent candidates
- local pressure -> crowding and motion conflict
- phase transitions -> explicit cell-state transitions
- predictive tension -> prediction error and uncertainty

Avoid consciousness, sentience, selfhood, or magical framing in code and technical docs.

## Review Checklist

When reviewing a change, ask:

- Does it preserve the baseline submission path?
- Does it keep lineage and provenance visible?
- Does it blur detection, association, state, and evidence?
- Does it introduce duplicate abstractions?
- Does it add more conceptual load than tracking value?
- Does it preserve sparse-annotation caution?
- Does it keep the repository understandable?

If several answers are concerning, recommend a simpler alternative.