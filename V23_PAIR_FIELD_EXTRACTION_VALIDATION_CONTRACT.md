# V23 Pair-Field Extraction And Validation Contract

Status: **preregistered design only**. No tensor extraction or model fitting is authorized by this document.

## Purpose

The CFAR-native census found 29 patched-official positive division events across 22 samples, with adequate support in both families and all three deterministic sample-blocked folds. This contract freezes how those events may become pair-conditioned 3D fields and how any later model must be judged.

It keeps three questions separate:

1. Can the fields be extracted deterministically without leakage or hidden boundary artifacts?
2. Does image evidence add signal beyond daughter geometry and candidate masks?
3. Does any gain generalize across samples, folds, and both biological families?

A pass on one question must never be reported as a pass on the next.

## Candidate Population And Labels

The population remains CFAR-only. For each available registered event:

- anchors are CFAR parent detections within the official 7 um radius of the GT parent;
- candidate daughters are every distinct unordered pair at `t+1` whose members lie within 14 um of that candidate parent;
- the 14 um division-formation radius remains distinct from the frozen 9 um ordinary continuation gate;
- every isolated fork is labeled by the directly integrated patched official scorer;
- patched-official TP actions are positive;
- patched-official FP actions are the only supervised negatives;
- unsupported or unevaluated actions remain unknown.

Unknown actions stay in full candidate ranking so they can bury a TP, but they never become false positives or supervised negatives merely because sparse GT does not support them.

All 90 official-TP action variants remain valid. They represent 29 biological events, so metrics and loss weights must collapse multiplicity through sample -> event -> label side -> action weighting. The canonical action receives no privilege.

## Field Definition

The assembled tensor is `float32`, axes `CZYX`, shape `5 x 33 x 33 x 33`, sampled on an isotropic 1 um grid from -16 um through +16 um around the candidate parent.

Channels are frozen:

1. robust-normalized image at `t`;
2. robust-normalized image at `t+1`;
3. parent trilinear-splat mask;
4. symmetric daughter-pair trilinear-splat mask;
5. explicit crop-coverage mask.

Images are independently normalized per full frame using percentiles 1 and 99.9, clipped to [0,1], then sampled trilinearly with constant-zero padding. No training-fold statistic enters normalization. Parent-mask mass must equal 1 and daughter-mask mass 2. Swapping daughter IDs must produce a byte-identical assembled tensor.

Coordinates, family, route, sample ID, node ID, and frame number are metadata only and cannot enter the model.

## Storage

Dense image fields are cached once per candidate parent. Daughter-pair actions store only a reference to that parent field plus a sparse symmetric mask description. Repeating the four shared dense channels for every pair is forbidden.

Before writing tensors, a metadata-only preflight must report action counts and estimated size. Extraction enters HOLD if it would exceed 20 GiB uncompressed, 20,000 actions in any event, or 5,000 parent fields. Outputs live under `outputs/v23_cfar_pair_field_v1` and stay out of git; only compact manifests, contracts, and reports belong in the repository.

## Extraction Gates

A GO to model preregistration requires:

- exactly 29 positive events and 90 official-TP variants reproduce;
- all three folds and both families reproduce;
- no sample crosses folds;
- every value is finite and image values remain in [0,1];
- coverage is binary and agrees with physical crop bounds;
- parent and daughter mask masses pass at 1e-5 tolerance;
- daughter swapping is exactly invariant;
- repeated extraction produces identical parent-tensor hashes;
- official label parity is exact;
- no source graph is mutated;
- all resource limits pass.

This stage has three outcomes: `GO_TO_BOUNDED_PAIR_FIELD_MODEL_PREREGISTRATION`, `HOLD_EXTRACTION_RESOURCE_OR_STRATUM_CONCERN`, or `NO_GO_EXTRACTION`.

## Weighting And Evaluation

Outer validation uses the frozen three sample-blocked folds. Held-out samples cannot guide architecture, thresholds, normalization, early stopping, or calibration. Inner selection uses only the two outer-training folds.

The primary future metric is equal-event-weighted recall@10 over the full candidate ranking. Unknown candidates participate in rank position but are not counted as false positives. Secondary metrics are recall@1, recall@5, MRR, and TP-versus-official-FP pairwise accuracy. Every result must be reported by fold, family, sample, and event.

Raw action weighting is forbidden. Samples are equal within fold, events equal within sample, positive and FP sides equal within event, and actions equal within each side. Official FP sampling is capped at 64 per event by the frozen hash seed `v23-pair-field-fp-v1`.

## Mandatory Controls

The main field model must be compared with all five controls:

- nearest-distance ranking;
- a low-capacity geometry-only ranker;
- the same model with both image channels zeroed;
- image fields deterministically shuffled within held-out fold, family, and crop-coverage quartile;
- a static-image control replacing `t+1` with `t`.

A pooled score alone cannot carry a GO. The future model must reach recall@10 of 0.80 pooled, 0.625 in every fold, and 0.65 in each family; fold spread must not exceed 0.25. It must also reach MRR 0.40 and TP-versus-official-FP pairwise accuracy 0.75.

Independent image evidence requires recall@10 margins of at least 0.10 over the best non-image control, 0.10 over shuffled images, and 0.05 over the static-image control, with no fold regressing by more than one event versus the best non-image control.

## Guardrails

This contract does not select a model architecture and does not authorize tensor writes yet. It authorizes implementation of a metadata-only preflight and extractor validation harness. Model fitting requires a separate bounded model preregistration after extraction integrity passes.

CFAR remains frozen. Assignment remains disabled. Production graphs remain untouched. Full-199 evaluation remains locked.
