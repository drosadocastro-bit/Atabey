# V22 Temporal U-Net Full Development Shadow

Date: 2026-07-24
Status: pre-registered; GPU outcomes unopened

## Purpose

The frozen 12-event temporal U-Net screen passed its pre-registered gate:

- 6/9 target events gained a complete parent plus two-distinct-daughter triplet;
- both `44b6` and `6bba` recovered;
- 3/3 independent positive controls were preserved;
- no edge inference or graph mutation occurred.

This larger shadow asks whether that availability gain generalizes across every GT
division in the already-open V21 development split. It does not test tracking,
official division recognition, or production integration.

## Frozen Population

Machine-readable source:

`tests/fixtures/v22_unet_detection_development_46.json`

Population:

- 46 GT divisions from 27 development samples;
- 6 `44b6` divisions and 40 `6bba` divisions;
- 25 divisions with no V19 candidate action;
- 8 divisions with a V19 action that was not an official TP;
- 13 V19 official-positive controls.

Calibration and locked validation samples are excluded.

## Frozen Detector

The detector is unchanged from the 12-event screen:

- artifact `biohub-tracking-support-pack-400ep-snapshot-v1`;
- checkpoint SHA-256
  `12f6881ee3620a831697ca098ff8f48e687a24225f4e048b538deec3562fe771`;
- temporal window size 2 with public sliding-window context;
- 0.1%-99.9% quantile normalization;
- spatial downsample `(1, 4, 4)`;
- threshold `0.970`;
- 3.0 um physical peak suppression;
- eight-view XY D4 TTA;
- inference mode with sequential parent/daughter window release.

No threshold sweep, restoration, edge prediction, ILP, division rule, or graph
mutation is authorized.

## Measurements

For all 46 divisions:

- parent candidates within the official 7 um radius;
- candidates for each daughter within 7 um;
- availability of two distinct daughter peaks;
- complete-triplet availability;
- nearest role distances;
- U-Net peak count in the parent and daughter frames;
- result by family and V19 baseline-status class.

A separate frozen local audit records V19 detection counts in the same event frames:

`scripts/build_v22_v19_event_frame_reference.py`

Those counts are joined after GPU inference to measure U-Net/V19 peak-count ratios.

## Decision Contract

The learned detector may proceed to a downstream semantic/linking shadow only if:

1. at least 13/25 previously unavailable divisions gain complete triplets;
2. at least 12/13 official-positive controls retain complete triplets;
3. recovered previously unavailable cases include both sample families;
4. median U-Net/V19 frame peak-count ratio is at most 2.0;
5. p90 U-Net/V19 frame peak-count ratio is at most 3.0;
6. all outputs retain `graph_mutated=False` and `edges_inferred=False`.

Passing items 1-3 produces only `GO_PENDING_FRAME_INFLATION_AUDIT`. A final GO
requires the frozen frame-count comparison. Failure does not authorize threshold
tuning on these 46 outcomes.

## Outputs

- `v22_unet_detection_development_46.csv`
- `v22_unet_detection_development_46_summary.json`
- `v22_v19_event_frame_reference.csv`

## Guardrails

- Development membership is fixed and complete; no samples may be removed.
- Calibration and locked validation remain unopened.
- The 12-event screen is retained as historical evidence, not reused as an
  independent validation set.
- Complete detection availability is not an official division TP.
- Peak-count ratios are candidate-load diagnostics, not biological cell counts.
- FluoResFM and segmentation-free QC remain separate future experiments.
