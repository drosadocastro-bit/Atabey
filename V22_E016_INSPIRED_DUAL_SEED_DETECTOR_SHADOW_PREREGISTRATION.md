# V22 E016-Inspired Dual-Seed Detector Shadow Preregistration

Status: **PREREGISTERED; EXTERNAL MODEL ARTIFACT NOT ACCEPTED YET**

## Objective

Test whether an independently trained temporal U-Net seed improves upstream
division-candidate availability and correct daughter-pair formation while the
current Atabey graph, scorer, and postprocessor remain untouched.

This design is inspired by the public E016 notebook, which keeps the primary
route for `44b6_` samples and adds a second temporal model plus low-margin link
consensus only for `6bba_` samples. The transferable hypothesis is independent
detector evidence at the candidate-formation stage, not the notebook's exact
thresholds, gap repair, ILP settings, or division filters.

## Why This Is the Next Gate

The current V22 primary U-Net shadow raised patched-official action availability
from 13/46 to 39/46 with zero graph mutation. The later semantic and temporal
appearance audits found no route-robust incremental scorer. The remaining
uncertainty is therefore upstream: whether a second detector can expose the
correct daughter pair before the linker chooses ownership.

This shadow measures candidate availability and pairing opportunity. A complete
triplet is not an official division TP, and improved availability is not a
leaderboard claim.

## Frozen Population

The decision population is the already-open V22 development split:

- 46 registered GT divisions across 27 samples;
- both `44b6` and `6bba` families;
- the existing 13 V19 official-positive controls;
- the existing primary-U-Net outputs and event-frame reference counts.

The prior 12-event U-Net screen is retained as an integration smoke battery
only. It cannot be used as independent evidence for the 46-event decision.

Machine-readable sources:

- `v22_unet_official_action_development_46.csv`;
- `tests/fixtures/v22_unet_official_action_development_46.json`;
- `v22_unet_detection_development_46_peaks.csv`;
- `v22_v19_event_frame_reference.csv`.

## Artifact Provenance Gate

The external second seed is not accepted from a notebook cell alone. Before
inference, the artifact must provide:

- a checkpoint SHA-256 and manifest SHA-256;
- architecture and input preprocessing description;
- training seed and training-data provenance;
- confirmation that hidden-test labels, official GT division labels, or Atabey
  development labels were not used to fit or select the checkpoint;
- a reproducible offline load test.

If these fields cannot be verified, the experiment stops at `HOLD_ARTIFACT_NOT
PROVENANCE_COMPLETE`.

## Route Design

For `44b6_` samples, the primary detector and current inference path are copied
unchanged. The second seed has no effect.

For `6bba_` samples, record four detector views without graph mutation:

1. primary-only detections;
2. secondary-only detections;
3. union detections after confidence blending;
4. consensus-qualified detections for low-margin links.

The union may increase candidate availability, but it may not delete a primary
detection. Consensus is an annotation and pairing-opportunity signal in this
phase, not a committed edge.

The primary Atabey postprocessor is not changed. No gap closing, safe-division
filter, ILP, local assignment, semantic score, or production graph projection
is enabled.

## Measurements

For every registered division, report before/after and source provenance for:

- parent candidate within the official 7 um radius;
- each daughter candidate within 7 um;
- two-distinct-daughter availability;
- complete-triplet availability;
- whether the existing correct parent/daughter action remains present;
- whether the correct pair becomes available only in the union or consensus view;
- competing and added candidate counts per event and frame;
- primary/secondary/union peak-count ratios;
- family, route, fold, sample, and event breakdowns.

For every recovered event, record whether recovery is due to parent detection,
daughter detection, pair uniqueness, or candidate ownership opportunity. Do not
call any recovered event a true division without the patched official scorer.

## Decision Contract

`GO_TO_DUAL_SEED_PAIRING_SHADOW` requires all of:

- 13/13 existing official-positive controls retain complete availability;
- at least 3 of the 7 currently unavailable development divisions gain a
  complete triplet;
- recovered divisions include both families;
- no `44b6_` division loses primary availability;
- median union/primary frame peak-count ratio <= 1.50;
- p90 union/primary frame peak-count ratio <= 2.50;
- zero graph mutations and zero inferred edges;
- artifact provenance gate passes.

The candidate-load ratios are engineering guardrails, not biological thresholds.
Any division Jaccard or EdgeRecall change requires a separate, later shadow with
the official scorer.

Decision states:

- `GO_TO_DUAL_SEED_PAIRING_SHADOW`;
- `HOLD_ARTIFACT_NOT_PROVENANCE_COMPLETE`;
- `HOLD_CANDIDATE_LOAD_OR_ROUTE_UNSTABLE`;
- `NO_GO_DUAL_SEED_AVAILABILITY`.

No threshold tuning is authorized from this audit. No full-199 run is authorized
by a GO; only a separately preregistered local pairing shadow may follow.

## Explicit Non-Transfers From E016

The notebook's exact detector weights, confidence blend, low-margin cutoff,
motion relink limits, gap repair, safe-division caps, and ILP weights remain
external hypotheses. They must not be copied into Atabey without local
provenance, route-stratified evidence, and official-metric validation.

Machine contract:
`tests/fixtures/v22_e016_dual_seed_detector_shadow.json`
