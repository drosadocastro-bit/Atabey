# Project Atabey Development TODO

This TODO supersedes the pasted seed list by splitting work into gates that protect both Kaggle
practicality and Atabey's stateful lineage identity.

## Gate 0 - Repository Baseline

- [x] Create repository scaffold.
- [x] Add README, requirements, pyproject, `.gitignore`, docs, tests, and `src/atabey`.
- [x] Preserve a small public API.
- [x] Record Kaggle metadata checked on 2026-06-30.
- [ ] Accept Kaggle competition rules in the browser if needed.
- [x] Download or inspect `sample_submission.csv`.
- [x] Confirm the exact submission schema.

## Gate 1 - Dataset Probe

- [x] Read one `.zarr` sample through `zarr.open`.
- [x] Confirm axis order, expected shape, chunking, and dtype.
- [x] Read one timepoint without loading the full video.
- [ ] Visualize central Z slices in `notebooks/00_data_probe.ipynb`.
- [ ] Calculate min, max, and percentile intensity statistics.
- [x] Inspect Zarr metadata files.
- [x] Read one paired `.geff` training graph.
- [x] Extract node IDs, `t, z, y, x` centroids, and graph edges.
- [x] Check any `estimated_number_of_nodes` metadata if present.

Rule: never load a full 3D+time volume unless there is a documented reason.

## Gate 2 - Valid Baseline Submission

- [ ] Normalize each timepoint by robust percentiles.
- [x] Detect candidate cells with simple thresholding and 3D connected components.
- [x] Convert voxel coordinates to physical microns.
- [x] Link adjacent timepoints with nearest-neighbor matching.
- [x] Generate an internal lineage graph.
- [x] Implement the official submission writer after schema confirmation.
- [ ] Run an end-to-end Kaggle notebook from a clean session.

## Gate 3 - Sparse Ground Truth Evaluation

- [x] Match predicted detections to annotated centroids in physical units.
- [x] Estimate approximate recall without treating sparse annotation as exhaustive truth.
- [x] Compare predicted edges against annotated edges.
- [ ] Track identity-switch proxy, lost tracks, and recovered tracks after the basic sparse report is stable.
- [x] Document what each metric can and cannot mean.

## Gate 4 - Lumina-Inspired State Layer

- [ ] Add `CellState` transitions only after the baseline graph is stable.
- [ ] Treat state as an interpretive tracking aid, not as biological truth.
- [ ] Add track memory for velocity, intensity, volume, age, missing frames, and uncertainty.
- [ ] Add local field pressure from crowding and motion conflict.
- [ ] Add latent candidate retention for weak detections.
- [ ] Measure whether state improves tracking or merely adds conceptual weight.

## Gate 5 - Division and Uncertainty

- [ ] Detect plausible parent-to-two-daughter transitions.
- [ ] Score division candidates with proximity, symmetry, morphology, and continuity.
- [ ] Preserve uncertainty when division evidence is weak.
- [ ] Keep prediction error as an attention signal, not proof.
- [ ] Avoid converting repeated lineage into independent confirmation.

## Gate 6 - Runtime Hardening

- [ ] Measure runtime per sample.
- [ ] Measure peak memory use.
- [ ] Avoid fragile dependencies and excessive logging.
- [ ] Confirm Kaggle paths.
- [ ] Confirm hidden-test notebook execution creates `submission.csv`.

## Mantra

```text
Memory tracks the past.
State explains the present.
Lineage preserves the becoming.
```
