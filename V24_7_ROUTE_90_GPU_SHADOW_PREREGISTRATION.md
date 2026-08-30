# V24.7 Route-90 Commitment plus ILP GPU Shadow Preregistration

Date: 2026-08-29

Status: **AUTHORIZED FOR SHADOW EXECUTION ONLY**.

This experiment does not authorize graph mutation, threshold tuning, automatic
V19/V24 selection, submission generation, or production integration.

## Question

Across the complete route-matched cohort, do persistent predecessor-intervention
effects identify a narrower set of meaningful joint-assignment alternatives than
reconverging effects, and do those alternatives improve the retrospective official
metric when applied to a graph copy?

The experiment evaluates a stability and containment mechanism. It does not infer
biological identity or provide untouched generalization evidence because all 199
labels have already been opened.

## Fixed Cohort

The cohort is every sample in `v22_route_prevalence_199.json` satisfying:

```text
family == 6bba
detector == components
link_strategy == greedy
```

This produces 90 samples: all 16 known V24.3 regressions against V19 and 74
route-matched V24.3 wins. No control sampling is performed. Regression status is
used only for retrospective stratification, never as an inference input.

The exact ordered IDs and source hashes are frozen in
`tests/fixtures/v24_7_route_90_shadow.json`.

## Frozen Runtime Contract

- frozen E016 checkpoint SHA-256:
  `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`
- frozen predictor SHA-256:
  `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`
- full sequences; no timepoint cap
- U-Net batch size: 4
- motion-mutual link radius: `9.0 um`
- commitment candidates: 64 ambiguity-ranked accepted edges per sample
- commitment horizon: 2 frames
- maximum ILP windows: 16 changed-assignment windows per sample
- ILP baseline-change penalty: `2.0 um` per symmetric-difference edge
- minimum contained improvement: `0.5 um`
- maximum binary variables: 512 per window
- solver time limit: 5 seconds per window
- resume enabled
- deterministic replay required on the first sample

## Graphs and Scoring

Frozen E016 coordinates are relinked with motion-mutual. The V24.3 baseline is
reconstructed by applying V24.2 isolated-node pruning followed by V24.3 short-
fragment pruning. Both pruning steps preserve accepted edges.

The commitment audit runs on the relink graph. Every record with at least one
changed downstream assignment enters the ILP funnel, persistent records first.
The ILP primary and zero-penalty diagnostic remain separate.

Each non-empty ILP proposal is applied to a new V24.3 graph copy and scored with
the pinned official tracking evaluator. The source graph must retain its exact
signature. Add-only, remove-only, ownership-rewrite, and exact-baseline proposals
are reported separately.

Because the commitment and ILP stages operate on the pre-pruning relink graph,
a proposal can reference an endpoint removed by V24.2 or V24.3. Such a proposal
is retained with its original class and reported as
`inapplicable_after_pruning`; it is not altered, scored, or included in efficacy
deltas. This is compatibility telemetry, not evidence for restoring a pruned
node.

Before route-90 execution, the first ordered sample must complete the entire
inference, pruning, commitment, ILP, official-scoring, serialization, aggregation,
immutability, and deterministic-replay path under `--preflight-only`. The full
cohort starts only after that one-sample summary passes its fixed checks.

## Frozen Endpoints

Report separately for the regression-16, route-control-74, and complete route-90:

1. commitment-changed and persistent window counts;
2. primary and zero-penalty ownership-rewrite counts;
3. proposal classes and intervention sizes;
4. official adjusted-edge and raw-edge deltas for each proposal;
5. improved, regressed, and neutral proposal counts;
6. solver budget, timeout, infeasible, and error counts;
7. inference and total runtime;
8. deterministic replay and graph-immutability checks.
9. post-pruning inapplicable proposal counts and reasons.

## Interpretation Rules

- If no persistent windows or no ownership rewrites occur, the combined mechanism
  is unsupported on this cohort.
- Persistent-versus-reconverging enrichment is descriptive and must include raw
  denominators; one successful example is insufficient.
- Any contained primary rewrite with a negative official delta blocks promotion.
- Positive zero-penalty results do not authorize lowering the containment penalty.
- Add-only gains do not count as ownership-rewrite evidence.
- No result from this opened-label cohort authorizes a selector or submission.

The next decision after execution is limited to whether the unchanged mechanism
merits a separately designed test on future independent evidence.