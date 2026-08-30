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

### V24 Containment Hypotheses and Result

Frozen V24.3 has completed full-199 score validation. It reached adjusted edge Jaccard `0.721056`,
a `+0.235028` delta over V19, with 183 improved and 16 regressed samples. All 16 regressions are in
the `6bba` family on the V19 `components + greedy` route. Forensics localize the loss upstream to
E016 detections plus motion-mutual relinking; V24.2 and V24.3 improve every regression over their
immediate predecessors. Submission, automatic fallback, and further pruning remain unauthorized.

The shadow-only containment work tested three linked hypotheses:

1. **Commitment intervention:** removing one accepted predecessor contribution can expose
  assignments whose downstream motion history is path-dependent. This is inspired by ROOT's
  intervention logic, not a literal transfer of Boolean feedback loops to an acyclic lineage graph.
2. **Bounded ILP adjudication:** a three-frame integer program can compare joint ownership paths,
  while an explicit baseline-change charge makes abstention the default and contains broad rewrites.
3. **Combined precision funnel:** commitment persistence should select a narrower and more useful
  set of ILP windows than ambiguity or optimization alone.

The fixed route-90 GPU replay is complete and does not support the combined hypothesis. ROOT found
631 commitment-changed windows, of which 84 were persistent. The contained primary accepted 55
ownership alternatives, but 46 were incompatible with the pruned V24.3 scoring graph and all 9
scoreable rewrites were metric-neutral. The zero-penalty diagnostic had 3 improved, 38 neutral, and
1 regressed scoreable rewrites; all four nonzero outcomes were reconverging rather than persistent.
V24.7 is therefore a **NO-GO for promotion**. The V24.3 baseline remains unchanged, and neither
threshold tuning nor automatic selection is authorized from this opened-label evidence.
The V24.8 independent-cohort inventory accounts for all 199 labeled samples and finds zero unopened
candidates; the historical 34-sample internal split is part of the checkpoint-training 172. V24.8
therefore remains blocked until genuinely new labeled evidence and an immutable source manifest are
available.

V25 opens as read-only upstream-association forensics. It instruments the unchanged E016 plus
motion-mutual path to distinguish candidate-generation failures from candidates that enter and lose,
with V19 comparison and pruning survival exposed only as audit layers. It makes no score, selector,
promotion, routing, or intervention claim.
The [V25 Kaggle CUDA telemetry notebook](notebooks/V25_upstream_association_forensics_cuda_kaggle.ipynb)
runs the frozen 16-case observer while recording separate NVML hardware-utilization evidence.

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
| V23 | Can detector-native, radar-inspired, or parent-centered pair-field evidence rank division actions beyond explicit geometry? | Closed NO-GO for the learned pair-field path. Across three seeds the image model recovered only 6-10 of 29 events at Recall@10, while geometry-only recovered 26/29. Shuffled and static-image controls found no independent image contribution. CFAR and production graphs remain unchanged. |
| V24 | Can a held-out temporal U-Net improve complete-sequence official edge tracking over frozen V19? | Full-199 score validation complete, submission not authorized. Frozen V24.3 reached 0.72106 adjusted edge Jaccard (`+0.23503` vs V19), with 183 improvements and 16 regressions. The route-90 V24.7 commitment-plus-ILP funnel is a promotion NO-GO: its 9 scoreable contained rewrites were neutral, while the zero-penalty diagnostic included one regression. |

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
- [V23 Session Closure](V23_SESSION_CLOSURE_2026-08-02.md): final detector-native evidence
  synthesis, pair-field NO-GO, preserved geometry result, and the boundary for any future version.
- [V23 Bounded Pair-Field Ranker Results](V23_BOUNDED_PAIR_FIELD_RANKER_RESULTS.md): three-seed
  sample-blocked results and mandatory control comparison.
- [V24 Score-First Tracking Preregistration](V24_SCORE_FIRST_TRACKING_PREREGISTRATION.md):
  held-out whole-sequence cohort, three isolated arms, official edge endpoint, and promotion gates.
- [V24 Score-First Tracking Results](V24_SCORE_FIRST_TRACKING_RESULTS.md): frozen 27-sample
  official result, node-inflation gate failure, and HOLD adjudication.
- [V24.1 Node-Inflation Diagnostic](V24_1_NODE_INFLATION_DIAGNOSTIC.md): descriptive
  family/route audit; localized inflation found, but no suppression rule authorized.
- [V24.2 Interior-Orphan Shadow Preregistration](V24_2_INTERIOR_ORPHAN_SHADOW_PREREGISTRATION.md):
  bounded `6bba/components` post-link candidate with edge-preservation safeguards.
- [V24.3 Node-Inflation Decomposition](V24_3_NODE_INFLATION_DECOMPOSITION.md): read-only
  decomposition of removed versus residual nodes across the full-27 cohort.
- [V24.4 Topology Telemetry Audit](V24_4_TOPOLOGY_TELEMETRY_AUDIT.md): bounded per-node and
  exact per-stratum telemetry; connected-node pruning is not yet authorized.
- [V24.3 Short-Fragment Shadow Preregistration](V24_3_SHORT_FRAGMENT_SHADOW_PREREGISTRATION.md):
  frozen size-two interior non-division component shadow.
- [V24.3 Short-Fragment Full-27 Audit](V24_3_SHORT_FRAGMENT_SHADOW_FULL_27_AUDIT.md):
  all frozen gates passed; full-199 score validation authorized, with submission still blocked.
- [V24.3 Full-199 Score Validation Preregistration](V24_3_FULL_199_SCORE_VALIDATION_PREREGISTRATION.md):
  deterministic two-shard population validation with separate training-172 and held-out-27 interpretation.
- [V24.3 Full-199 Score Validation Audit](V24_3_FULL_199_SCORE_VALIDATION_AUDIT.md):
  complete 199-sample merge, population score context, regression audit, and preserved submission boundary.
- [V24.3 Full-199 Regression Forensics](V24_3_FULL_199_REGRESSION_FORENSICS.md):
  16-case edge-error decomposition and review-only containment analysis.
- [V24.5 Commitment Shadow](V24_5_COMMITMENT_SHADOW_LOCAL_2.md): ROOT-inspired predecessor
  intervention on two representative regressions, with one persistent tied assignment.
- [V24.6 Bounded ILP Shadow](V24_6_BOUNDED_ILP_SHADOW_LOCAL_2.md): conservative three-frame
  assignment optimization and explicit baseline-change containment.
- [V24.7 Combined Commitment plus ILP Shadow](V24_7_COMMITMENT_ILP_COMBINED_SHADOW_LOCAL_2.md):
  six-window funnel comparison, proposal classification, and fixed-contract abstention result.
- [V24.7 Route-90 GPU Shadow Preregistration](V24_7_ROUTE_90_GPU_SHADOW_PREREGISTRATION.md):
  fixed 90-sample cohort, runtime contract, endpoints, and interpretation rules.
- [V24.7 Route-90 GPU Shadow Results](V24_7_ROUTE_90_GPU_SHADOW_RESULTS.md): complete evidence,
  compatibility attrition, official-metric outcomes, and promotion NO-GO.
- [V24.8 Post-Pruning Commitment plus ILP Preregistration](V24_8_POST_PRUNING_COMMITMENT_ILP_PREREGISTRATION.md):
  graph-aligned contract; implementation and execution blocked pending genuinely new labeled evidence.
- [V24.8 Independent Cohort Eligibility Audit](V24_8_INDEPENDENT_COHORT_ELIGIBILITY_AUDIT.md):
  complete inventory proving that no unopened labeled repository cohort remains.
- [V25 Upstream Association Forensics Preregistration](V25_UPSTREAM_ASSOCIATION_FORENSICS_PREREGISTRATION.md):
  frozen observability contract for the 16 known V24.3 regressions.
- [V25 Failure Taxonomy Audit](V25_FAILURE_TAXONOMY_AUDIT.md): initial evidence classes,
  preserved negative findings, and the unresolved candidate-generation-versus-ranking question.
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
