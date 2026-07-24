# V22 Temporal U-Net Detection-Availability Shadow

Date: 2026-07-24
Status: pre-registered; GPU inference not yet run

## Question

Can the public temporal 3D U-Net recover parent/daughter detections that are absent
from Atabey's frozen V19 formation path, without importing the notebook's transformer,
ILP, relinking, pruning, or division decisions?

This is a detector-availability experiment. It is not a tracking comparison and
cannot authorize production graph changes.

## Public Source

The implementation is taken from the public Kaggle notebook
`praxel/biohub-0-902-motion-division-calibration` and its attached CC0 support pack
`pilkwang/biohub-tracking-support-pack-50ep-v1`.

The detector contract inspected on 2026-07-24 is:

- temporal 3D U-Net with a two-frame input window;
- manifest artifact `biohub-tracking-support-pack-400ep-snapshot-v1`;
- checkpoint `weights/unet_transformer/split_0/edge_predictor_best.pth`, SHA-256
  `12f6881ee3620a831697ca098ff8f48e687a24225f4e048b538deec3562fe771`;
- 0.1%-99.9% image-quantile normalization;
- spatial downsample `(1, 4, 4)`;
- 3.0 um physical max-pool suppression;
- eight-view XY D4 test-time augmentation from the selected public notebook;
- fixed detection threshold `0.970`.

The source notebook also contains transformer edge prediction, ILP, motion relinking,
gap repair, short-track filtering, safe-division insertion, and smoothing. None of
those stages are called by this shadow.

## Frozen Battery

Machine-readable source:

`tests/fixtures/v22_unet_detection_shadow.json`

The 12 events are drawn only from the already-open V21 development split:

- all six `44b6` GT divisions;
- three `6bba` target failures, selected as the lexicographically first case from
  each of `no_parent_detection_within_7um`,
  `fewer_than_two_daughter_lineages_within_7um`, and
  `no_pair_inside_14um_formation_radius`;
- three `6bba` official-positive controls, selected lexicographically.

No calibration or locked validation sample is opened.

## Measurements

For every event, the runner exports:

- number of U-Net peaks within the official 7 um radius of the GT parent;
- number within 7 um of each GT daughter;
- whether two distinct daughter peaks exist;
- whether the complete parent plus two-daughter detection triplet exists;
- nearest role distances;
- total U-Net peak count in each evaluated frame;
- the frozen threshold, suppression radius, and TTA mode;
- explicit `graph_mutated=False` and `edges_inferred=False` fields.

The result measures detection availability only. It does not claim that an available
triplet can be linked correctly or recognized as an official division.

## Bounded Decision Rule

Proceed to a larger learned-detector shadow only if all hold:

1. at least 3/9 target events gain a complete triplet;
2. at least one recovered target is from each of `44b6` and `6bba`;
3. all 3/3 positive controls retain complete triplets;
4. no threshold, TTA, normalization, or peak-suppression parameter is changed after
   outcome inspection;
5. the output confirms zero graph mutation and no edge inference.

Peak-count inflation is reported descriptively in this first run. Even a GO does not
authorize integration; it only justifies a larger sample-blocked detector study where
candidate inflation can be compared against frozen frame-level baseline counts.

## GPU Execution

The preferred first runtime is a Kaggle GPU notebook because the competition data and
public support pack can be mounted without copying roughly 100 GB through a temporary
Colab runtime. Colab remains supported when equivalent local paths are supplied.

The runner is:

`scripts/run_v22_unet_detection_shadow.py`

Expected outputs:

- `v22_unet_detection_shadow.csv`
- `v22_unet_detection_shadow_summary.json`

## Guardrails

- Track A/V20 and the production submission path remain untouched.
- No Atabey edge, division, or candidate-formation rule is invoked.
- No threshold sweep is allowed.
- FluoResFM restoration is not part of this run.
- Segmentation-free density/keypoint QC is not part of this run.
- Raw microscopy and official GEFF labels remain authoritative.
