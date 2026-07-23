# Official Evaluator Parity Inventory

Date: 2026-07-23
Status: complete

## Purpose

This inventory identifies every evaluation surface under `src/atabey/evaluation` and the derived
metrics used by experiment scripts. Its purpose is to prevent local calibration signals from being
described as competition-equivalent metrics.

The classification labels are:

- **Official direct:** Atabey converts its graph representation and calls the pinned competition-host
  implementation without reimplementing matching or scoring.
- **Official compatibility wrapper:** a local API delegates to an official-direct adapter.
- **Diagnostic only:** a bounded local measurement that answers a useful research question but is not
  the Kaggle metric.
- **Experimental diagnostic:** a deliberately alternate or historical local measurement.
- **Invariant:** a software-integrity check, not a biological or competition score.

## Pinned Provenance

- Competition host: `royerlab/kaggle-cell-tracking-competition`
- Host commit: `075fc5f5a52d11077f9dc2b074644618f26939e2`
- Patched division commit: `aa65e90aeb8a774ebb1b549e547787b87ac8a01c`
- `tracksdata` commit: `39dccf3a243e44274759468cb31b2ad9e7fc1d09`
- Matching radius: `7 um`

The optional dependency pins live in `pyproject.toml`.

## Executed Host Evidence

The current pinned host was executed against Atabey's local competition training data:

| Host suite | Result | Coverage |
|---|---:|---|
| `tests/test_metrics.py` | 44/44 passed | matching, edge counts/Jaccard, node recall, node-count adjustment, run aggregation, duplicate/merge/out-degree guards, real GEFF regressions |
| `tests/test_division_metrics.py` | 39/39 passed | patched directed-fork division matching and exploit regressions |

Atabey's direct adapter suite passes 7/7 targeted tests. The repository-wide suite is also required
before publishing changes.

## Competition-Equivalent Surfaces

| Atabey surface | Classification | Host call | Notes |
|---|---|---|---|
| `evaluate_official_tracking()` | Official direct | `tracking_cellmot.metrics.evaluate`, `node_recall`, `per_sample_metrics` | Returns official edge TP/FP/FN, edge Jaccard, adjusted edge Jaccard, node recall/count adjustment, patched division counts, and per-sample score. |
| `summarize_official_tracking()` | Official direct | `tracking_cellmot.metrics.summarise` | Uses the host's edge-denominator weighting and micro-averaged division counts. Local averaging must not substitute for this function when making competition-score claims. |
| `evaluate_official_divisions()` | Official direct | `tracking_cellmot.division_metrics.score_divisions` | Preserves the patched directed parent-to-two-daughter rules and sparse unsupported-fork behavior. |
| `compute_division_jaccard()` in `sparse_ground_truth.py` | Official compatibility wrapper | delegates to `evaluate_official_divisions()` | Legacy matching arguments remain only for caller compatibility and are ignored. |

These are the only local surfaces authorized for claims using the words **official**, **competition
metric**, **adjusted edge Jaccard**, or **Division Jaccard**.

## Local Calibration Surfaces

| Surface | Classification | What it measures | Why it is not official |
|---|---|---|---|
| `match_sparse_centroids()` | Diagnostic only | GT-order greedy one-to-one centroid assignment within a same-frame radius | The host uses `tracksdata` distance matching and its own collision/merge behavior; ordering can change local assignments. |
| `SparseEvaluationReport.sparse_recall` | Diagnostic only | fraction of sparse GT nodes matched by the local greedy matcher | It inherits local matching behavior and is not the host `node_recall`. |
| `SparseEvaluationReport.sparse_edge_recall` / historical `EdgeRecall` | Diagnostic only | recall among GT edges whose two endpoints were locally matched | It does not count official edge FP, excludes edges with unmatched endpoints from its denominator, and is not edge Jaccard. |
| `predicted_to_estimated_node_ratio` | Diagnostic only | `N_pred / N_estimated` | The official `total_node_ratio` is `(N_pred - N_total) / N_total`; the values are related but not interchangeable. |
| `nearest_centroid_errors_um()` | Diagnostic only | nearest prediction distance for each supplied sparse point | It is localization calibration without one-to-one host matching or graph scoring. |
| script-level `quality_score = 0.5*sparse_recall + 0.5*sparse_edge_recall` | Diagnostic only | a historical ranking composite for bounded experiments | It has no host equivalent and must never be presented as a competition-score proxy without an explicit empirical study. |

Sparse diagnostics remain useful for detector/linker debugging when their matching rule, radius,
sample set, and bounded scope are reported. Their existing `SparseEvaluationReport.caution` correctly
states that they are not the official Kaggle metric.

## Experimental And Non-Metric Surfaces

| Surface | Classification | Boundary |
|---|---|---|
| `sparse_ground_truth_v19_experimental.py` | Experimental diagnostic | Uses a global distance-ordered greedy matcher. It exists to expose matcher-order sensitivity and must not replace either the stable sparse diagnostic or official host matching. |
| `compute_multi_source_agreement()` in `agreement_maps.py` | Experimental diagnostic | Clusters detections from multiple detector sources. Its counts describe source agreement, not correctness or a competition metric. |
| graph signatures and `source_zero_perturbation` | Invariant | Prove a shadow experiment did not mutate its source graph. They say nothing about biological validity or score quality. |
| raw candidate/fork counts | Diagnostic only | Describe mechanism output volume. They become official TP/FP/FN only after evaluation by the corresponding official adapter. |

## Aggregation Boundary

Official run-level adjusted edge Jaccard is not a plain mean and is not weighted by
`estimated_number_of_nodes`. The host:

1. computes per-sample adjusted edge Jaccard;
2. weights each valid sample by `edge_tp + edge_fp + edge_fn`;
3. micro-averages division TP/FP/FN; and
4. adds `0.1 * division_jaccard` when divisions are present.

Research summaries may use medians, family stratification, or other weights, but those must be named
as research summaries and kept separate from official aggregation.

## Missing By Design

- Hidden-test leaderboard scoring cannot be reproduced locally because the labels are unavailable.
- Atabey does not maintain a second implementation of host matching or scoring; direct pinned calls
  are the parity strategy.
- Historical logs are not retroactively transformed into official metrics. Claims are re-evaluated
  only when the original graphs or sufficient count evidence still exist.

## Closure

The parity inventory is complete:

- official per-sample edge/division scoring is directly integrated;
- official run-level aggregation is directly integrated;
- local sparse and experimental metrics are explicitly classified as non-equivalent diagnostics;
- no unidentified local evaluation surface remains.

Future evaluation additions must enter this inventory before they are described as official or used
to support a competition-score claim.
