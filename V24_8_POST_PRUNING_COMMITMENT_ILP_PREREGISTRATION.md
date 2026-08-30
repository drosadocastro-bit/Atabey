# V24.8 Post-Pruning Commitment plus ILP Preregistration

Date: 2026-08-30

Status: **INDEPENDENT-COHORT INVENTORY COMPLETE; EXECUTION BLOCKED**.

This document fixes the next admissible question after the V24.7 route-90
promotion NO-GO. It does not authorize implementation, execution, threshold
tuning, graph mutation, automatic selection, submission, or deployment.

## Prior Evidence and Failure Mode

V24.7 ran commitment intervention and bounded ILP on the pre-pruning relink graph,
then attempted to score proposals on the pruned V24.3 graph. Across both arms, 612
proposal evaluations were inapplicable after pruning. The contained primary had 9
scoreable ownership rewrites and all were official-metric neutral. The zero-penalty
diagnostic had 3 improved, 38 neutral, and 1 regressed scoreable rewrites.

The next experiment may address only the graph-boundary mismatch. It must not tune
the optimizer to the opened route-90 outcomes or reinterpret V24.7 as evidence of
efficacy.

## Question

When commitment intervention and bounded ILP both operate directly on the frozen
V24.3 post-pruning graph, can they produce internally applicable, bounded ownership
proposals without mutating that graph?

Only a separately frozen independent cohort may answer whether any such proposals
improve official tracking metrics.

## Graph Contract

The candidate graph is constructed in this exact order:

```text
frozen E016 coordinates
-> motion-mutual relinking at 9.0 um
-> V24.2 interior-isolated-node pruning
-> V24.3 interior-short-fragment pruning
-> commitment intervention
-> bounded three-frame ILP shadow
-> proposal on a new graph copy
-> pinned official evaluator
```

The same post-pruning graph instance supplies the commitment baseline, ILP
baseline, proposal endpoint set, and scoring baseline. Pre-pruning triggers may not
be translated, restored, or projected onto this graph.

## Frozen Mechanism

Subject to the eligibility gate below, V24.8 must retain the unchanged V24.7
settings:

- checkpoint SHA-256:
  `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`
- predictor SHA-256:
  `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`
- full sequences; no timepoint cap
- motion-mutual link radius: `9.0 um`
- commitment candidates: at most 64 accepted edges per sample
- commitment horizon: 2 frames
- ILP enrollment: commitment records with at least one changed assignment
- ILP ordering: persistent first, then fixed margin and stable node IDs
- maximum ILP windows: 16 per sample
- primary baseline-change penalty: `2.0 um` per changed edge
- primary minimum improvement: `0.5 um`
- maximum binary variables: 512 per window
- solver time limit: 5 seconds per window
- zero-penalty arm: mechanism diagnostic only

No setting may be selected from V24.7 per-window outcomes.

## Independent-Evidence Eligibility Gate

Execution remains blocked until a separate immutable cohort contract records:

1. sample IDs and a reproducible source manifest;
2. evidence that neither labels nor official per-sample outcomes were used in V24
   development, V24.3 pruning, V24.5-V24.7 analysis, or cohort selection;
3. hashes for the sample manifest, runner, predictor, checkpoint, evaluator pins,
   and this preregistration;
4. a fixed sample count and complete-sequence requirement;
5. enough samples to report raw denominators rather than isolated examples.

The existing 199 labeled samples, including route-90, are opened evidence and are
ineligible for promotion decisions. They may be used only for implementation
tests that assert invariants and must not influence thresholds or gates.

## Required Invariants

Before any independent run, synthetic and opened-data canaries must establish:

- commitment and ILP receive the exact post-pruning graph signature;
- every proposed added and removed edge has endpoints in that graph;
- every removed edge exists and every added edge is absent in the baseline;
- proposals preserve adjacent-frame timing and continuation ownership limits;
- proposal application occurs only on a fresh graph copy;
- source graph signatures are unchanged before and after both shadow stages;
- repeated canary runs are byte-deterministic;
- budget, timeout, infeasible, and error states fail closed.

Any post-pruning inapplicability is an implementation or contract failure, not an
efficacy outcome.

## Frozen Endpoints

Report, with raw denominators:

1. commitment-eligible, changed, persistent, and reconverging window counts;
2. primary and zero-penalty proposal classes;
3. scoreable and inapplicable ownership-rewrite counts and reasons;
4. changed-edge counts and objective improvements;
5. official adjusted-edge and raw-edge deltas for every scoreable rewrite;
6. improved, neutral, and regressed rewrite counts;
7. solver status and variable-budget counts;
8. inference, pruning, shadow, scoring, and total runtimes;
9. deterministic replay and graph-immutability results.

Add-only proposals remain separate and do not count as ownership-rewrite evidence.

## Decision Rules

- Any post-pruning inapplicability blocks promotion and requires implementation
  review without changing the frozen mechanism.
- Any negative contained-primary official delta blocks promotion.
- No positive contained-primary rewrite means the efficacy hypothesis is
  unsupported.
- Positive zero-penalty results do not authorize lowering the change penalty.
- Persistent-versus-reconverging comparisons are descriptive and require raw
  denominators; persistence alone is not an error label.
- A selector requires a separate preregistration and independent evidence.
- V24.3 remains unchanged unless every applicable promotion gate passes.

## Current Decision

The completed
[independent-cohort eligibility audit](V24_8_INDEPENDENT_COHORT_ELIGIBILITY_AUDIT.md)
accounts for all 199 labeled samples and finds zero unopened candidates. The
historical 34-sample internal-validation split is entirely contained within the
checkpoint-training 172 and is not independent evidence. Competition hidden-test
labels and per-sample outcomes are not locally available or auditable.

V24.8 remains authorized only for contract design. Implementation and execution
remain blocked until genuinely new labeled samples can be frozen under an
immutable source manifest satisfying the eligibility gate.