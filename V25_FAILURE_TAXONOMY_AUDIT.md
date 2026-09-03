# V25 Failure Taxonomy Audit

Date: 2026-09-03

Status: **CUDA TELEMETRY COMPLETE; DESCRIPTIVE MECHANISM AUDIT CLOSED**.

The fixed cohort is the 16 samples where V24.3 regressed against V19. Existing
The frozen Kaggle run completed all 16 full sequences. It emitted 16 sample
records, deterministic association payloads, official correspondence, and
separate hardware telemetry without mutating a graph.

## Direct Answer

Across 1,069 V19-credited ground-truth edges lost by V24.3:

| Edge-level class | Count | Share |
| --- | ---: | ---: |
| `candidate_selection_ranking_failure` | 704 | 65.86% |
| `candidate_generation_failure` | 243 | 22.73% |
| `metric_node_adjustment_only_effect` | 99 | 9.26% |
| `post_link_pruning_interaction` | 23 | 2.15% |
| `unresolved_insufficient_telemetry` | 0 | 0.00% |

The dominant answer is therefore **the correct association entered and lost**,
not that it never entered. This is an edge-level statement: 14 non-adjustment
samples contain mixed generation and selection mechanisms and must not be
collapsed to one sample-level cause.

## Mechanism Decomposition

Of the 243 generation failures, 63 have at least one missing E016 endpoint
match. The remaining 180 have both endpoints but fail the fixed 9 um geometric
candidate gates: 109 fail motion prediction only, 9 fail physical step only,
and 62 fail both.

Exact replay of the pinned SciPy `cKDTree` choices separates the 704 selection
losses into:

| Selection subtype | Count | Selection share |
| --- | ---: | ---: |
| Correct target loses forward motion-prediction rank | 436 | 61.93% |
| Correct rank-1 target fails reverse mutuality | 268 | 38.07% |

Selection dominates every non-adjustment sample. `6bba_fc516dc6` is the only
sample where reverse-mutuality losses exceed forward-ranking losses; it still
contains both mechanisms.

The two adjustment-only samples are `6bba_b204cac7` and `6bba_ed9377fd`.
The four catastrophic samples are `6bba_2646afc7`, `6bba_2540cd90`,
`6bba_76db78c1`, and `6bba_d5eae175`.

## Replay And Observer Boundary

Replaying the frozen linker from recorded physical coordinates reproduced all
86,778 relink edges exactly, with zero missing or extra edges. The observer's
NumPy ordering marked 23 rejected candidates as rank-1 mutual even though the
executed SciPy path did not accept them. Quantized nearest-neighbor ties account
for a visible subset. Consequently, high-level candidate presence and
acceptance remain valid, but forward-versus-reverse subtyping uses exact pinned
`cKDTree` replay rather than observer rank labels.

## Preserved Negative Findings

- V24.2 and V24.3 improve every regression over their immediate predecessor;
  existing sample-level evidence does not identify pruning as the cause.
- Division handling is not causal in the retained aggregate evidence.
- Route identity cannot authorize fallback: the same `components + greedy`
  stratum contains 92 V24.3 wins.
- Node-ratio, edge-ratio, and short-fragment-removal thresholds do not isolate
  the regressions without many false positives.
- V24.7 commitment plus ILP does not supply a rescue mechanism.

## Decision

V25 observability is complete. The evidence supports studying upstream
association selection before further pruning work, but it does not identify a
safe intervention. No threshold tuning, V19/V24 selector, automatic routing,
graph mutation, promotion, or submission is authorized. Any intervention
requires a separate frozen preregistration and independent evidence.

Machine result: `v25_upstream_association_forensics_results.json`.