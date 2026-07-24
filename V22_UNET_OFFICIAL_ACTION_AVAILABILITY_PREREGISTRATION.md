# V22 U-Net Official-Action Availability Shadow

Date: 2026-07-24
Status: pre-registered; peak coordinates and official-action outcomes unopened

## Purpose

The frozen V22 detector recovered complete parent-plus-two-daughter triplets for
23/25 previously unavailable development divisions while preserving 13/13
positive controls. That result establishes detector availability only.

V21 semantic scoring stopped because only 13/46 development divisions had an
action recognized as a true division by the patched official metric. This
Phase 1A asks whether the unchanged U-Net detections raise that official-action
availability enough to authorize semantic-score development.

No semantic score, confidence fit, assignment solve, graph mutation, or locked
validation access is authorized here.

## Frozen Population And Detector

The population remains all 46 divisions in the existing development fixture:

`tests/fixtures/v22_unet_detection_development_46.json`

Its SHA-256 is:

`14d77a14c17224d84b5653b76efa39b962f5172628f155eb7e1a91de9ddc3fb8`

The detector checkpoint, threshold `0.970`, 3.0 um peak suppression, temporal
window, normalization, downsampling, and eight-view XY D4 TTA remain unchanged.
Calibration and locked validation samples remain unopened.

## Candidate Formation

The GPU pass exports every U-Net peak from each evaluated parent and daughter
frame with a deterministic ID, physical coordinates, and confidence.

For each event frame `t`, candidate formation is independent of GT identity:

1. take every V19 detection at `t-1` as a track anchor;
2. predict its `t` position with one-step constant velocity when history at
   `t-2` exists, otherwise use the anchor position;
3. admit every U-Net parent peak within 14.0 um of at least one prediction;
4. observe every U-Net daughter peak at `t+1` within 14.0 um of that parent;
5. enumerate every distinct two-daughter pair.

When several anchors claim one parent peak, the nearest predicted anchor is
recorded deterministically. This tie handling is provenance, not a semantic
score or ownership decision.

GT coordinates are used only after the full action set exists, to identify
registered candidate forks within the official 7.0 um role radius. Those
geometrically matched forks are projected one at a time through the pinned,
patched official division scorer.

## Measurements

For every registered division, report:

- V19 route and link strategy;
- prior-frame anchor count;
- U-Net parent peaks and anchored parent peaks;
- total formed division actions;
- registered geometric-match action count;
- patched-official TP action count;
- official-positive availability;
- source-graph zero perturbation.

Raw action volume is a computational diagnostic, not an FP count. Sparse
unsupported actions are not labeled negative.

## Decision Contract

Phase 1A is a **GO for semantic-score development only** if:

1. at least 20/46 registered divisions have an official-positive action;
2. at least 12/13 prior official-positive controls remain available;
3. official-positive actions occur in both `44b6` and `6bba`;
4. every source graph passes zero perturbation;
5. no graph mutation, semantic scoring, or assignment occurs.

The minimum of 20 preserves the positive-count requirement already frozen in
the V21 semantic design. It is not a borrowed confidence threshold.

Failure does not authorize detector-threshold tuning on these 46 cases.
Passing does not authorize graph integration or opening locked validation. It
only permits a separately pre-registered semantic ranking experiment on the
development action table.

## Execution Sequence

Run the updated development notebook on Kaggle and retain:

- `v22_unet_detection_development_46.csv`;
- `v22_unet_detection_development_46_summary.json`;
- `v22_unet_detection_development_46_peaks.csv`.

After placing the peak CSV in the local repository, run:

```powershell
python -u scripts/run_v22_unet_official_action_availability.py `
  --peaks v22_unet_detection_development_46_peaks.csv `
  --train-dir train `
  | Tee-Object v22_unet_official_action_development_46.log
```

This local pass rebuilds V19 only through the registered event frames and writes
the case table, JSON decision summary, and Markdown report. It does not require a
GPU.

## Guardrails

- The 46 detector outcomes may not change candidate-formation radii.
- No candidate may be removed using GT identity or sparse absence.
- The patched official scorer is the only source of official TP status.
- Candidate counts must never be described as official FP.
- The V19 source graph must remain byte-for-byte unchanged.
- Track A, Track B, calibration, and locked validation remain frozen.
