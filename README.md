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
routing, then tested ideas like Overall System Sensitvity, Target Reinforce, Target Correlation, CFAR, side-lobe suppression, and latent recovery without losing
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
