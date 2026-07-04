# ADR-004: Latent Cell Candidates

## Status

Proposed.

## Decision

Weak detections may be retained for a short, bounded window as latent candidates after
the baseline detector and tracker are valid.

## Rationale

Sparse, noisy, or transient cell signals can be lost by hard thresholding. Lumina's
dormant-node idea is useful here only when translated into a bounded tracking mechanism.

## Boundaries

- Latency is not confirmation.
- Promotion requires temporal evidence.
- Latent candidates must expire.
- The mechanism must be measured against false positives and lost tracks.
