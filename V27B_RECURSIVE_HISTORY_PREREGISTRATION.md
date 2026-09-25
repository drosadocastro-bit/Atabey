# V27B: recursive history and pruning response

Date: 2026-09-24

Status: **PROPOSED; NOT IMPLEMENTED; NOT FROZEN; NOT EXECUTED**.

Danny requested V27B with its own contract after reviewing V27A.1. This document
defines that next experiment. Preparation is authorized; the implementation,
review and exact-payload execution records are still absent. V27A.1 authorization
does not authorize a different payload. Machine specification:
[v27b_recursive_history.json](tests/fixtures/v27b_recursive_history.json).

## Question and scope

For each of the five prespecified association rules, how do decisions change
when its own accepted links supply subsequent predecessors? How do those raw
changes affect the outputs of the unchanged V24.2 and V24.3 pruning functions?

V27B covers **recursive linking and pruning response** on the same opened
16-sample cohort. New official correspondence, rematching and scoring are excluded
and require a subsequent contract. Keeping that boundary explicit separates
graph construction, graph filtering and evaluation semantics. Neither extra
links nor retained nodes establish improved tracking quality.

V27A.1 observed order/ranking interaction and tie-mediated eligibility differences.
Those findings motivate this design but do not select an arm, threshold, sample
or stopping rule. All five arms and all 16 samples are mandatory. This is
retrospective mechanism evidence, not independent validation. V24.3 remains the
reference, V26A remains NO_GO and the original V27A run remains INVALID_EXECUTION.

## Fixed rules and two history regimes

| Arm | Order | Ranking | Forward ties |
|---|---|---|---|
| H | Exact historical select-then-gate | Motion error | Existing pinned cKDTree |
| M0 | Select, then gate | Motion error | First original target index |
| M1 | Filter, then select | Motion error | First original target index |
| S0 | Select, then gate | Physical step | First original target index |
| S1 | Filter, then select | Physical step | First original target index |

**F (frozen history)** is the existing V27A.1 decision record for each arm, using
V25 baseline predecessors. Recompute and compare every scientific frame record
with the pinned V27A.1 first pass before using it as a reference. Preserve the
original annotations, failures and archived membership semantics. F decisions
remain a local reference: do not assemble, prune or score an F alternative graph.

**R (recursive history)** builds one new raw graph per arm over exactly the same
immutable detections, node IDs, physical coordinates, sample/frame membership and
original within-frame order. Start each arm with no predecessors in the first
frame. Advance through every integer timepoint, including empty frames. For the
transition t → t+1, only that arm's finally accepted t-1 → t edges may supply
predecessors. Process the entire transition before updating the map for t+1.
Discard unaccepted/expired history; never seed later frames from H or another arm.
An empty frame interrupts adjacent linking. There is no gap bridge, division,
latent state, new detection, interpolation or candidate expansion.

Prediction remains `source + (source - predecessor)`, or the source position
when no predecessor exists. Prediction error and physical step must both be
finite and <= 9 microns. Select-then-gate abstains when its selected candidate
fails; it never tries a second candidate. Filter-then-select ranks only feasible
candidates. Exact ties use no epsilon, rounding, jitter or candidate renumbering.

Reverse ownership remains raw physical nearest neighbor under the pinned cKDTree
and inclusive 9-micron gate. The existing stable greedy assignment consumes
prediction error with original source order for equal errors. Edge confidence
remains `max(0, 1 - prediction_error / 9)`; relation and edge serialization remain
those of the historical linker. Retain every raw detection even if it has no link.

The decision functions and constants are common; prediction tables need not be
equal across R arms once their histories diverge. Physical-step tables, detection
order and reverse ownership must remain equal. S0's selected target, before its
gates, must match F_S0 because its selection has no history-dependent input.

## Validate ties on the same history

Reuse the unchanged V27A.1 frame observer on each arm's own immutable predecessor
map. Its five decisions are validation probes on that common context; **only the
active arm's accepted edges propagate**. Probe results must identify the history
owner and must not enter primary counts as additional trajectories or replicates.

The candidate-wise V27A.1 amendment still applies within each common-context
probe: preserve original failure dispositions; allow only proven exact tied
motion minima with correctly evaluated candidate predicates. Numerical, anchor,
confidence or other unexplained discrepancies remain hard failures.

Do not apply a tie-only equality requirement directly to R_H versus R_M0 after
their histories diverge. That contrast measures the total downstream effect of
changing the forward tie policy, including induced history changes. A later
non-tied difference across those different contexts is not automatically an
implementation failure. Conversely, probes on an identical full frame context
must agree exactly, including confidence and greedy acceptance.

## Prespecified comparisons and units

For every `(sample_id, source_t, source_id)` before the final frame:

1. Compare R_a with F_a for each a in H, M0, M1, S0, S1. Record both predecessor
   IDs, predictions, selected/gate-eligible/accepted targets, confidence, reasons,
   distance tables, exact ties and raw edge identities.
2. Repeat the five V27A.1 paired contrasts separately in F and R: M0 → M1,
   S0 → S1, M0 → S0, M1 → S1 and H → M0. R contrasts are total dynamic policy
   effects; F contrasts hold baseline history fixed.
3. Classify accepted outcomes as SAME, GAIN, LOSS or SWITCH. SAME includes two
   abstentions; separately flag confidence changes when an accepted target is
   unchanged. A SWITCH removes one edge and adds one, but changes one source
   outcome. Report identities as well as counts.
4. Record predecessor-ID and predicted-position equality separately. Different
   predecessor identities may have identical coordinates. Record first history,
   selection and acceptance divergence per sample/arm, using null if absent.
   These are chronology diagnostics, not an inferred unique biological cause.

For the accepted-edge indicator Y, report each regime's per-source interaction
`I_q = (Y_q,S1 - Y_q,S0) - (Y_q,M1 - Y_q,M0)` and `I_R - I_F`.
Preserve the full integer distribution, including zero and any +/-2 values.
For each before/after pair b,a, report the accounting identity
`delta_R(a,b) - delta_F(a,b) = (Y_R,a - Y_F,a) - (Y_R,b - Y_F,b)`.
This identity describes history sensitivity; it is not an additive biological
mediation model or a unique attribution of each changed edge.

Report per-sample tables and full-cohort sums, with denominators. Source/frame
counts are dependent observations. No hypothesis tests, confidence intervals,
pooled independent-trial interpretation, winner ranking or efficacy thresholds
are introduced. Retain complete F target tuples and all R target tuples so that
equal net link counts cannot conceal replacements.

## Pruning is downstream and cannot feed history

For each completed R graph, independently retain three immutable stages:

1. RAW: complete recursive graph with all original detections.
2. P2: `prune_interior_isolated_detections(RAW)` with unchanged code/defaults.
3. P3: `prune_interior_short_fragments(P2)` with unchanged code/defaults,
   including `MAX_COMPONENT_SIZE = 2`.

This yields **240 graph-stage artifacts**: 16 samples × 5 arms × 3 stages.
P2/P3 are post-sequence transformations; they never alter R linking inputs,
predictions, predecessor maps or the original F reference.

Save node/edge sets and confidence-aware signatures at every stage. Record the
exact removed node/edge identities for RAW → P2 and P2 → P3. Require subset
preservation: pruning cannot create a node or edge, modify a retained coordinate,
confidence or relation, or mutate its input graph. Report the same five arm
contrasts at each stage. For each raw added/removed edge relative to the paired
arm, retain its endpoint and edge survival through P2/P3, including cases where
an edge present in both RAW graphs survives in only one final graph.

Different pruning outputs under identical code are a response to different
input graphs. Do not label them a changed pruning algorithm, or conflate them
with direct raw association changes or newly credited/unmatched edges.

## Required anchors and execution validity

- Verify all parent payload source identities and input artifacts before and
  after execution, including all 50 V27A.1 raw files in its pinned inventory.
- Reproduce the 16 F streams exactly: 99,167 sources, 86,778 H links, 229 exposed
  decisions, 200 exposed S1 acceptances and the stored full count dictionary.
  The 20 tie/eligibility cases are reference integrity checks, not R targets.
- R_H must equal the archived historical raw graph, edge confidences and F_H
  decisions throughout; H's P2/P3 must reproduce all 48 historical signatures.
- R_S1 must match the unchanged `relink_detections_step_ranked` executable on
  the same detections, and its P3 signature must equal the archived V26A
  ablation signature for each sample. No old metric is reinterpreted or rescored.
- All R arms must equal their F arm at the initial transition with empty
  predecessor maps. Every later predecessor must be witnessed by that arm's
  accepted immediately previous edge; duplicate parents/targets are invalid.
- Every common-context V27A.1 probe must pass its amended checks. Detection and
  input signatures must remain unchanged. Validate pruning subset/copy invariants.
- Run two complete scientific passes, resetting all arm state for every sample
  and pass. Require exact decision, graph, ledger and aggregate digests. Exclude
  only separately stored timing/memory telemetry from scientific digests.
- Require complete cohort, all five R graphs and all three stages per sample.
  Never skip an arm, omit a failing sample or silently continue with fewer data.

Use **VALID_RECURSIVE_MECHANISM_RESULT** only after all checks pass. On failure,
persist the failing context and partial evidence, stop with **INVALID_EXECUTION**
and retain the failed directory. No silent retries, resumption into that directory,
threshold adjustment or post-observation relaxation of checks. A corrected attempt
requires a separately identified reviewed payload and new output directory.

## Implementation, review and freeze requirements

Extend the existing audit machinery with a bounded shadow orchestrator; preserve
the frozen V27A/V27A.1 modules and their artifacts. Do not add a production linker
strategy or alter the baseline submission path. Stream one frame context at a
time and retain only bounded predecessor state plus graph records needed by the
existing post-sequence pruning code. No image volumes are loaded.

Before any cohort execution, tests must demonstrate a multi-frame case where
own-history decisions diverge from frozen-history decisions, isolation between
arms/passes, empty-frame reset, initial-history equality, confidence-only changes,
stable target ordering, pruning non-feedback, and exact H/S1 executable anchors.
Include the known exact-tie gate witness as a regression, explicitly not independent
evidence; include synthetic later non-tied divergence after a tie-mediated history
change so that the common-context validity check cannot be misapplied globally.

The new manifest must pin this protocol, machine contract, complete implementation
and imported source closure, tests/results, all input container identities,
V27A.1 approval/result/streams, and the exact Python/package runtime. Runtime here
is an observed reference, not a V27B lock. Proposal/review/null authorization must
be rejected by the eventual execution entry point. Required final records identify
the builder, a distinct reviewer, and human authorization of the exact new payload.
The machine proposal's null fields are intentional, not an executable freeze.

## Required deliverables and limits

Produce a freeze copy, two deterministic scientific passes, per-frame contexts
with history-owner labels, per-source F/R comparisons, exact divergence witnesses,
all graph stages, pruning survival ledgers, per-sample/full-cohort summaries,
failure dispositions, runtime/resource telemetry and a byte/hash inventory.
Keep probe counts separate from the 99,167 primary source observations per regime.
Preserve the old run's failures rather than rewriting them as successful runs.

No ground-truth rematching, official scoring, training, inference, tuning,
production promotion or Kaggle submission is authorized by this proposal. A
subsequent evaluation contract must specify metric/runtime/data identities and
fresh stage-specific matching; historical mapping membership cannot substitute
for that evaluation. Results from this opened cohort cannot release V24.8's
independent-data block. A valid null or adverse mechanism result completes V27B
just as fully as a result with more accepted links.
