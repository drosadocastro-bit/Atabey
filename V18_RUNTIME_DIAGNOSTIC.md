# V18 Runtime Diagnostic

## Scope

Read-only instrumentation pass only.

- No behavioral changes to V18 decision logic.
- No injection into graph.
- Goal: identify where the observed V18 runtime cost comes from before any further accuracy work.

Artifacts used/generated:

- submissions/v18_global_optimization_bounded.json
- submissions/v18_runtime_diagnostic.json
- scripts/run_v18_runtime_diagnostic.py

Diagnostic run configuration:

- Cohort slice: at-risk
- Samples profiled: 6
- Window sizes profiled: 3 and 5
- Known edge target: Type1_direct_edge_replaced_by_frame_skip rows from submissions/v16_diagnostic_root_cause.json

## 1) Stage-Level Timing Breakdown

The per-edge optimizer path was decomposed into:

1. candidate enumeration (window candidate collection + transition enumeration)
2. cost build (graph/cost edge construction)
3. solve (min-cost-flow call)

### Window = 3 (current bounded setting)

Mean per-edge decision time: 17.53 ms

- candidate enumeration: 8.24 ms (46.99%)
- cost build: 1.52 ms (8.68%)
- solve: 7.77 ms (44.30%)

### Window = 5 (diagnostic scaling probe)

Mean per-edge decision time: 975.02 ms

- candidate enumeration: 932.25 ms (95.61%)
- cost build: 9.03 ms (0.93%)
- solve: 33.74 ms (3.46%)

Key finding:

- At 3-frame scope, solve is material but still millisecond-scale.
- At 5-frame scope, runtime is dominated by candidate enumeration, not by min-cost-flow solving.

## 2) Where the 38s/Sample Cost Comes From

From submissions/v18_runtime_diagnostic.json:

- mean graph-build time per sample: 35.82 s
- mean decision time per edge (window=3): 17.53 ms
- graph-build share vs shadow decision share:
  - graph-build: 99.951%
  - shadow decision: 0.049%

Interpretation:

- The ~38 s/sample cost is not from global optimization solve complexity.
- It is dominated by full-sample CFAR+sidelobe graph build in build_graph_cfar_sidelobe.
- This is setup overhead relative to the bounded optimizer, not an inherent min-cost-flow bottleneck for the local V18 decision itself.

## 3) Scaling Behavior

### Window size scaling

Mean per-edge decision time:

- window=3: 17.53 ms
- window=5: 975.02 ms
- multiplier: ~55.6x

This increase is strongly superlinear with window extension in the current diagnostic implementation, and the profile shows the increase is almost entirely candidate enumeration work.

### Sparse vs dense local neighborhoods

Window=3:

- sparse mean: 13.67 ms
- dense mean: 19.94 ms
- dense/sparse: 1.46x

Window=5:

- sparse mean: 1446.40 ms
- dense mean: 621.61 ms

The window=5 sparse/dense inversion indicates runtime variance is influenced by temporal candidate-distribution structure (which frames contain large populations and transition fan-out), not just local first-layer count.

## 4) Extrapolation vs Kaggle Runtime Budget

Using the full-run V18 means (from submissions/v18_global_optimization_bounded.json) and 720-minute budget:

- projected 66-sample runtime: 42.07 minutes (5.84% of budget)
- projected 51-sample runtime: 32.51 minutes (4.52% of budget)

These are additive runtime estimates for the profiled V18 path over those cohorts.

## 5) Runtime GO/NO-GO

Decision: NOT a runtime NO-GO at current bounded (3-frame) scope.

Reasoning:

1. The dominant ~38 s/sample cost is setup/graph-build overhead, not optimizer solve time.
2. The bounded window=3 optimizer solve path is millisecond-scale.
3. Extrapolated cohort runtime remains far below the 720-minute budget.

However:

- Expanding horizon (window=5) causes severe candidate-enumeration blow-up in the current implementation.
- Any future widening of window/hypothesis depth requires strict pruning/caching or it will become impractical.

## 6) Recommended Next Step

Because runtime is dominated by fixable overhead (full-sample build and candidate-enumeration strategy), proceed with targeted optimization before any expanded-horizon test:

1. Reuse/carry forward existing graph outputs instead of rebuilding full sample just for V18 shadow diagnostics.
2. Restrict profiling/execution to disagreement-first subset only.
3. Keep window at 3 for next accuracy checks unless candidate-enumeration pruning is added.

Conclusion:

- Runtime does not close the V18 line of work by itself at bounded scope.
- Continue only with disagreement-first accuracy validation under 3-frame bounded mode and explicit runtime guards.
