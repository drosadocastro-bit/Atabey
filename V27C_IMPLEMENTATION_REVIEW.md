# V27C implementation review

Date: 2026-09-27

Status: **IMPLEMENTED AND SYNTHETICALLY VALIDATED — AWAITING HUMAN REVIEW OF
THE EXACT CANDIDATE; NOT FROZEN OR EXECUTED ON THE COHORT**.

Builder: Codex. Reviewer and execution authority are intentionally unset in the
candidate. This is builder verification, not independent scientific review.

## Implemented behavior

[The instrument](src/atabey/evaluation/frozen_graph_audit.py) creates fresh host
graphs and calls the pinned official evaluator once per cell. Metrics, node
correspondence and the host-filtered edge table come from that same matched
state. It preserves warnings, undefined-value reasons and metric denominators.
The host's internal division matching is unchanged.

Every input prediction edge is accounted for as official TP, official FP,
unevaluated by sparse GT, or filtered by the host. The instrument reconciles
TP/FP with host counts and credited/missed GT edges with FN. Pair ledgers retain
prediction-edge unions, gained/lost/shared GT credits, node remapping,
confidence-only changes and pruning survival. Confidence remains an algorithmic
attribute, not a probability of biological identity.

[The runner](scripts/run_v27c_official_graph_evaluation.py) reads saved V27B
graphs and sparse GEFF labels. It does not call tracking, inference or pruning.
Both full evaluation passes follow the specified sample/arm/stage order.
Per-cell and complete-pass scientific digests must agree exactly. Historical
H/P3 and S1/P3 metric anchors use the contract's exact integer/null rules and
absolute finite-float tolerance of 1e-12.

The runner produces 15 host summaries, all eight stage-specific arm contrasts,
three pruning contrasts for each arm, per-sample extrema, interaction arithmetic,
complete ledgers and a human-readable report. Summary differences preserve the
host's aggregation rather than averaging per-sample deltas. Undefined division
metrics retain the host's score convention; undefined primary metrics block a
complete result. Adjusted Jaccard is not clipped to one.

Input checks cover graph containers and ordered attributes, parent summaries and
inventory chain, 16 GEFF trees including metadata/chunks, historical anchors,
parent source identities, installed evaluator source files/VCS provenance and
the recorded runtime. Preparation performs those checks without invoking cohort
matching. Execution repeats them before evaluation and after both passes.

The source closure includes all 103 original V27B source identities and the new
instrument, runner, tests, V27C contract/protocol and evaluator test references:
112 canonical source files in total. Parent-frozen modules, tests, contracts,
failures and results remain unchanged. Historical freeze validation is not
silently expanded to authorize V27C.

## Validation evidence

The combined battery passed **193 tests, zero failures/errors/skips**:

- 52 V27C tests for metric parity, single host evaluation, fresh-state replay,
  host ties and the inclusive 7 um boundary, one-time physical conversion,
  sparse-GT evaluability, host filtering, confidence changes, pruning-induced
  remapping, input mutation, undefined metrics and host summary weighting;
- the 133-test V27A/V27A.1/V27B and historical tracking regression battery;
- eight existing official tracking, association and division adapter tests.

Runner tests exercise source/runtime/input/test-report drift, missing or stale
approval, wrong scope, builder-as-reviewer rejection, exclusive output creation,
partial failure preservation, and synthetic complete two-pass orchestration.
Synthetic runner integration explicitly substitutes its cohort, authority and
cell evidence; it is not a hidden execution against the real 16 samples.

Pinned combined report: `outputs/v27c_validation_20260927.xml`. The sole warning
is the existing host summary's documented omission of a division term when no
division denominator exists. It is not a failed or skipped test.

The initial instrument report is retained at
`outputs/v27c_instrument_initial_20260927.xml`: one test expected an undefined
primary metric for completely empty host graphs, but the host raised
`reduce() of empty iterable with no initial value` first. The test was split
to preserve that host failure and separately exercise undefined-metric handling
with an explicitly synthetic host result. No host rule or contract was changed.
The initial runner report and intermediate evaluator report are also retained.

## Failure and resource boundaries

The run command requires an explicit approved-manifest SHA-256, FROZEN status,
payload integrity, a distinct reviewer and human authorization of the exact
V27C scope and payload. A candidate, parent approval or altered manifest is
rejected before cohort matching. Failing attempts retain active context,
completed cells, telemetry, available cell diagnostics and an artifact inventory.
Existing output directories are never reused or overwritten, and no automatic
retry is implemented.

Execution holds one sample's 15 cell records for paired comparisons; it never
loads image volumes or multiple samples' full correspondence tables together.
Large cell and ledger artifacts are compressed incrementally by sample. Saved
sample summaries retain metrics and accounting, not entire correspondence
tables. Telemetry reports evaluation-call wall time and Python-traced allocation
after graph loading; it is not total process RSS or a prediction of cohort cost.

No cohort metric runtime estimate or tracking-quality claim follows from these
tests. Historical metric anchors may still reveal differences when fresh
evaluation is authorized; an anchor mismatch must stop and preserve evidence.

## Reviewable candidate and next authority step

[Candidate manifest](v27c_freeze_candidate_20260927.json).

Candidate file SHA-256:
`56e9b6a6370784137b325375ffbb5316c4c2603c307017cdc9b30a1b8d4aa8c1`

Exact payload SHA-256:
`0b11827689b07034f3db3afa7142dbc60d8be9ead6cbfcf1e57af634c5e83af9`

Preparation completed successfully and pinned 112 canonical sources, 854 input
files, 103 installed host Python source files, 146 runtime package/version pairs
and the passing 193-test XML report. A subsequent read-only check confirmed
candidate payload integrity, complete source closure, unchanged source hashes
and the test-report identity.

The machine status is `READY_FOR_HUMAN_REVIEW`; both `review` and
`human_execution_authorization` are null. This candidate does not authorize
execution. Review its exact payload together with this report and the unchanged
[preregistration](V27C_OFFICIAL_GRAPH_EVALUATION_PREREGISTRATION.md). Human
approval of that payload is required before recording a separate approved
freeze and running the cohort. The original candidate must remain preserved.

V26A remains NO_GO. V27C remains retrospective on opened data; independent
validation, production promotion and submission remain outside its scope.
