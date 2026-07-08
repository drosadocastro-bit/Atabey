# V18 Bounded Global Optimization Exploration

Status: NO-GO (for promotion beyond shadow mode)

## Objective

Run a bounded global-association experiment on a known real failure mode, not a pipeline rewrite.

Chosen narrow target:

- Type1 wrong-edge residual class from prior diagnostics:
  - Type1_direct_edge_replaced_by_frame_skip
  - Source artifact: submissions/v16_diagnostic_root_cause.json
  - Target set size: 66 edges

Guardrails respected:

- Shadow-only decision scoring
- No graph injection
- No run.py or V13 default changes
- Short window only (3-frame neighborhood: t, t+1, t+2)

## Precedent Basis

This bounded experiment follows well-established global-association precedents in cell tracking:

- Min-cost-flow and network-flow data association (including approaches used by modern trackers such as Ultrack-class pipelines)
- Multi-hypothesis/global association literature for ambiguous local linking
- Published ant-colony lineage reconstruction as a global-search precedent for escaping local minima

Note: this branch tests the global-association hypothesis itself first with the lowest-risk implementation (min-cost-flow-style short window), before any bespoke ACO-style investment.

## Implementation Scope

New isolated module:

- src/atabey/tracking/global_window_optimizer.py

New experiment runner:

- scripts/run_v18_global_optimization_bounded.py

Method (per known-problem source edge):

1. Build current V17 hybrid graph for the sample (same detector/linking settings as v17_hard_exclusion_validate.json).
2. For each target source, collect local candidates in t+1 and t+2.
3. Compare:
   - Greedy/direct local adjacent choice (baseline linker behavior)
   - Global short-window choice via min-cost-flow-style objective over t -> t+1 -> t+2 (with dynamic-program fallback)
4. Log both decisions, agreement/disagreement, and GT-mapped correctness as shadow records.

No edge replacement was applied to the graph.

## Validation Protocol

Reused the exact V16/V17 cohort discipline:

- Cohorts: routed CFAR 66, at-risk 51, outside 15
- Metric reference: quality_score = 0.5*sparse_recall + 0.5*sparse_edge_recall
- Runtime reported explicitly

Artifacts:

- submissions/v18_global_optimization_bounded.json
- submissions/v18_global_optimization_shadow_edges.jsonl

## Results

### Decision outcomes on the 66 known Type1 edges

- considered_edges: 66
- changed_decisions (global vs greedy): 0
- global_better: 0
- greedy_better: 0
- both_correct: 66
- both_wrong_or_unmapped: 0

By cohort:

- routed 66: changed=0, global_better=0, greedy_better=0, both_correct=66
- at-risk 51 intersection (53 edges from the 66 set): changed=0, both_correct=53
- outside 15 intersection (13 edges from the 66 set): changed=0, both_correct=13

### Runtime

- graph_build_total_seconds: 2517.81
- graph_build_mean_seconds: 38.15 per sample
- shadow_eval_total_ms: 6482.38
- shadow_eval_mean_ms: 98.22 per edge decision
- shadow_eval_max_ms: 4949.83

Interpretation:

- The incremental shadow scorer is bounded and computationally tractable relative to graph build time.
- But it produced no decision changes on this known residual subset.

## Before/After Interpretation

For this specific narrow target, the hypothesis "global short-window association resolves the known wrong-edge residuals better than greedy/direct" is not supported by observed outcomes.

Observed signal:

- Zero decision deltas
- Zero net edge-correction gains

This is valuable evidence that, for this residual subset as currently represented, the failure is likely not a local-greedy-vs-global-association issue.

## GO/NO-GO

Decision: NO-GO for promotion beyond bounded shadow mode.

Why:

1. No meaningful fraction of known failure cases was fixed (0/66 changed, 0 global_better).
2. No edge-level gain signal exists to justify injection risk.
3. Additional complexity (ACO/annealing/quantum-inspired variants) is unlikely to unlock value on this exact failure class without a stronger causal signal first.

## Practical Next Step

If V18 is revisited, keep scope equally bounded and change the causal target, not the optimizer family:

- Focus on cases where decision disagreement actually exists first (for example, ambiguous-target neighborhoods identified by prior gate-trace analysis), then rerun the same shadow protocol.
- Keep global optimization shadow-only until there is clear edge-level lift on known-problem cases.

## Disagreement-First Follow-Up (Recommended Next Step Executed)

A dedicated disagreement-first shadow validation was run on the at-risk cohort using the V17 gate-trace disagreement records (strict 3-frame window, graph reused per sample).

Artifacts:

- submissions/v18_disagreement_subset_validate.json
- submissions/v18_disagreement_subset_records.jsonl
- scripts/run_v18_disagreement_subset_validation.py

Headline results:

- disagreement records evaluated: 3337 (50 at-risk samples)
- changed decisions (global vs greedy): 670
- evaluable records (GT target available): 33
- global_better: 5
- greedy_better: 0
- both_correct: 13
- unmapped_or_unevaluable: 3319

Runtime (at-risk disagreement-first run):

- graph_build_total_seconds: 2476.85
- graph_build_mean_seconds: 49.54
- shadow_eval_total_ms: 144395.66
- shadow_eval_mean_ms: 43.27

Interpretation:

- The disagreement-first subset does produce nontrivial behavioral divergence (670 decision changes).
- There is a small positive mapped signal (5 global_better, 0 greedy_better) in the limited evaluable subset.
- Mapping coverage remains the dominant limitation (only 33 evaluable out of 3337 disagreement records).

Decision after follow-up:

- Keep this line in shadow/diagnostic status only.
- The signal is interesting but too sparse in evaluable GT coverage to justify injection.
- Any promotion requires substantially stronger evaluable edge-level lift, not just raw decision-change volume.
