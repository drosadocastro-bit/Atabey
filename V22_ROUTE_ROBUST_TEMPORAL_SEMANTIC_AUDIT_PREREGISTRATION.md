# V22 Route-Robust Temporal Semantic Evidence Audit Preregistration

Status: **PREREGISTERED; FEATURES NOT EXTRACTED**

## Objective

Test whether direct temporal image evidence distinguishes patched-official
division actions across both supported detector routes and both sample families.
This is an evidence audit only. It does not fit an action ranker, perform local
assignment, or mutate a lineage graph.

The preceding positive-unlabeled ranker was a clear NO-GO: supported-route
action/event recall@50 was 0.367/0.526, it did not improve over the
`mean_daughter_contrast` baseline, CFAR recall@50 was zero, and 44b6 recall@50
was zero. Static single-frame contrast is therefore a real but insufficient
signal.

## Availability Census

The frozen development split contains 39 official-positive events across 27
sample-blocked samples. Every positive event has the full `t-1` through `t+2`
image window:

| Family | Route | Positive events | Complete windows |
| --- | --- | ---: | ---: |
| 44b6 | CFAR/bipartite | 2 | 2 |
| 44b6 | local-maxima/motion-mutual | 1 | 1 |
| 6bba | CFAR/bipartite | 5 | 5 |
| 6bba | components/greedy | 31 | 31 |

No event is excluded because of temporal boundary position. Local-maxima remains
zero-shot and decision-ineligible.

## Hypothesis

A real division should contain a coordinated temporal appearance transition:

- parent-centered signal is present before the proposed split;
- two daughter-centered signals emerge or strengthen after the split;
- the two daughter signals remain independently visible one frame later;
- parent-to-daughter signal and shape changes are balanced enough to be
  biologically plausible.

These are image observations, not motion or ownership evidence. They must never
be described as proof of biological division.

## Frozen Temporal Measurements

All measurements use the original image volumes and physical coordinates already
present in the frozen U-Net action table. Patch geometry remains fixed in
micrometers.

Per location, compute robust shell-normalized descriptors at the relevant
frames:

- contrast;
- positive signal mass;
- effective volume;
- intensity-weighted anisotropy;
- patch coverage.

The audit derives only these temporal action features:

- parent contrast and mass retention from `t-1` to `t`;
- daughter contrast and mass emergence from `t` to `t+1`;
- minimum daughter persistence from `t+1` to `t+2`;
- daughter emergence balance;
- daughter persistence balance;
- temporal parent-to-daughters mass conservation error;
- temporal parent-to-daughters effective-volume conservation error;
- temporal daughter anisotropy agreement;
- fraction of the required temporal patches with full coverage.

Fixed-coordinate temporal sampling is used. No nearest-neighbor search, future
peak reassociation, spatial optimization, interpolation toward ground truth, or
teacher continuation is permitted.

## Prohibited Inputs

The audit may not use:

- V19 or V20 teacher scores;
- parent-child distance, daughter separation, angle, velocity, prediction error,
  turn, step ratio, or any mathematically reconstructed motion feature;
- density, ownership margin, candidate rank, assignment state, route, family,
  sample identifier, or fold as a predictive feature;
- ground-truth distance or sparse absence as a negative label.

Route, family, fold, sample, and event are reporting strata only.

## Labels And Evaluation

`official_tp` is the positive class and directly scored `official_fp` is the
reliable negative class. Unsupported and not-evaluated actions remain unknown
and are excluded from discrimination calculations.

Feature direction is selected using training folds only. Each feature is
evaluated with sample-blocked out-of-fold, equal-event-weighted AUC. Results must
be reported by fold, family, and route. No multivariate model is decision
eligible in this phase.

The existing static `mean_daughter_contrast` feature is the mandatory baseline.
The audit must report incremental AUC for each temporal feature over that
baseline, not merely pooled discrimination.

## GO Contract

A GO to preregister a temporal positive-unlabeled ranker requires all of:

- temporal descriptor completeness >= 0.99 for official TP and official FP;
- at least two temporal feature families achieve pooled AUC >= 0.70;
- at least one temporal feature achieves each-fold AUC >= 0.60;
- at least one temporal feature achieves each-family AUC >= 0.62;
- at least one temporal feature achieves CFAR AUC >= 0.62;
- at least one temporal feature achieves components AUC >= 0.70;
- the same feature, or a preregistered feature family aggregate, satisfies the
  fold, family, and supported-route floors;
- best temporal AUC exceeds static `mean_daughter_contrast` AUC by >= 0.03;
- zero graph mutations and zero assignment decisions.

Local-maxima is reported separately as unproven zero-shot evidence and cannot
carry a GO.

Decision states:

- `GO_TO_TEMPORAL_PU_RANKER_PREREGISTRATION`;
- `HOLD_TEMPORAL_SIGNAL_ROUTE_OR_FAMILY_UNSTABLE`;
- `NO_GO_TEMPORAL_SEMANTIC_EVIDENCE`.

No value is rounded into passing.

## Boundaries

This preregistration authorizes only extraction and read-only discrimination on
the frozen 27-sample development split. It does not authorize model fitting
beyond univariate direction selection, assignment, graph projection, locked
validation, or a full-199 run.

Machine contract:
`tests/fixtures/v22_route_robust_temporal_semantic_audit.json`
