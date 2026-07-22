# Rule-Based Pipeline Ceiling Summary (V14-V18)

## Purpose

> [!NOTE]
> **V19 Watershed Addendum:** The "ceiling" mapped in this document applies specifically to the *linking* layer. As proven by the subsequent V19 Watershed sub-voxel refinement GO, the detection and localization layer still had real, fixable headroom. This perfectly validates the core conclusion of this document: the bottleneck was always poor upstream localization in dense clusters, not a lack of linking heuristics.

This document closes the rule-based experimentation chapter by consolidating evidence across four independent branches:

1. bounded-CFAR reformulation,
2. correlation and track-continuity recovery,
3. kinematic soft-linking with hard exclusion,
4. bounded global optimization.

The goal is to state, with quantified evidence, where the rule-based ceiling sits on this dataset and why the next lever should move to learned detection (or upstream localization refinement).

## Source Evidence Map

Primary artifacts used in this consolidation:

- [submissions/cfar_bounded_scan_fulltrain.json](../submissions/cfar_bounded_scan_fulltrain.json)
- [submissions/v14_diagnostics.json](../submissions/v14_diagnostics.json)
- [submissions/oss_diagnostics.json](../submissions/oss_diagnostics.json)
- [submissions/v15_traineval_OFF.json](../submissions/v15_traineval_OFF.json)
- [submissions/v15_traineval_ON.json](../submissions/v15_traineval_ON.json)
- [submissions/correlation_merge_gate_10tp.json](../submissions/correlation_merge_gate_10tp.json)
- [docs/V16_KINEMATIC_CLOSEOUT.md](V16_KINEMATIC_CLOSEOUT.md)
- [docs/v17_hard_exclusion.md](v17_hard_exclusion.md)
- [V17_GATE_TRACE_AUDIT.md](../V17_GATE_TRACE_AUDIT.md)
- [docs/V18_global_optimization_bounded.md](V18_global_optimization_bounded.md)
- [V18_COVERAGE_FORENSICS.md](../V18_COVERAGE_FORENSICS.md)

Note: this summary is documentation-only and does not introduce new experiments.

## Consolidated Branch Findings

| Branch | What Was Tried | Mechanism Targeted | Quantitative Result | Ceiling Root Cause |
| --- | --- | --- | --- | --- |
| Bounded-CFAR (parked) | Reformulated and diagnosed CFAR behavior under bounded signal conditions; profiled collapse risk and recoverability. | Detector thresholding assumptions under high background and dense clutter. | CFAR-routed cohort size was 66, with 51 marked at-risk at pfa 1e-03 (77.27%) in [submissions/cfar_bounded_scan_fulltrain.json](../submissions/cfar_bounded_scan_fulltrain.json). OSS diagnostic reported 51 Type-A recoverable and 0 Type-B blind-spot (100% and 0%) in [submissions/oss_diagnostics.json](../submissions/oss_diagnostics.json). | Formulation mismatch between CA-CFAR assumptions and bounded [0,1] signal dynamics in dense high-background regions. Detection quality becomes unstable before linking even starts. |
| Correlation and track-continuity (V15, merge-gated) | Added synthetic continuity candidates, then merge-gated suppression to reduce identity collision. | Gap recovery and continuity reinforcement when direct detections are weak. | Merge-gated at-risk node recall delta stayed positive (+0.011119) with zero displaced matches, but at-risk edge recall delta remained negative (-0.001737) and mean collision fraction was 0.268905 in [submissions/correlation_merge_gate_10tp.json](../submissions/correlation_merge_gate_10tp.json). On real pipeline ON vs OFF, at-risk mean quality delta was only +0.000243 with 9 improved, 9 regressed, 33 unchanged (computed from [submissions/v15_traineval_ON.json](../submissions/v15_traineval_ON.json) and [submissions/v15_traineval_OFF.json](../submissions/v15_traineval_OFF.json)). | Real recovery exists, but identity collision and wrong-edge extrapolation cap net edge gains in ambiguous regions; target cohort remains operationally flat. |
| Kinematic soft-linking (V16 to V17) | Applied hard exclusion to prevent frame-skip enrollment when direct adjacent candidates are available. | Competition between direct t to t+1 links and frame-skip recovery candidates. | At-risk mean quality delta improved from -0.011172 (V16) to -0.000884 (V17), a 92.09% reduction in regression magnitude, but remained negative in [docs/V16_KINEMATIC_CLOSEOUT.md](V16_KINEMATIC_CLOSEOUT.md) and [docs/v17_hard_exclusion.md](v17_hard_exclusion.md). V17 edge follow-up fixed 56 of 66 Type-1 edges, with 10 residuals classified as direct-link criteria or eligibility mismatch (10 of 10). | Hard exclusion removed most harm, but residual dense-region ambiguity and direct-link criteria mismatch prevented clean promotion to flat or positive target-cohort behavior. |
| Bounded global optimization (V18) | Shadow-only short-window global scoring (t, t+1, t+2), first on known residual edges, then on disagreement-first subset. | Non-greedy global consistency in locally ambiguous linking cases. | On known Type-1 residuals: 0 of 66 changed decisions in [docs/V18_global_optimization_bounded.md](V18_global_optimization_bounded.md). On disagreement-first subset: 670 decision changes, but only 33 evaluable records, with 5 global-better and 0 greedy-better; forensics showed 2931 of 3319 unevaluable records (88.31%) had no GT nearby in [V18_COVERAGE_FORENSICS.md](../V18_COVERAGE_FORENSICS.md). | Method can change decisions and shows small positive mapped signal, but evidence is capped by sparse GT coverage and unresolved ambiguity in the underlying detection geometry. |

## Common Thread Across All Four Branches

All four branches improved something real in dense, high-background, high-ambiguity neighborhoods:

- bounded-CFAR isolated a real detector stress regime,
- correlation recovery added real node recoveries,
- hard exclusion removed most V16 regression magnitude,
- global optimization found real disagreement cases and a small positive mapped signal.

But all four also hit a ceiling for the same underlying reason expressed through different failure shapes:

- not enough discriminating signal in raw detections and local geometry to resolve identity robustly in ambiguous regions.

The failure modes differ by branch, but the bottleneck is shared:

- detector assumption mismatch,
- collision-prone synthetic continuity,
- direct-link eligibility mismatch under crowding,
- sparse-mapping-limited evaluation of global decisions.

Each is a different manifestation of limited separability in difficult regions, not a simple lack of linking heuristics.

## Key Insight: Layer Boundary of the Remaining Gap

Rule-based redesigns of linking and scoring have now been exercised across thresholding, candidate generation, kinematic gating, and global short-window optimization.

The remaining gap is not primarily a linking-logic gap.

It is a detection-quality and discriminability gap in ambiguous dense regions, which sits upstream of linking and constrains every downstream rule-based variant.

## Quantified Ceiling Statement

The ceiling is established by the following combined evidence:

1. CFAR collapse-risk concentration is high in the routed cohort: 51 of 66 (77.27%) at pfa 1e-03 in [submissions/cfar_bounded_scan_fulltrain.json](../submissions/cfar_bounded_scan_fulltrain.json).
2. Recoverable continuity signal exists in principle: OSS Type-A was 51 and Type-B was 0 (100% and 0%) in [submissions/oss_diagnostics.json](../submissions/oss_diagnostics.json).
3. Real-pipeline improvements from linking-layer fixes remain below promotion thresholds on target cohorts:
   - V15 ON vs OFF at-risk quality delta: +0.000243 (flat operationally), from [submissions/v15_traineval_ON.json](../submissions/v15_traineval_ON.json) and [submissions/v15_traineval_OFF.json](../submissions/v15_traineval_OFF.json).
   - V17 at-risk quality delta: -0.000884 after hard exclusion, from [docs/v17_hard_exclusion.md](v17_hard_exclusion.md).
4. Even non-greedy global reasoning over existing detections cannot fully break the ceiling:
   - disagreement-first showed 5 to 0 mapped directional signal but only 33 evaluable records,
   - 88.31% of unevaluable disagreements had no nearby GT support, from [V18_COVERAGE_FORENSICS.md](../V18_COVERAGE_FORENSICS.md).

Together, these numbers support a ceiling at the rule-based linking layer for this dataset under current detection evidence quality.

## Why This Motivates the CNN-Advisor Pivot

Because the limiting factor is discriminability in the raw detection layer, the highest-leverage next step is not another linking heuristic.

A learned detector path, aligned with the in-progress CNN-advisor direction, targets the actual bottleneck directly:

- improve separation of true cells in dense, high-background regions,
- reduce identity ambiguity before linking,
- give downstream linking and global scoring cleaner candidate sets to operate on.

This makes the CNN-advisor track the correct next experimental axis: it changes the information content of detections rather than re-optimizing reasoning over the same ambiguous CFAR-derived candidates.

## Close-Out Decision

Rule-based linking/scoring exploration is closed as NO-GO for promotion beyond current bounded baselines on this dataset.

Future rule changes may still be useful for robustness, but they should be treated as secondary to upstream detection-quality gains.

Primary forward path: continue the CNN-advisor and learned-detector direction as the main lever for further quality lift.