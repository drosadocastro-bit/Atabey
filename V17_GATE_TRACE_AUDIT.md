# V17 Gate Trace Audit

## Scope

This is a read-only, instrumentation-only audit of per-source exclusion gate decisions:

- singleton precheck (current V17 behavior)
- full-context precheck (V17.1-alignment style check)

No behavioral changes were applied to kinematic_recovery.py during this pass.

## Artifacts

- submissions/v17_gate_trace_audit.json
- submissions/v17_gate_trace_records.jsonl

## Cohort and Coverage

- Cohort: routed CFAR 66 samples
- Considered source candidates: 21643
- Disagreement sources: 3861
- Disagreement rate: 0.1783948620801183 (17.84%)

## Density / Crowding Signal

- Dense threshold (neighbors within link radius): >= 3
- Dense disagreements: 2157
- Sparse disagreements: 1704
- Median neighbors (all considered): 2
- Median neighbors (disagreements only): 3
- Mean neighbors (all considered): 2.5433
- Mean neighbors (disagreements only): 2.9021

Interpretation: disagreements are enriched in more crowded local neighborhoods, consistent with exclusion sensitivity to assignment competition.

## Outcome Mapping vs V17 and V17.1

From disagreement_outcome_comparison:

- mapped_disagreements: 39
- singleton_better: 0
- full_context_better: 0
- ties: 39

Additional summary from disagreement_outcomes list:

- preferred_check counts: unknown=3822, tie=39
- outcome_v17 counts: unmapped=3822, unchanged=39
- outcome_v17_1 counts: unmapped=3822, unchanged=39

Critical limitation: most disagreement sources do not map to evaluable sparse GT edge outcomes in this audit framing, so direct winner attribution (singleton vs full-context) is mostly unavailable here.

## Concrete Disagreement Examples

Representative mapped tie examples (all singleton=true, full_context=false, unchanged in both V17 and V17.1):

1. sample_id=44b6_40c45f5a, source_id=44b6_40c45f5a:t5:cf206, frame_t=5, nearest=7.176 um, second=10.349 um, neighbors=1
2. sample_id=44b6_551a5dba, source_id=44b6_551a5dba:t6:cf56, frame_t=6, nearest=7.413 um, second=8.723 um, neighbors=2
3. sample_id=44b6_668e0cc7, source_id=44b6_668e0cc7:t7:cf183, frame_t=7, nearest=1.675 um, second=3.173 um, neighbors=4

These examples reinforce that disagreement can appear across both sparse and dense local contexts, but the disagreement concentration is higher in denser neighborhoods overall.

## Why Singleton Is Still the Better Operational Proxy (Current Evidence)

- Independent validation already showed full-context alignment attempt (V17.1) degraded outcomes versus V17.
- This trace audit shows disagreements are common in crowded contexts where assignment competition is high.
- The audit does not provide broad mapped evidence that full-context precheck improves edge outcomes in these disagreement regions.

Given current evidence, singleton precheck remains the safer operational default.

## Narrow Refinement Hypothesis (For Future Work)

Do not attempt broad criteria alignment again. Instead, test a tightly bounded refinement:

- Keep singleton precheck as default.
- Optionally invoke a secondary context-aware veto only when crowding is high and candidate-distance ambiguity is high (for example, high neighbor count plus small nearest-vs-second gap).
- Evaluate only on disagreement-heavy dense subsets first, then on the full 66 cohort.

This keeps the strong V17 default while probing whether a narrowly gated context check can reduce false exclusions without reproducing V17.1 regression.

## Lessons Learned

- Alignment-by-criteria is not equivalent to alignment-by-outcome. Matching gate semantics to a baseline linker can still degrade measurable edge quality.
- Gate disagreements cluster in crowding-heavy neighborhoods, so local competition pressure must be treated as a first-class condition in exclusion design.
- Sparse GT mapping coverage can be the limiting factor in mechanism attribution; instrumenting decisions is necessary but not sufficient without evaluable outcome linkage.
- Broad behavioral flips are high risk in this part of the pipeline. Bounded, trigger-based changes are safer than global policy swaps.

## NO-GO Decision (Current State)

Decision: NO-GO for full-context exclusion alignment as a production behavior change.

Why NO-GO:

- Prior validation already showed V17.1 underperformed V17 on the targeted cohort.
- This audit does not produce mapped evidence that full-context precheck wins in disagreement regions (0 mapped wins for singleton, 0 for full-context, 39 ties, 3822 unmapped).
- Disagreement enrichment in crowded contexts increases risk of broad unintended regressions if context checks are globally applied.

Operational state: keep V17 singleton gate as the active path.

## Recommendation

Keep V17 singleton exclusion gate as current best state.

Do not ship full-context alignment behavior.

Use this audit as a basis for a narrow, density/ambiguity-triggered experimental gate refinement only.
