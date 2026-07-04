# ADR-002: Timepoint Streaming Design

## Status

Accepted.

## Decision

Atabey reads and processes one timepoint at a time unless a later experiment documents a
clear need for a larger temporal window.

## Rationale

The competition data is 3D+time image data exposed through Zarr shards. Loading complete
videos is risky for memory, runtime, and Kaggle reproducibility.

## Consequences

- IO adapters expose timepoint reads.
- Detection operates on a 3D volume for one timepoint.
- Tracking receives detections grouped by adjacent timepoints.
