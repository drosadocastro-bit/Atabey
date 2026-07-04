# ADR-006: Sparse Annotation Caution

## Status

Accepted.

## Decision

Ground-truth evaluation must treat sparse annotations as calibration and partial evidence,
not as an exhaustive list of all cells.

## Rationale

Sparse annotation can support centroid calibration, motion ranges, and division behavior,
but extra detections should not automatically be interpreted as false positives without
understanding the annotation protocol.

## Consequences

- Report approximate recall and centroid error.
- Avoid over-penalizing extra detections in internal analysis.
- Document metric limitations beside any score.

## Implemented Calibration Report

`evaluate_sparse_ground_truth` reports matched sparse-node count, approximate sparse recall,
matched centroid error, matched sparse-edge recall, and predicted-to-estimated node ratio.
These are calibration signals for comparing baseline settings, not a replacement for the
official Kaggle metric.

Important limits:

- unmatched predictions are not automatically false positives because annotations are sparse
- sparse recall is only about annotated nodes, not all visible cells
- sparse-edge recall only considers edges whose two endpoints were matched first
- predicted-to-estimated node ratio is meaningful only when the predicted graph covers the same
  time span as the estimate
- partial-timepoint smoke tests should be used to verify mechanics, not to judge full-sample quality
