# V30: saved-coordinate diagnostic of V29A regressions

Status: **PROPOSED — methodology review; implementation pending; execution not authorized.**

Danny accepted preparation of the proposed diagnostic. This document defines a
new exploratory analysis after V29A outcomes were opened. It is not a retrospective
amendment to V29A. Builder: Codex. Reviewer and execution authority: Danny.

## Question and claim boundary

Where do the two saved detection outputs differ geometrically, how do those
differences accompany changes in recursive linking, and which differences survive
or arise during pruning? Which existing official metric components accompany the
observed sample losses?

V29A improved the local aggregate from 0.721055749 to 0.735927590 but failed its
individual-loss and protected-case gates. V28 remains the submitted reference;
V29A remains NO_GO. Neither result establishes V28's performance ceiling.

This diagnostic can locate structural changes and generate hypotheses. It cannot
attribute a fraction of score loss causally to detection, ranking, history or
pruning. A later intervention requires its own contract. Saved peak coordinates
cannot reconstruct the logits, suppressed peaks or causes of detection changes.

## Inputs, cohort and authority

The machine-readable proposal is `v30_diagnostic_proposal_20260928.json`.
Its input inventory records raw SHA-256 identities for all 398 coordinate arrays,
398 inference records, the frozen result, inference summary, parent manifests,
source bundle and review documents. Source and runtime identities are pinned.

Use all 199 paired samples in lexical sample-ID order. Retain the five original
V29A strata and their exact memberships. Additionally report the two frozen-route
groups: pruning enabled and pruning disabled. Groups overlap; never sum them as
independent observations. There is no new holdout.

Detailed focus comprises all 25 samples with the already published score delta
strictly below -0.020, plus all four protected IDs. Freeze the explicit lists from
the existing result before implementation. This is outcome-selected exploration,
not prospective confirmation. Report every sample, including improvements.

Allowed during preparation: read-only identity checks, enumeration of previously
published metrics and memberships, and creation of this review package.
No graph reconstruction or new coordinate comparison has been performed for V30.

Future execution is one CPU-only diagnostic pass from saved coordinates, with a
two-hour wall limit including preflight, a single sample pair resident at a time,
and frame-local geometric comparisons. No inference, GPU, raw-image access,
checkpoint loading, new GT scoring, parameter sweep, hybrid sample selector,
competition submission or selection change. No commit or push is implied.

## Preflight and faithful stage reconstruction

Before any diagnostic output, verify the complete input inventory, both release
freezes, normalized scientific-source parity with the V29A bundle, and pinned
Python/numpy/scipy runtime. Reject missing, changed or unexpected cohort inputs.
Use `numpy.load(..., allow_pickle=False)` and validate finite N-by-4 `[t,z,y,x]`
arrays, integral nonnegative time, original time order and in-bounds positions
against the frozen shape. Never sort or deduplicate coordinates before replay.
Do not reinterpret row IDs shared across branches as shared detections.

For each arm, use the existing implementations, unchanged:

1. RAW: `relink_predictor_detections` with motion-mutual linking and 9 microns.
2. P2: `prune_interior_isolated_detections(RAW)` only if the frozen route permits.
3. P3: `prune_interior_short_fragments(P2)` under the same route; this is FINAL.

For disabled routes, P2 and P3 are explicitly BYPASSED and equal RAW; hypothetical
pruning is out of scope. Preserve original node/edge order and confidence values.
Record stage signatures, node/edge counts and each node's first removal stage.
Verify RAW counts and FINAL signature/counts/export-row hash against each saved
record. A mismatch stops the run and preserves partial evidence; do not repair the
linker or relabel a mismatch as a new result. Route decisions come from frozen
records, not a new image profile.

The source selects a forward nearest target to the predicted position, then
checks prediction error and physical step, applies reverse physical-nearest
mutuality, and greedily assigns candidates. Its original ordering, SciPy tie
behavior and branch-local predecessor updates remain operative. Do not prefilter
feasible targets, change tie breaks, reorder candidates or exchange histories.
Stage reconstruction exposes downstream effects; it does not isolate these rules.

## Coordinate correspondence: geometry, not cell identity

All comparisons are within the same sample and timepoint. Distances use physical
`(z,y,x)` scales `(1.625, 0.40625, 0.40625)` microns and float64 arithmetic.

The primary correspondence is an EXACT anchor: numerically identical `[t,z,y,x]`
values occurring exactly once in each arm. No rounding or coordinate tolerance.
Duplicate coordinate keys in either arm are reported as DUPLICATE_AMBIGUOUS and
excluded from all one-to-one correspondences, even if multiplicities agree.

A secondary, separately reported geometric context uses radius **2.0 microns**.
This is a chosen descriptive resolution, not the official GT radius, a biological
identity criterion or a parameter to optimize after opening V30 results.
On all unique-coordinate nodes in both arms, build the full frame-local bipartite
neighborhood with squared physical distance <= 4.0, including exact anchors.
Accept a non-exact NEAR_ISOLATED pair only when both endpoints have degree one
and neither is already exact-anchored. Compute degrees once, with no iterative
removal or rematching. Exact anchors stay exact even in a crowded neighborhood.

Remaining unique nodes have NO_NEAR_COUNTERPART if their degree is zero, or
NEAR_AMBIGUOUS otherwise (including proximity to an already exact-anchored node).
These labels describe coordinates only; do not rename them missed or false cells.
No nearest-neighbor tie resolution, minimum-cost assignment or GT matching is
used to force cross-arm correspondence. Duplicate nodes are excluded from degree
construction; report their counts alongside the coverage limitation.

Per arm/frame, the five disjoint node labels must sum to RAW node count: EXACT,
NEAR_ISOLATED, NO_NEAR_COUNTERPART, NEAR_AMBIGUOUS, DUPLICATE_AMBIGUOUS.
Report count, denominator and fraction, plus displacement distances for accepted
near pairs (count, min, median, max; empty statistics null). The correspondence
map is built on RAW coordinates once and carried unchanged through later stages.

## Links, history and pruning

Produce two explicitly separate views: primary EXACT-only and supplementary
EXACT-plus-NEAR_ISOLATED. Never pool their denominators or label the second an
identity-validated association comparison.

At each stage, partition each arm's edges into both endpoints mapped versus one
or both endpoints unmapped. Within the mapped subset, compare directed endpoint
pairs in the shared correspondence space: common, baseline-only and TTA-only.
For common pairs, report relation changes and confidence-only changes separately;
confidence equality is exact, with maximum absolute difference also recorded.
Verify both arm edge totals from this partition. Equal totals alone are not parity.

For each mapped RAW source, classify outgoing state into: same mapped successor,
different mapped successor, baseline-only outgoing, TTA-only outgoing, neither,
or UNRESOLVED if an existing outgoing endpoint is unmapped. Unexpected branching
is a validity failure for this fixed continuation linker. Node removals in later
stages are not counted as fresh RAW association decisions.

Describe immediate incoming history independently: both absent, same mapped
predecessor, different mapped predecessor, one absent, or unresolved. For recursive
history, compare the complete incoming chain from the source backwards using
mapped identities, with no truncation: SAME_CHAIN, DIFFERENT_CHAIN, or UNRESOLVED
when a necessary predecessor is unmapped. Preserve arm-specific depth and use a
memoized representation to avoid repeatedly materializing long chains. A confirmed
mapped mismatch establishes DIFFERENT_CHAIN; otherwise an unresolvable comparison
stays UNRESOLVED. Equal histories do not imply equal candidate populations.

Cross-tabulate outgoing categories by immediate/recursive history status. Do not
call any category ranking-caused, tie-caused or history-caused. Exact forward/reverse
tie exposure, candidate eligibility and order-sensitive causal witnesses require
a later trace contract; they are explicitly UNMEASURED here.

For each mapped node pair, cross-tabulate first removal stage (P2, P3, SURVIVES)
between arms. Include unmapped-node removal counts separately. Each branch's stage
differences must reconcile with removed node/edge IDs. A final difference on a
pruning-disabled sample cannot be attributed to executed pruning. P2/P3 effects
on changed graph topology remain descriptive, not standalone pruning treatments.

## Existing official metrics, without rescoring

Join unchanged official per-sample V29A records by sample ID. Display baseline,
TTA and delta for score, adjusted edge Jaccard, edge Jaccard, edge TP/FP/FN,
predicted nodes, estimated total nodes, total-node ratio, node recall, and division
TP/FP/FN/Jaccard. Preserve nulls and the original aggregate records; never replace
the official aggregate by the mean of sample scores.

Distinguish changes in edge Jaccard from changes in its node-count adjustment.
Show the descriptive residual `adjusted_edge_jaccard - edge_jaccard` in each arm
and its delta. This is arithmetic on opened metrics, not a causal decomposition
or a new metric. Preserve the official division component and null handling.
No new GT matching or stage-specific official scores are authorized by V30.

Both prior arms had zero division true positives and 151 false negatives. Division
recovery is a separate hypothesis; this analysis neither implements nor validates it.

## Output, validity and stop rules

Write into a new, exclusive run directory. Never overwrite prior artifacts.
Record approved contract/implementation/input hashes, runtime, timestamps and
completed sample IDs. Save per-sample stage/correspondence/link/history/pruning
tables and the copied official metrics; retain enough row IDs and coordinates to
audit classifications. Summary contains all 199 sample rows and each declared
group. Provide detailed tables for the frozen focus union and a concise report.

Completion requires all 398 final graph and export parities, complete coverage,
all node/edge/stage accounting identities, and unchanged input hashes at closure.
Status is COMPLETE_DESCRIPTIVE_DIAGNOSTIC, never GO or quality-improved.
Hash/parity/invariant failures produce INVALID_INCOMPLETE; budget exhaustion
produces BUDGET_EXHAUSTED_INCOMPLETE. Preserve the first failure and completed
rows; do not silently omit samples, retry, relax limits or promote partial results.

The report must distinguish observed structural differences, their co-occurrence
with opened score losses, and unmeasured causal mechanisms. If correspondence
coverage is weak, report that limitation instead of expanding the radius. No
minimum favorable effect size or outcome is required for a valid diagnostic.

## Implementation review before freeze

No diagnostic runner is supplied or approved by this proposal. The next step is
to implement this contract in an additive diagnostic script using existing graph
functions, then review the exact script and tests with Danny before freezing and
executing one pass. Do not alter frozen V28/V29A modules or release files.

Required synthetic checks cover duplicate coordinates; crowded exact anchors;
2.0-micron boundary and just-outside pairs; ambiguous chains without iterative
rematching; anisotropic axes; unchanged/changed/unmapped successors; confidence
changes without endpoint changes; recursive unresolved history; route bypass;
P2 versus P3 removal; missing frames; and fail-closed identity/parity/accounting
checks. Synthetic fixtures are instrumentation checks, not biological evidence.

The future execution receipt must bind the final contract, implementation/tests,
input inventory and Danny's explicit execution approval. Implementation changes
to these definitions require a visible contract revision before execution.
