# Project Atabey

Project Atabey is an experimental, stateful lineage-tracking scaffold for the Kaggle competition
[Biohub - Cell Tracking During Development](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development).

Disclaimer: this repository is experimental research code for a Kaggle competition. It is not a
production system, it is not a validated biological model, and its outputs should be treated as
bounded tracking experiments rather than authoritative conclusions.

## Repo Intro

Atabey is a record of an evidence-driven tracking workflow: start with a streaming baseline,
diagnose where it fails, test bounded fixes, measure the runtime and quality tradeoffs, and keep
only the branches that improve the calibration story.

In practice, this means the repo shows how we moved from simple component centroids to adaptive
routing, then tested ideas like Overall System Sensitivity, Target Reinforce, Target Correlation, CFAR, side-lobe suppression, latent recovery, and marker-based watershed refinement without losing
auditability or pretending the tracker knows more than the data supports.

If you want the short version: this repo is about disciplined experimentation, explicit
uncertainty, and the decisions we made after the measurements came back.

Atabey is inspired by Project Lumina's attention to memory traces, phase transitions, local pressure,
and dormant potential, but it applies those ideas conservatively to 3D+time embryonic cell tracking.
The goal is not to infer biological meaning beyond the observable data. The goal is to preserve
observable lineage state while producing a valid, reproducible Kaggle submission.

## Main Path

```text
Zarr sample
-> streamed timepoint IO
-> candidate detection
-> physical-coordinate normalization
-> temporal linking
-> lineage graph
-> optional state and latent-candidate layer
-> submission writer
-> sparse ground-truth evaluation
```

V19: Watershed Centroid Refinement — Validated GO
After four consecutive NO-GOs on the linking layer (V14 pfa-mode CFAR reformulation, V15 track-continuity recovery, V16/V17 kinematic soft-linking, V18 bounded global optimization — each documented with its own diagnostic and root-cause analysis), V19 targeted a different layer entirely: detection-stage localization precision.
The problem: CFAR's core detection selects the single brightest voxel as a cell's coordinate. The adaptive baseline instead computes an unweighted geometric centroid over a segmented blob. This difference introduces localization noise in CFAR's output relative to the true cell centroid — enough, in dense/high-background samples, to push otherwise-correctly-tracked cells outside Kaggle's official 7.0µm ground-truth matching radius.
Two intermediate fixes were tried and failed before the working approach was found:

Local bounding-box refinement — failed; a fixed window structurally truncates cell bodies depending on where the peak sits.
Global blob centroid — failed catastrophically in dense regions; a single connected component was found to merge up to 284 distinct cells into one averaged coordinate.

What worked: marker-based watershed segmentation — CFAR's peaks as markers, a global intensity mask as the segmentation boundary, each resulting region reduced to its own unweighted centroid. This keeps CFAR's sensitivity to dim/crowded cells while correcting the reported coordinate, without merging neighboring cells.
Validated result (66-sample CFAR-routed cohort, strict A/B against frozen V13, identical evaluator):
MetricV13V19 WatershedDeltaQuality score0.73030.7558+0.0255Node recall76.96%79.74%+2.78%Edge recall69.10%71.42%+2.32%Runtime overhead—~25s/samplewithin budget

57 of 66 samples improved; 2 flat; 7 regressed (shallow, concentrated in the densest 44b6_ samples where a single connected component exceeds 350,000 voxels — a known, characterized limitation).
44b6_0c582fdc — the sample that originally motivated the V14 pfa-collapse investigation — improved by +0.1038, the largest single-sample gain in the cohort.
Isolated behind --enable-watershed-refinement (default off); V13's production path is byte-identical with the flag unset.

Full methodology — including the failed intermediate approaches, the disproven "-4.36µm uniform bias" hypothesis (later shown to be a sample-selection artifact from a 5-sample preview), and a runtime explanation that was proposed, profiled, found incorrect, and retracted — is documented in docs/V19_CFAR_Z_BIAS_ROOT_CAUSE.md.

## Current Scope

This repository starts with a minimal research scaffold:

- streaming-first Zarr and GEFF adapter boundaries
- CPU-friendly baseline detection utilities
- nearest-neighbor tracking over physical coordinates
- internal lineage graph types
- a submission writer placeholder that must be reconciled with the real `sample_submission.csv`
- synthetic tests for core deterministic behavior
- architecture notes and ADRs

## Competition Facts Captured So Far

Live Kaggle metadata was checked on 2026-06-30:

- competition: `biohub-cell-tracking-during-development`
- task: detect and track zebrafish cells through 3D space and time
- required output filename: `submission.csv`
- row id column: `id`
- notebook submissions only
- CPU/GPU runtime limit: 720 minutes
- daily submissions: 5
- deadline: 2026-09-29 23:59 UTC

The file listing exposes `sample_submission.csv` and sharded `.zarr` test data, but direct download of
`sample_submission.csv` returned `403 Forbidden` from the local CLI. See
[docs/DATASET_NOTES.md](docs/DATASET_NOTES.md) before hardening the writer.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Run Tests

```powershell
python -m pytest
```

## Minimum Viable Atabey

1. Read one Zarr timepoint without loading the full video.
2. Detect candidate centroids.
3. Link detections across adjacent timepoints.
4. Generate an internal node and edge graph.
5. Reconcile the writer with the official `sample_submission.csv`.
6. Produce `submission.csv` from a Kaggle notebook.

Atabey's state layer comes after the baseline submission path is valid.
