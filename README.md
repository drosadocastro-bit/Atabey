# Project Atabey

> Signal processing over brute force. Evidence before conclusions.

Project Atabey is a streaming-first, experimental lineage tracker for the Kaggle competition
[Biohub - Cell Tracking During Development](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development).
It studies how to detect and associate cells across 3D time-lapse microscopy while preserving
ordinary track continuity and representing true parent-to-two-daughter divisions.

Dense tissue, weak contrast, local background variation, ambiguous neighbors, sparse annotations,
and strict runtime limits make this more than a nearest-neighbor problem. Atabey approaches it as a
bounded signal-detection and data-association problem. Its ideas draw from radar engineering,
multi-target tracking, constrained assignment, and uncertainty-aware routing, while every borrowed
analogy must earn its place through microscopy-specific evidence.

## Scope and Intent

Atabey is educational and personal research code. It is not an official Biohub, Kaggle, or
competition-host project; not a validated biological model; and not a medical or diagnostic system.
Its outputs are experimental tracking hypotheses, not authoritative claims about cell identity,
lineage, or developmental biology.

Sparse ground truth creates an important boundary: an unsupported prediction is unknown, not
automatically a false biological event and not evidence of a true one. Claims in this repository are
therefore tied to the evaluator, sample set, and experimental window that produced them.

## Current Research Status

The most important current finding is methodological. Atabey's earlier local Division Jaccard
evaluator was neither the old exploitable host implementation nor the patched official metric. The
repository now calls the pinned official division scorer directly and has parity coverage against the
host regression suite.

Under the corrected official scorer, in the fixed Phase 1/2 bounded windows:

| Path | TP | FP | FN | Interpretation |
|---|---:|---:|---:|---|
| V19 raw bipartite | 4 | 6 | 10 | Recovers real division signal, with limited bounded precision |
| V20 strict firewall | 0 | 0 | 14 | Removes evaluable noise but also suppresses every recovered true division |

The previous claim of approximately 91% official division-FP reduction is withdrawn. Most raw forks
behind that claim were not evaluable under the sparse official metric. The V20 firewall is closed in
its current form unless a structural redesign is justified by new evidence.

Official per-sample and run-level edge/division scoring now call the pinned competition host directly.
Separate sparse EdgeRecall and graph-identity findings remain useful diagnostic evidence, but they are
explicitly non-equivalent to official adjusted edge Jaccard. The complete classification is recorded
in [OFFICIAL_EVALUATOR_PARITY_INVENTORY.md](OFFICIAL_EVALUATOR_PARITY_INVENTORY.md); the canonical
research status and full set of preserved and withdrawn claims remain in
[V21_SESSION_SYNTHESIS_2026-07-22.md](V21_SESSION_SYNTHESIS_2026-07-22.md).

## Design Principles

- **Streaming first:** process timepoints and bounded local volumes without assuming the full 4D
  sample fits comfortably in memory.
- **Physical coordinates:** reason in micrometers rather than silently treating anisotropic voxels as
  isotropic distance.
- **Deterministic baselines:** preserve simple, inspectable paths before adding learned advisers or
  richer assignment machinery.
- **Shadow before mutation:** evaluate candidate mechanisms without changing the production graph
  until zero-perturbation and bounded validation are demonstrated.
- **Official metrics where available:** call pinned host implementations instead of maintaining
  approximate local copies.
- **Failures are results:** retain NO-GO experiments, regressions, and withdrawn claims so later work
  does not rediscover them.
- **No analogy by authority:** radar, particle tracking, pulsar physics, and other domains can suggest
  questions, but they do not validate a cell-tracking mechanism.

## Pipeline

```text
Zarr microscopy sample
  -> streamed timepoint IO
  -> route-aware 3D detection (components or CFAR-derived paths)
  -> physical-coordinate normalization
  -> motion and candidate association
  -> lineage graph construction
  -> optional shadow candidates / uncertainty routing
  -> official or explicitly labeled diagnostic evaluation
  -> GEFF / submission output
```

The repository contains several historical and experimental entry points. Their presence does not
mean every path is approved for submission or active development; consult the session synthesis and
the relevant audit before promoting one.

## Research Evolution

| Arc | Question | Evidence-backed outcome |
|---|---|---|
| V13 | Can a CPU-friendly streaming tracker establish a reproducible baseline? | Yes. It established the frozen reference path and practical runtime discipline. |
| V14-V18 | Can CFAR, kinematics, and shadow advisers improve difficult local detections? | Mixed. Several useful diagnostics survived, while literal radar transfers and some learned/shadow mechanisms failed their bounded gates. |
| V19 | Can watershed localization and bipartite formation improve dense tracking and expose divisions? | Partly. It produced four official division TPs in the corrected bounded audit, but ownership and noise remain unresolved. |
| V20 | Can a strict kinematic firewall clean division topology? | NO-GO in its current form: it suppressed all four corrected V19 TPs. Earlier FP-reduction claims were invalidated by evaluator mismatch. |
| V21 | Can recovery, confidence routing, continuity, or local exclusivity rescue divisions safely? | Partial research result. The joint semantic Phase 0 extractor passed its fixed battery, but the preregistered availability gate failed at 13/46 development and 7/47 calibration positives. Calibrated scoring and constrained assignment are not authorized under the current formation path. |
| V22 | Can public learned detections repair upstream division availability without weakening epistemic guardrails? | Mixed but promising. The conservative post-link second-child rule remained a standalone NO-GO, while the frozen temporal U-Net raised patched-official action availability from 13/46 to 39/46 with zero graph mutation. Semantic ranking plus coupled local ownership is now pre-registered on development only; locked validation and the full 199 remain closed. |

## Start Here

- [V21 Session Synthesis](V21_SESSION_SYNTHESIS_2026-07-22.md): canonical current state,
  corrected evidence, open questions, and priorities.
- [V21 Joint Semantic Scorer and Assignment Design](V21_JOINT_SEMANTIC_ASSIGNMENT_DESIGN.md):
  shadow-only architecture, abstention rules, and locked validation contract.
- [V21 Joint Semantic Phase 0 Audit](V21_JOINT_SEMANTIC_PHASE0_AUDIT.md): raw evidence
  extraction, official projected labels, route provenance, and zero-perturbation results.
- [V21 Semantic Dataset Pre-Registration](V21_SEMANTIC_DATASET_PREREGISTRATION.md): frozen
  development/calibration membership and the positive-availability gate.
- [V21 Semantic Positive Availability Audit](V21_SEMANTIC_POSITIVE_AVAILABILITY_AUDIT.md):
  full 54-sample prerequisite result and the calibrated-scoring NO-GO.
- [V22 Safe-Division Shadow Pre-Registration](V22_SAFE_DIVISION_SHADOW_PREREGISTRATION.md):
  frozen public-rule transfer, development cohort, and official-metric decision contract.
- [V22 Safe-Division Shadow Audit](V22_SAFE_DIVISION_SHADOW_AUDIT.md): development-only
  official outcome and standalone-transfer NO-GO.
- [V22 U-Net Full Development Shadow](V22_UNET_DEVELOPMENT_46_RESULTS.md): frozen detector-only
  availability result, candidate-load guard, and zero-perturbation GO.
- [V22 U-Net Official-Action Availability](V22_UNET_OFFICIAL_ACTION_AVAILABILITY_RESULTS.md):
  patched-official 39/46 action-availability GO and explicit remaining failures.
- [V22 Joint Semantic Ranking With Local Assignment](V22_JOINT_SEMANTIC_ASSIGNMENT_PREREGISTRATION.md):
  sample-blocked ranking, unknown-label policy, and coupled ownership constraint contract.
- [Official Evaluator Parity Inventory](OFFICIAL_EVALUATOR_PARITY_INVENTORY.md): authoritative
  classification of official, diagnostic, experimental, and invariant evaluation surfaces.
- [Official Division Metric Integration](OFFICIAL_DIVISION_METRIC_INTEGRATION.md): host pins,
  adapter design, and parity evidence.
- [V21 Division Recovery Track](V21_DIVISION_RECOVERY_TRACK.md): Track A/Track B history and
  corrected division interpretation.
- [Local Assignment Shadow Audit](V21_LOCAL_ASSIGNMENT_SHADOW_AUDIT.md): why exclusivity is useful
  evidence but insufficient as a standalone selector.
- [Counterfactual Pairing Audit](V21_COUNTERFACTUAL_PAIRING_AUDIT.md): what future continuity can and
  cannot resolve.
- [Sun Check Bounded Audit](ATABEY_SUN_CHECK_BOUNDED_AUDIT.md): microscopy QC/routing analogy,
  confounding result, and correction guardrails.
- [Independent CFAR-Only Sun Check Follow-Up](SUN_CHECK_CFAR_FOLLOWUP_PREREGISTRATION.md):
  locked cohort, official-metric endpoint, and pre-registered decision rules.
- [Adversarial Battery](ATABEY_ADVERSARIAL_BATTERY.md): fixed cases that future changes must face
  before expensive cohort runs.
- [Radar Concepts and Atabey](docs/RADAR_CONCEPTS_AND_ATABEY.md): conceptual transfers and their
  limits.
- [Cross-Repository Transfer Ideas](CROSS_REPO_TRANSFER_IDEAS_FOR_ATABEY.md): learning-oriented map
  of ideas that may transfer, why they might, and what evidence they still require.

Architecture decisions and earlier experiment notes live under [`docs/`](docs/). Historical files
should be read in date/version context; later corrected-metric documents supersede conflicting
Division Jaccard interpretations.

## Installation

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

Install the pinned official competition metric dependencies when reproducing official division
evaluation:

```powershell
python -m pip install -e ".[official-metrics]"
```

Run the deterministic test suite with:

```powershell
python -m pytest
```

Tests marked `slow` require local competition data or trained weights.

## Data and Repository Hygiene

Competition data are intentionally absent from version control. Extract `.zarr` image stores and
`.geff` lineage labels locally under the expected `train/` and `test/` layout; these artifacts can
approach 100 GB and are ignored by git. Do not commit raw competition data, generated weight files,
or large audit logs.

Small source files, tests, fixed adversarial cases, compact result tables, and research notes are the
durable record of the project.

## Competition Context

- **Competition:** `biohub-cell-tracking-during-development`
- **Problem:** detect and track cells through 3D space and time, including lineage divisions
- **Submission environment:** Kaggle notebook execution under competition runtime constraints
- **Evaluation discipline:** use the pinned official implementation for claims about official metric
  behavior; label local approximations and sparse diagnostics explicitly

Atabey's goal is not to make uncertainty disappear. It is to make each tracking decision,
abstention, failure, and correction inspectable enough that the next experiment starts from evidence
rather than memory.
