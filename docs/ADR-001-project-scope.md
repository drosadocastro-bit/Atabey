# ADR-001: Project Scope

## Status

Accepted.

## Decision

Atabey is a Kaggle-oriented experimental lineage tracker for 3D+time embryonic cell
videos. It is not a general biological reasoning engine, not an automated truth system,
and not a product.

## Rationale

The project needs enough practical structure to submit to Kaggle, but the conceptual
center is lineage-preserving state over time. The safest first path is a valid,
streaming-first baseline before adding Lumina-inspired state mechanisms.

## Consequences

- The baseline detector and tracker are core.
- The state layer is experimental until it improves or clarifies tracking.
- The submission writer remains provisional until `sample_submission.csv` is inspected.
