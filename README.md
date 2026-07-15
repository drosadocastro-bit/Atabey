# Project Atabey

> *"Signal Processing over Brute Force."*

Project Atabey is an experimental, stateful lineage-tracking research scaffold built for the Kaggle competition [Biohub - Cell Tracking During Development](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development). 

Unlike traditional black-box deep learning approaches, Atabey treats 3D+time cell tracking as a **signal detection and data association problem**. It heavily borrows thinking frameworks from classical radar engineering—like CFAR (Constant False Alarm Rate) thresholding, sidelobe suppression, and kinematic tracking—to build a highly interpretable, evidence-driven tracking pipeline.

*Disclaimer: This repository is experimental research code. It is a testbed for bounded tracking mechanics, not a validated biological model, and its outputs should be treated as rigorous tracking experiments rather than authoritative conclusions.*

---

## Table of Contents
- [Table of Branches (TOB) / Evolution](#table-of-branches-tob--evolution)
- [Pipeline Architecture](#pipeline-architecture)
- [Documentation & Deep Dives](#documentation--deep-dives)
- [Installation & Usage](#installation--usage)
- [Competition Context](#competition-context)

---

## Table of Branches (TOB) / Evolution

Atabey is built on disciplined experimentation and explicit uncertainty. We don't just commit code; we formulate hypotheses, run parallel multi-core audits across our cohort, and document the rigorous lessons learned—especially when we're wrong.

Below is the "Table of Branches", tracking the major evolutionary arcs of the scaffold:

| Branch / Arc | Focus & Hypothesis | Outcome & Lesson |
| :--- | :--- | :--- |
| **V13: The Baseline** | Establish a fast, CPU-friendly streaming scaffold using basic Otsu thresholding and greedy `motion_mutual` linking. | Formed the auditable baseline. Proved that streaming local voxel blocks was strictly necessary for the 720-min Kaggle limit. |
| **V14-V18: CFAR & Sidelobes** | Borrow radar concepts to adaptively threshold dense/noisy tissue regions instead of a brittle global cutoff. | **Success/Pivot**: CFAR architecture worked beautifully, but the literal CA-CFAR math caused bounded-domain collapse. Taught us to borrow the framework, not just the equations. |
| **V19: Watershed & Z-Bias** | Decouple peak detection from sub-voxel bounds localization. Investigated a massive -4.36µm Z-bias anomaly. | **Refutation**: Rigorous testing proved the directional bias was a sample-selection artifact, resolving into symmetric localization variance. |
| **V20: The Division Jaccard & Bipartite Solver** | Attempted to use the Hough Transform for morphological mitosis precursors. Disproved via statistics, leading to a purely topological 1-to-2 Bipartite Solver. | **Success**: A 3-pass kinematic gate allowed true division tracking natively without breaking the 1-to-1 stability of non-dividing cells. |

---

## Pipeline Architecture

Atabey operates on a strictly streaming-first, deterministic execution path. We never load a full 3D+time video into memory without a documented reason.

```text
Zarr sample
 ├─> Streamed timepoint IO (Memory safe)
 ├─> 3D CFAR + Watershed Detection (Signal vs Noise)
 ├─> Physical-coordinate normalization (Microns, not Voxels)
 ├─> Bipartite Topological Linking (Handles 1:1 and 1:2 branches)
 ├─> Lineage Graph Construction
 ├─> Optional state / latent-candidate layer
 ├─> Sparse ground-truth evaluation
 └─> Kaggle submission.csv writer
```

---

## Documentation & Deep Dives

The true value of this repository is in its documented failures, pivots, and evaluations. For anyone digging into the codebase (future collaborators, reviewers, or recruiters), start here:

- **[RADAR_CONCEPTS_AND_ATABEY.md](docs/RADAR_CONCEPTS_AND_ATABEY.md)**: A conceptual explainer of how radar concepts (CFAR, Sidelobe suppression) mapped to biology, and where they failed.
- **[MULTI_AI_COLLABORATION_METHODOLOGY.md](MULTI_AI_COLLABORATION_METHODOLOGY.md)**: How we orchestrated multi-agent execution to build this.
- **[RULE_BASED_CEILING_SUMMARY.md](RULE_BASED_CEILING_SUMMARY.md)**: The ceiling of V14-V18 and the push toward adaptive learning.
- **[V19_CFAR_Z_BIAS_ROOT_CAUSE.md](V19_CFAR_Z_BIAS_ROOT_CAUSE.md)**: The anatomy of a false anomaly and the value of full-cohort testing.
- **[DIVISION_JACCARD_INVESTIGATION_SUMMARY.md](DIVISION_JACCARD_INVESTIGATION_SUMMARY.md)**: The arc from the 0% Division score to the bipartite solver.

---

## Installation & Usage

Atabey is designed to be lightweight and CPU-friendly, mirroring the Kaggle inference environment.

```powershell
# Clone and setup virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies and the package in editable mode
python -m pip install -r requirements.txt
python -m pip install -e .
```

### Running Tests

We maintain a strict suite of deterministic synthetic tests and bounded zero-perturbation regression checks.

```powershell
python -m pytest
```

---

## Competition Context

- **Competition**: `biohub-cell-tracking-during-development`
- **Task**: Detect and track zebrafish cells through 3D space and time.
- **Constraints**: Notebook submissions only. Strict CPU/GPU runtime limit of 720 minutes.
- **Evaluation**: Custom Jaccard metric combining `edge_jaccard + (0.1 × division_jaccard)`.

*Atabey's primary mandate is producing a valid, reproducible baseline path before polishing elegant state machinery.*
