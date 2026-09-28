# V27C: official evaluation of frozen recursive-history graphs

Date: 2026-09-27

Status: **PROPOSED — NOT FROZEN; NO COHORT MATCHING OR SCORING EXECUTED**.

## Question and evidence boundary

On the 16 already opened V27B samples, how do operation order, ranking and
recursive history affect official credit, evaluable errors and metrics, and how
does unchanged pruning alter those differences? V27C evaluates the saved V27B
graphs. It does not rerun linking, pruning, inference or model training.

V27A.1 established fixed-history decision differences; V27B established recursive
graph differences. Neither establishes tracking quality. V27C is retrospective,
descriptive evaluation of this selected cohort, not independent validation or a
Kaggle leaderboard result. Sparse annotations are not exhaustive biological truth.
V26A's historical NO_GO and V24.8's independent-data block remain in force.

## Fixed matrix and identities

The machine contract is `tests/fixtures/v27c_official_graph_evaluation.json`.
It names the same ordered 16 sample IDs, five recursive arms H/M0/M1/S0/S1 and
three stages RAW/P2/P3: **240 distinct graph evaluations per pass**. F has no
saved alternative graph and is not an evaluation arm. No sample, arm or stage
may be selected or dropped based on observed metrics.

Use first-pass V27B graph files as inputs. Before evaluation, verify all 480
physical graph copies against the V27B inventory and require each pass pair's
bytes and full ordered graph digest to agree. Require the 32 parent sample-pass
summaries, parent inventory, parent approved freeze and parent machine result
to match their pinned identities. Preserve node/edge order, IDs, positions,
confidence and every saved attribute when decoding. Invalid endpoints,
duplicates, nonfinite coordinates, nonadjacent edges or changed sample IDs are
blocking errors; do not silently sanitize input for the evaluator.

The 16 `train/{sample_id}.geff` directories are pinned by every relative file
path, size and raw SHA-256, including metadata and chunks. A tree digest is the
SHA-256 of the sorted file-record list serialized as UTF-8 JSON with sorted
keys, separators `(',', ':')`, and no nonfinite numbers. Missing or extra files
invalidate the tree. Metadata supplies the fixed positive estimated node count;
do not replace it with annotated-node counts or a fitted estimate. These are
current local input identities, not a claim that historical runs recorded the
same raw GEFF identities.

Read only these sparse GEFF graphs, one sample at a time. Image volumes and model
weights are unnecessary. The proposal pins existing source identities and the
observed local runtime; the execution freeze must additionally pin the complete
new implementation, transitive imports, tests, passing test evidence and runtime.

## Official evaluator and fresh matching

Use the existing pinned host implementation:

- `tracking-cellmot` commit `075fc5f5a52d11077f9dc2b074644618f26939e2`;
- `tracksdata` commit `39dccf3a243e44274759468cb31b2ad9e7fc1d09`;
- `tracking_cellmot.metrics.evaluate`, `per_sample_metrics`, `node_recall` and
  `summarise`, with the host division evaluator unchanged;
- physical `(z,y,x)` microns, `scale=None`, maximum matching distance **7.0 um**.

The tracking gates were 9 um; they are not evaluator matching thresholds. GEFF
coordinates use the existing reader and `(1.625, 0.40625, 0.40625)` um voxel scale
exactly once. Check GEFF metadata against these conventions. The pinned host
owns matching boundary/tie behavior; do not substitute a local nearest-neighbor
matcher, reorder nodes, repair duplicates or modify its scoring rules.

For every sample/arm/stage/pass, create fresh prediction and GT host graphs.
Invoke `evaluate` once and retain that evaluation's node mapping and post-filter
edge table from `_evaluate_matched_graph`. Derive metrics and ledgers from that
same matched state. Do not independently rematch just to construct a ledger.
The host's internal division matching on copies remains part of the pinned
evaluator. Preserve its warnings and matching/filtering effects as evidence.

The existing Atabey tracking adapter is a reference for metric semantics. The
existing association-correspondence adapter does not expose `pred_valid`; its
unmatched-edge list alone cannot implement this contract. Add bounded evaluation
instrumentation without editing parent-frozen modules. Validate parity with the
existing adapter on synthetic graphs before cohort execution.

## Endpoints and aggregation

The primary diagnostic endpoint is **official adjusted edge Jaccard**, reported
for every sample and every arm/stage, with paired deltas. Also report official
edge TP/FP/FN and edge Jaccard, node recall, predicted/estimated node counts,
total-node ratio, division TP/FP/FN and division Jaccard, and combined score.
All stages are mandatory; P3 describes the final saved graph and RAW/P2 explain
stage changes. There is no winner selection or research-interest threshold.

Use `summarise` separately for each of the 15 arm/stage cells, preserving host
count pooling and adjusted-Jaccard denominator weighting. A cohort contrast is
the difference of those host summaries, not an unlabelled mean of sample deltas.
Retain each sample delta and each denominator; show minimum/maximum sample
changes so aggregate gains cannot conceal losses. No p-values, bootstrap,
independent-trial claims, per-sample arm routing or post hoc objective selection.

Do not clip adjusted Jaccard to one: the pinned host can exceed one when the
predicted count is below the estimate. Do not fabricate zero for undefined
metrics. Encode undefined values as null with their reason and denominator.
Require all 16 successful rows per cell. An undefined edge/adjusted metric or
invalid node estimate prevents a complete primary result; record it and stop.
An undefined division Jaccard from a zero division denominator is allowed;
preserve the host's documented omission of that term from score. No silent
failed-row exclusion by `summarise` is permitted.

## Comparisons fixed before evaluation

At each stage, report H -> M0 (tie policy plus induced history), M0 -> M1
(operation order under motion ranking), S0 -> S1 (order under physical-step
ranking), M0 -> S0 (ranking with selection first), and M1 -> S1 (ranking with
filtering first). Additionally report H -> M1, H -> S0 and H -> S1 as descriptive
baseline contrasts, keeping H -> M0 only once. None is a history-controlled
direct effect: these R graphs include the histories induced by their policies.

For each arm, report RAW -> P2, P2 -> P3 and RAW -> P3 with fresh stage matching.
For every numeric metric Y, report the descriptive interaction
`(Y[S1] - Y[S0]) - (Y[M1] - Y[M0])` at each stage. Propagate null operands.
Metric nonlinearity, changed denominators and rematching prevent interpreting
this arithmetic as additive biological causal effects.

## Credit, error and pruning ledgers

Keep two namespaces: prediction edges `(sample, source_id, target_id)` and GT
edges `(sample, gt_source_id, gt_target_id)`. Never compare host-internal numeric
IDs across evaluations. Include node mappings and mapping changes for shared
prediction IDs, plus confidence-only changes, separately from topology changes.

Partition every saved prediction edge into exactly one of:

1. `OFFICIAL_TP`: retained by the host edge table and matched to a GT edge;
2. `OFFICIAL_FP`: retained, `pred_valid=True`, and not matched;
3. `UNEVALUATED_BY_SPARSE_GT`: retained, `pred_valid=False`, and not matched;
4. `FILTERED_BY_HOST`: absent from the host's post-filter edge table.

Record original endpoints, mapped GT endpoints when available, matched mask,
`pred_valid`, host edge ID, table membership and captured warnings. Do not invent
a specific filtering reason when the host does not expose one. Category 3 can
still affect the node-count adjustment; it is not proof of correctness. Category
4 is not automatically FP. A matched edge with `pred_valid=False` is invalid.
Counts of categories 1/2 must equal host TP/FP. Credited GT edge IDs must be
unique and valid; their complement in GT must account for host FN.

For every paired contrast, save gained/lost/shared credited GT edge sets and a
prediction-edge union ledger. Include `ABSENT` on the missing side and the four
categories on each present side. Report transitions, changes in endpoint
mapping, and newly penalized/relieved FP separately from edges physically
added/removed. Require all set identities and TP/FP/FN differences to reconcile.

For pruning comparisons, distinguish deleted edges, deleted endpoints and
surviving edges whose mapping or evaluability changes. Reconcile saved graph
subset/attribute invariants. A gained GT credit after pruning need not be a new
prediction edge. The ledgers describe joint graph-and-matching changes; they do
not causally apportion node removal, rematching and node-count adjustment.
No reuse of V25/V26 correspondence membership or original loss buckets as new
credit. No new V19 evaluation or V26A interest-gate recalculation is included.

## Integrity, anchors and failure policy

Run two complete evaluation passes from fresh host graphs, with the same fixed
sample/arm/stage order. Require exact canonical scientific digests of metric
rows, mappings, edge categories, paired ledgers and aggregate summaries. Sort
output records by stable external IDs; never reorder evaluator inputs. Exclude
only recorded timing, process paths and memory telemetry from scientific digests.

Require all 240 graph identities and the parent's 48 historical H stage
signatures and 16 S1 P3 signatures. For H/P3 and S1/P3, compare fresh per-sample
metrics and the two cohort summaries with archived V26A baseline/ablation
metrics. Integers and null masks must agree exactly; historical finite floats
use absolute tolerance 1e-12 and zero relative tolerance. The two new passes
still require exact digests. These are reproducibility anchors, not fresh
validation evidence. An anchor mismatch stops the run with preserved context;
it must not be explained away by silently changing runtime, GT, matching or
tolerance. Diagnose separately before any amended attempt.

Before matching, fail on any input/source/runtime identity discrepancy. During
execution, fail on any missing cell, graph mutation, ledger inconsistency,
nonfinite primary endpoint, unaccounted host-filter drop, anchor mismatch or
nondeterministic replay.
Retain warnings even when nonfatal. Write **INVALID_EXECUTION** with completed
cells, last attempted cell, failure context and partial artifact inventory.
Never silently retry, overwrite, resume into the same directory or omit a cell.

Use **VALID_RETROSPECTIVE_EVALUATION_RESULT** only when every completeness,
identity, anchor, reconciliation and replay check passes. A null or adverse
effect completes the experiment equally well; validity is not improvement.

## Implementation, review and authorization

The implementation must test fresh-state isolation across arms/stages/passes;
physical-unit conversion; host boundary/tie behavior; out-of-region unmatched
edges versus official FP; filtered-edge handling; null division/primary metrics;
host summary weighting; pruning-induced mapping/category changes; exact replay;
input mutation detection; and rejection of absent, wrong-scope or stale approval.
Use explicit synthetic graphs and fakes only in tests; do not use the opened
cohort to tune or repair the design. Test success is implementation evidence,
not evidence of tracking quality.

Prepare an implementation review and candidate manifest before execution. Pin
this protocol, machine contract, input inventories, full source closure, host
source-file hashes, package versions/VCS provenance, passing tests and runtime.
Require a reviewer distinct from the builder and human authorization of that
exact new payload and V27C scope. Parent approval cannot authorize V27C.
The proposal's null review/authorization fields are intentionally non-executable.

Outputs must include freeze copy, input checks, both complete evaluation passes,
per-cell metrics/mappings/categories/warnings, paired and pruning ledgers,
15 host summaries, per-sample effects, anchor checks, resource telemetry,
machine result, human-readable report and byte/hash inventory. Full local inputs
remain required for reproduction; publish neither competition volumes nor a
claim of self-contained replay from Git alone.

Training, inference, tracker or pruning changes, threshold search, production
promotion, submission generation and independent-validation claims are outside
V27C. This proposal records a design for review, not execution authorization.
