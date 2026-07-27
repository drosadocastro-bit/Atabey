# V22 E016 Clean Secondary Checkpoint Preregistration

Date: 2026-07-25\r\nStatus: **training manifest locked; checkpoint not yet trained**

## Purpose

Produce a secondary U-Net checkpoint that can be evaluated fairly on the frozen
E016 development audit. The public seed-314159 artifact is authentic but was
trained on all 199 competition samples, so it is held out from local claims.

## Locked population

- Total competition samples: `199`.
- Clean training pool: `172` samples.
- Untouched development population: `27` samples.
- Development events reserved for evaluation: `46`.
- Development families: `44b6` and `6bba`.
- Official division radius: `7.0` micrometers.

The exact exclusion list, clean pool, and internal holdout are recorded in
`v22_e016_clean_checkpoint_manifest.json` and `v22_e016_clean_internal_split.json`. The 27 excluded samples are not
allowed in fitting, checkpoint selection, early stopping, threshold selection,
or feature normalization statistics.

## Training lock

- Method: `unet_transformer_clean172_seed314159_v1`.
- Base/effective seed: `314159`.
- Deterministic execution: required where supported by the runtime.
- Architecture: the E016 TemporalUNet3D + node-transformer configuration.
- Fit population: `138` samples from the clean pool.\n- Internal validation population: `34` samples from the clean pool.\n- Checkpoint selection: internal-validation evidence from the clean pool only.
- No development or hidden-test labels may influence training or selection.

## Evaluation lock

Evaluation is detector-only and read-only. It may record primary, secondary,
union, and low-margin consensus detections, but it must not alter lineage edges,
run assignment, or create inferred graph edges. The existing E016 gates remain:

- preserve all `13/13` existing official-positive controls;
- recover at least `3` of the `7` currently unavailable events;
- recover signal in both families;
- no loss of 44b6 primary availability;
- median union/primary peak ratio at most `1.5` and p90 at most `2.5`;
- graph mutation and inferred edges remain zero.

Any result from a checkpoint that cannot prove this population separation is
reported as provenance-ineligible, regardless of apparent score.
