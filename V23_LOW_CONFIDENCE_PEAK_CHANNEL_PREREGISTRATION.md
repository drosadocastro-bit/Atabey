# V23 Low-Confidence Peak Channel Preregistration

Status: **development-only, read-only shadow**.

## Purpose

Test a radar-inspired two-channel detector without weakening or replacing the
frozen CFAR path:

- **Primary channel:** the existing CFAR detector, unchanged.
- **Echo channel:** a lower-confidence local-peak pool that may preserve weak
  parent or daughter evidence missed by the primary channel.

The echo channel does not emit production detections, mutate candidates, add
edges, or alter lineage graphs.

## Population

Use the fixed 11-event CFAR development battery:

- seven events lacking official 7 um / 14 um fork geometry at raw CFAR;
- four events where the frozen detector already provides valid geometry.

The four valid events are preservation controls. Sparse GT is used only to
measure availability around registered divisions, not to label unrelated peaks
as false cells.

## Frozen Primary

- global floor: `0.50`;
- adaptive threshold: `background_mean + 1.10 * background_std`;
- local-maximum footprint: `(1, 5, 5)` voxels;
- maximum retained detections: `900` per frame.

## Echo Response Surface

The echo channel uses a fixed `(1, 3, 3)` local-maximum footprint and is measured
over the Cartesian grid:

- global floors: `0.45, 0.40, 0.35, 0.30, 0.25`;
- adaptive multipliers: `1.10, 0.80, 0.50`.

This grid is diagnostic. No operating point will be promoted from recovery
alone.

## Measurements

For every profile:

- official geometric availability after union with the frozen primary;
- recovery count among the seven failures;
- preservation count among the four controls;
- added echo candidates per frame: median, p90, and maximum;
- total candidate inflation relative to the frozen primary.

Results must separate the seven failures from the four controls and report
families explicitly.

## Decision Contract

- **NO-GO:** no recovery, any control loss, or recovery requires unbounded
  candidate inflation.
- **HOLD:** recovery exists but no clearly bounded Pareto point is present.
- **GO TO CONDITIONED ROUTER DESIGN:** at least one Pareto profile recovers
  multiple failures while preserving all controls and leaves a candidate pool
  small enough to be gated by prediction, continuity, and ownership evidence.

A GO does not authorize graph integration. It authorizes design of a
track-conditioned router that decides where the echo channel may be consulted.

## Guardrails

- Normalized microscopy intensity is not interpreted as literal decibels.
- Sparse unlabeled regions are not counted as false positives.
- The primary CFAR path remains frozen.
- No full-199 run follows directly from this bounded response audit.
