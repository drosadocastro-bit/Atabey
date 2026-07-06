# CNN Advisor Evaluation (Standalone Branch): Cellpose + StarDist vs CFAR

Date: 2026-07-05
Status: Bounded smoke completed (standalone, no production wiring). Metric-audit instrumentation added and Colab GPU runbook prepared. Current recommendation remains NO-GO for integration design at this stage.

This document tracks a standalone CNN-advisor exploration branch.

Guardrails:
- No wiring into `run_hybrid_submission.py` or `run.py` in this phase.
- No production-default changes.
- Correlation-layer branch remains closed; this is a separate initiative.

## Scope and Objective

Evaluate whether CNN-based detectors (Cellpose and StarDist), used as standalone advisors,
can improve detection quality on the CFAR at-risk cohort over current CFAR detection,
with bounded runtime.

Primary target cohort: at-risk samples from
`submissions/cfar_bounded_scan_fulltrain.json` under `real_failures_routed_and_at_risk["1e-03"]`.

## Environment and Runtime Notes

Environment checks (this machine):
- Python: 3.13.x (`.venv` configured)
- Cellpose: installed and importable
- StarDist + csbdeep + TensorFlow: installed and importable
- PyTorch CUDA available: false
- TensorFlow GPU devices: 0 (native Windows TensorFlow GPU limitation)

Implication: this branch currently executes CPU-only unless moved to a different runtime (WSL2/GPU).

## Data and Label Preparation Strategy

Data source:
- Volumes: `train/*.zarr` (shape per sample frame: ZYX = 64x256x256)
- Labels: `train/*.geff` sparse centroids

Important caveat:
- GEFF labels are sparse centroids, not dense instance masks.
- For this bounded advisor evaluation, pseudo-instance masks are created by rasterizing
a small disk around sparse GT centroids on 2D max-intensity projections (MIP).
- Therefore metrics here are bounded screening signals, not official competition metrics.

## Standalone Experimental Artifacts Added

Utilities:
- `src/atabey/experiments/cnn_advisor.py`
  - at-risk sample loading
  - bounded timepoint selection
  - pseudo-mask generation from centroids
  - instance IoU precision/recall/F1 aggregation
  - per-object IoU diagnostics (`matched_iou_values`, `best_iou_per_gt`)
  - physical-distance matching diagnostics in microns (`distance_match_metrics`)

Runner:
- `scripts/run_cnn_advisor_evaluation.py`
  - loads at-risk samples
  - builds train/val/test split
  - runs CFAR baseline on same frames
  - runs Cellpose zero-shot
  - runs StarDist zero-shot
  - optionally runs bounded smoke fine-tuning for both
  - emits per-method per-frame match diagnostics for auditability
  - reports explicit unit domain (`2D YX on MIP`) and pixel spacing metadata from Zarr multiscales
  - emits raw denominators and smoke-validity warnings for tiny splits
  - writes detailed and summary JSON outputs

Tests:
- `tests/test_cnn_advisor_utils.py`

Colab notebook:
- `notebooks/03_cnn_advisor_colab_gpu.ipynb`
  - installs dependencies in Linux runtime
  - verifies torch/tensorflow GPU visibility
  - runs corrected smoke audit and larger three-way rerun commands

## Commands

Bounded smoke run:

```powershell
$env:PYTHONPATH='src'; d:/Project-Atabey/.venv/Scripts/python.exe scripts/run_cnn_advisor_evaluation.py \
  --train-dir train \
  --scan-json submissions/cfar_bounded_scan_fulltrain.json \
  --max-samples 6 \
  --max-timepoints 4 \
  --cellpose-epochs 1 \
  --stardist-epochs 1 \
  --output-json submissions/cnn_advisor_eval_smoke.json \
  --output-summary-json submissions/cnn_advisor_eval_smoke_summary.json
```

Cellpose bounded smoke (clean v2 artifact):

```powershell
$env:PYTHONPATH='src'; d:/Project-Atabey/.venv/Scripts/python.exe scripts/run_cnn_advisor_evaluation.py \
  --train-dir train \
  --scan-json submissions/cfar_bounded_scan_fulltrain.json \
  --max-samples 3 \
  --max-timepoints 2 \
  --skip-stardist \
  --cellpose-epochs 1 \
  --output-json submissions/cnn_advisor_eval_cellpose_smoke_v2.json \
  --output-summary-json submissions/cnn_advisor_eval_cellpose_smoke_v2_summary.json
```

StarDist bounded smoke (v3 artifact, with fallback to scratch fine-tune):

```powershell
$env:PYTHONPATH='src'; d:/Project-Atabey/.venv/Scripts/python.exe scripts/run_cnn_advisor_evaluation.py \
  --train-dir train \
  --scan-json submissions/cfar_bounded_scan_fulltrain.json \
  --max-samples 3 \
  --max-timepoints 2 \
  --skip-cellpose \
  --stardist-epochs 1 \
  --output-json submissions/cnn_advisor_eval_stardist_smoke_v3.json \
  --output-summary-json submissions/cnn_advisor_eval_stardist_smoke_v3_summary.json
```

Corrected metric-audit smoke (CFAR-only, fast validity pass):

```powershell
$env:PYTHONPATH='src'; d:/Project-Atabey/.venv/Scripts/python.exe scripts/run_cnn_advisor_evaluation.py \
  --train-dir train \
  --scan-json submissions/cfar_bounded_scan_fulltrain.json \
  --max-samples 3 \
  --max-timepoints 2 \
  --skip-cellpose \
  --skip-stardist \
  --output-json submissions/cnn_advisor_eval_metric_audit_smoke.json \
  --output-summary-json submissions/cnn_advisor_eval_metric_audit_smoke_summary.json
```

Colab GPU execution:
- Open `notebooks/03_cnn_advisor_colab_gpu.ipynb` in Colab and run cells top-to-bottom.
- The notebook includes both a fast smoke-audit run and a larger GPU rerun command.

## Results

### Bounded smoke cohort

- At-risk samples used: 3
- Split: train 1 / val 1 / test 1
- Frames: train 2 / val 2 / test 2

### Cellpose (v2 smoke)

Artifact: `submissions/cnn_advisor_eval_cellpose_smoke_v2_summary.json`

| method | precision | recall | f1 | mean runtime (s/frame) |
|---|---:|---:|---:|---:|
| cfar_current | 0.00063 | 0.50000 | 0.00127 | 2.28233 |
| cellpose_zero_shot | 0.00207 | 0.50000 | 0.00413 | 210.13548 |
| cellpose_finetuned (1 epoch smoke) | 0.00207 | 0.50000 | 0.00413 | 199.11663 |

Observations:
- Cellpose improves precision/F1 vs CFAR on this tiny smoke split.
- Recall is unchanged vs CFAR in this bounded run.
- Runtime is ~87x-92x slower than CFAR per frame on CPU.
- One-epoch fine-tune did not improve quality over zero-shot in this smoke configuration.

### StarDist (v3 smoke)

Artifact: `submissions/cnn_advisor_eval_stardist_smoke_v3_summary.json`

| method | precision | recall | f1 | mean runtime (s/frame) |
|---|---:|---:|---:|---:|
| cfar_current | 0.00063 | 0.50000 | 0.00127 | 1.71889 |
| stardist_finetuned_scratch (1 epoch smoke) | 0.00000 | 0.00000 | 0.00000 | 0.26405 |

Pretrained zero-shot blocker (important):
- `StarDist2D.from_pretrained("2D_versatile_fluo")` fails on this Windows setup with
  `WinError 1314` during model extraction/rename in Keras cache.
- This means the requested StarDist pretrained zero-shot baseline is currently blocked
  by local OS privilege behavior, not by model quality itself.

Fallback behavior implemented:
- Runner now records pretrained-zero-shot failure explicitly and can continue with a
  bounded from-scratch fine-tune so experiments are not blocked end-to-end.

Artifacts generated in this pass:
- `submissions/cnn_advisor_eval_cellpose_smoke_v2.json`
- `submissions/cnn_advisor_eval_cellpose_smoke_v2_summary.json`
- `submissions/cnn_advisor_eval_stardist_smoke_v3.json`
- `submissions/cnn_advisor_eval_stardist_smoke_v3_summary.json`

### Metric Audit Smoke (corrected payload)

Artifact: `submissions/cnn_advisor_eval_metric_audit_smoke_summary.json`

Key audit findings:
- Raw denominator is tiny (`test_frames=2`, `gt_instances_total=2`), so this run is explicitly marked non-evidentiary.
- Unit domain is explicit: IoU on pseudo-instance 2D YX masks over MIP, plus micron-scaled YX centroid distance diagnostics.
- Pixel spacing is now read from sample multiscales metadata (`z=1.625`, `y=x=0.40625` microns).
- Per-frame diagnostics are emitted under `per_method_frame_diagnostics` in the detailed JSON.

Smoke validity warning emitted:
- `TEST_FRAMES_LT_10: smoke is too small for evidentiary model ranking.`

## Interim Recommendation

Go/No-Go for advisor-integration design (current bounded evidence): **NO-GO**.

Reasoning:
- Cellpose shows bounded precision/F1 improvement signal but no recall lift and prohibitive
  CPU runtime inflation.
- StarDist pretrained zero-shot path is blocked by environment privilege constraints; fallback
  scratch fine-tune did not show useful quality in this tiny smoke run.

What must happen before reconsidering advisor integration:
1. Resolve StarDist pretrained loading on this machine (or run in a compatible environment).
2. Run larger held-out at-risk evaluation (not 3-sample smoke) with both zero-shot and
   fine-tuned models.
3. Require meaningful recall/precision gain over CFAR with runtime that is operationally
   acceptable.

Advisor-not-arbiter definition remains deferred until those criteria are met.
If revisited, CNN score should be treated as an additional signal in the quality formula,
never as a direct replacement/override of CFAR detections.
