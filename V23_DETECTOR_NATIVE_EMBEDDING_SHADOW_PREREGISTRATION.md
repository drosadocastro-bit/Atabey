# V23 Detector-Native Evidence Shadow

Date: 2026-07-27
Status: design only; no model modification, assignment, or graph mutation

## Motivation

The E016 metadata ranker improved over detector confidence but failed the
retrieval contract: pooled event recall@50 was 17.95%, and CFAR event recall@50
was 0%. The peak export retained coordinates and confidence but discarded the
U-Net evidence that could distinguish a real daughter from a nearby geometric
lookalike.

The candidate-formation audit also found six misses with different causes. The
next experiment must therefore separate availability from ranking and preserve
the exhaustive 14 um action set while adding detector-native evidence.

## Evidence Export

Use the frozen E016 checkpoint only as a feature extractor. Create a writable
Kaggle working copy of the public support source and export, for each parent and
daughter peak:

- decoder or bottleneck embedding sampled at the physical peak location;
- local pooled feature vector over a small 3D physical neighborhood;
- detector logit/confidence before thresholding;
- explicit crop-boundary and missing-feature flags.

The export must be deterministic, use the same voxel scaling and TTA as E016,
and preserve the checkpoint hash. It must not change peak selection, links,
formation radius, or graph edges.

## Pair Features

For every already-formed action, derive only detector-native pair evidence:

- parent-to-daughter embedding cosine and distance;
- daughter-to-daughter compatibility and embedding separation;
- parent/daughter logit margins against local alternatives;
- temporal embedding persistence when neighboring frames are exported;
- confidence and local density as secondary diagnostics.

Coordinates, velocity, angle, ownership margins, and future graph outcomes are
kept as diagnostic strata or prohibited inputs according to the E016 contract.
No ownership bonus is allowed.

## Validation

Use the frozen E016 sample-blocked folds and patched official labels. Unknown
and unsupported actions remain unknown. Report fold, family, route, sample, and
event strata, with local-maxima marked **unproven generalization**. Compare:

1. confidence/density baseline;
2. embedding-only head;
3. embedding plus allowed detector metadata;
4. a simple nearest-embedding baseline.

A feature head must pass the existing retrieval floors, including CFAR and both
families, before any local assignment shadow is considered. The six unavailable
formation cases are an availability subgroup, not convenient negatives.

## Candidate-Formation Follow-up

Only after the embedding export is validated, run a separate six-case formation
sweep. It may test whether the missing role or correct identity appears under a
pre-registered detector-output expansion, but it must not alter normal tracking
continuation or silently change the 14 um action contract.

## Boundaries

This is development-only feature research. It does not authorize a new threshold,
production graph mutation, assignment solving, locked validation, or a full-199
run.
