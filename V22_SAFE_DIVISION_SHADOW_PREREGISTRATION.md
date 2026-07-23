# V22 Public Safe-Division Shadow Pre-Registration

Date: 2026-07-23
Status: locked before development-split shadow outcomes

No threshold tuning, learned-model import, production graph mutation, calibration-split inspection, or
locked-validation inspection is authorized by this document.

## Source And Attribution

The hypothesis comes from the public Kaggle notebook:

- `praxel/biohub-0-902-motion-division-calibration`
- https://www.kaggle.com/code/praxel/biohub-0-902-motion-division-calibration

The notebook reports a 0.902 public leaderboard submission and uses a public CC0 support pack:

- `pilkwang/biohub-tracking-support-pack-50ep-v1`
- https://www.kaggle.com/datasets/pilkwang/biohub-tracking-support-pack-50ep-v1

The leaderboard score is a combined competition score, not evidence that the safe-division pass has
positive Division Jaccard by itself. This audit tests the visible post-link rule independently inside
Atabey and makes no claim about the notebook author's private development process.

## Transfer Hypothesis

The notebook separates ordinary continuation from division capacity:

1. create a one-to-one continuation graph;
2. find parents with exactly one next-frame child;
3. consider only next-frame detections with no incoming edge;
4. add a capped second-child edge when parent, existing-child, and sister geometry are conservative.

The transferable hypothesis is narrow:

> Some Atabey divisions that have the required detections but fail official topology may be recovered
> by treating division as a bounded second-child exception after continuation ownership is established.

This is not expected to repair missing detections. In the frozen V21 development audit, the plausible
primary target is the eight `projected_actions_not_official_tp` divisions. The 11 missing-parent and
12 missing-daughter cases are reported as structurally outside this rule's capability.

## Frozen Rule

The shadow reproduces the notebook's visible `add_safe_divisions_postlink()` behavior:

- source parent has exactly one existing outgoing edge;
- existing child is at `t + 1`;
- candidate child is at `t + 1` and has no incoming edge;
- candidate parent distance is at most **4.66 um**;
- existing parent-child distance is at most **7.65 um**;
- existing-child/candidate sister distance is at most **8.5 um**;
- proposal score is `parent_distance + 0.15 * sister_distance`;
- proposals are ordered by score, with stable node-ID tie handling;
- each candidate child may be claimed once;
- per-frame additions are capped at `max(1, round(source_count * 0.0076))`;
- global additions are capped at `max(1, round(edge_count * 0.00375))`;
- the global cap is checked before the frame cap, matching the public source.

The public notebook disables its DeepCenter veto in the scored preset, so the Atabey shadow does not
add an image-based veto. It also does not import the notebook's U-Net, transformer, ILP, motion
relinker, gap repair, smoothing, or short-track filtering.

## Cohort

Only the frozen 27-sample V21 development split is eligible. It contains 46 known GT divisions.

The following remain unopened and unused:

- the 27-sample calibration split;
- the locked 20-sample independent validation cohort.

A one-sample smoke may be run only to verify execution and serialization. It does not authorize
threshold changes.

## Measurements

For every development sample:

1. rebuild the frozen V19 pre-firewall graph and record its actual detector/link route;
2. compute the shadow proposals without changing the source graph;
3. project only budget-selected edges onto a graph copy;
4. score baseline and projected graphs with the pinned patched official tracking evaluator;
5. recompute per-GT positive availability on baseline and projected graph copies;
6. report proposal count, selected count, official division TP/FP/FN, Division Jaccard, official
   adjusted edge Jaccard, and source zero perturbation;
7. report per-sample improved/flat/regressed breakdowns;
8. keep raw geometric proposal counts separate from official FP labels.

The audit must reproduce the frozen V21 development accounting before interpretation:

- 13 baseline official-positive availability cases;
- 8 baseline `projected_actions_not_official_tp` cases.

## GO Rules

The frozen rule is a GO only for a later, separate confirmatory shadow if all hold:

1. all 27 samples and 46 GT divisions complete;
2. all source graphs pass zero perturbation;
3. all 13 baseline available positives remain available;
4. at least one new actual patched-official division TP is recovered;
5. aggregate official adjusted edge Jaccard does not decrease;
6. official division FP increases by no more than the number of new official TPs;
7. no GO claim depends on raw proposal counts or sparse unsupported regions.

A GO does not authorize production integration. It permits only a separately preregistered
confirmatory shadow.

The result is a NO-GO if it adds no official TP, loses an available positive, regresses aggregate
official adjusted edge Jaccard, or reopens division FP beyond the locked bound.

## Guardrails

- No threshold or cap changes after outcomes are opened.
- No calibration or validation sample may be substituted into development.
- No U-Net or transformer model is imported during this audit.
- No raw eligible proposal is called a TP or FP without the patched official scorer.
- No source graph, V19 path, Track A, Track B, or submission path is mutated.
- The 4.66/7.65/8.5 um constants are tested as published, not claimed as biologically universal.
- A negative result does not test the public notebook's complete learned pipeline; it tests only this
  visible post-link rule on Atabey's existing detections and continuations.

## Decision State

The shadow implementation and tests may be committed before outcomes. The next permitted action is a
bounded smoke followed by the complete development-only run with the rule unchanged.
