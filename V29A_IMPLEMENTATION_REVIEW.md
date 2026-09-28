# V29A implementation review

Status: **PROPOSED_NOT_APPROVED**. Prepared September 28, 2026.
Builder: Codex. Reviewer and execution authority: Danny.

V29A is ready for review of one bounded research execution. There are no V29A
GPU results, official quality measurements or competition submissions yet.
The candidate manifest is `v29a_research_candidate_20260928.json`.

## Exact intervention and deliverable

Enable the existing predictor's four-view XY detector TTA, changing only
`det_tta` from false to true. Retain the V28 checkpoint, thresholds, physical
linker, pruning, routing and output schema. Different detections can alter
candidate order, ties and recursive history; this is a detection intervention
with downstream effects. It is not a ranking-only causal comparison.

Review `V29A_TTA_RESEARCH_CONTRACT.md` for the complete decision rules.
The executable package is `outputs/v29a_preparation_20260928/package_r1`.
Its manifest SHA-256 is:

`7d93749e50dfe95fa1643dceb39e870f9111850ce994c14c30ca1496ddd4dc67`

The 501,694-byte source bundle contains 81 pinned source/contract members plus
its manifest. The notebook embeds this bundle and stops before installation or
GPU work while its receipt remains `NOT_APPROVED`. The repository notebook and
package notebook are identical. Approval would create a separate dispatch copy
with the receipt filled in; preserve the unapproved template and record both
identities. The package manifest stays unchanged.

## One research execution, two phases

1. **Kaggle inference: at most 6 hours**, including setup, potentially consuming
   12 device-hours on a two-GPU allocation. Check the seven fixed timing cases,
   two exact repeats and four visible CSV cases before completing both branches
   across all 199 samples. An unchanged conservative V28 runtime projection must
   pass its 10-hour limit, first on the timing cases and again on all cases.
2. **Local official evaluation: at most 3 hours**, only after complete inference
   passes timing and identity checks. Rebuild both graphs, reproduce historical
   baseline signatures and official metrics, and compare TTA using the pinned
   evaluator and GT. Launch the local process with a 10,800-second outer timeout;
   the runner also checks its budget between samples.

The historical archive has counts and metrics, not coordinates for all samples.
Fresh baseline inference is therefore explicitly included. All 199 baseline
signatures must reproduce the historical references. A hardware or numerical
parity failure invalidates the execution; it is not permission to relax parity.

At dispatch, recheck the candidate hashes, quota, deadline, selected entries and
actual Kaggle image identity. Enforce the six-hour overall research limit in
addition to the notebook's remaining-time child timeout. Capture failures and
partial outputs. Do not retry silently or regenerate missing evidence.

## Promotion criteria

All fixed gates must pass: aggregate combined-score gain at least **0.003**,
nondecreasing aggregate adjusted-edge Jaccard and subgroup scores, more improved
than regressed samples, individual score losses at most **0.020**, no losses on
the four catastrophic cases, aggregate recall loss at most **0.002**, and no
increase in summed official edge FP. Require complete paired coverage and
defined primary/guard metrics. The contract identifies all subgroups and cases.

The 172 training and 27 held-out samples have all been opened. This comparison
is development evidence, not independent validation; passing does not predict
a public or private leaderboard gain. Timing extrapolation assumes the hidden
voxel workload is no greater than the observed 199-sample workload and remains
uncertain about density, storage and hardware effects.

Passing yields `GO_TO_HUMAN_SUBMISSION_REVIEW`. A separate submission package,
visible validation and approval precede any new competition submission.

## Implementation checks and retained failure

**110 tests passed** in `outputs/v29a_preparation_20260928/tests_r2.xml`.
Coverage includes the actual embedded notebook, source identities, refusal of
unapproved or wrong-scope execution, timing failure blocking evaluation,
coordinate serialization through the real graph/CSV adapter with an explicit
fake predictor, historical metric parity, and each quality gate.

The first test run had 108 passes and one failure: an assertion compared a
JSON-decoded list with an in-memory tuple. Only that test's serialization
expectation was corrected. `tests_initial.xml` preserves the failure. These
tests establish implementation behavior; they do not measure TTA efficacy,
runtime, GPU determinism or live official baseline parity.

The final preparation audit verifies the package and local sources, pinned
official dependencies/runtime, all 199 image metadata records and GT tree
identities, the historical archive, all 76 V28 release artifacts, and the
pre-existing V25 notebook bytes. It performs no inference or metric evaluation.
Its record is `outputs/v29a_preparation_20260928/preparation_audit.json`.

## Existing submission and authority

The authenticated Kaggle selected-submissions query at
2026-09-28 11:17:59 UTC returned **V28 56631581 (0.728)** and
**V19 54622713 (0.515)**. Its response is preserved in
`outputs/v29a_preparation_20260928/final_selection_check.json`.
No selection change was made. V28 remains frozen at tag `v28-kaggle-0.728`.

The proposed research approval covers exactly one offline GPU research version
and, conditionally, its paired local evaluation. It does not authorize a
competition submission, a parameter sweep, retry, commit/push or selection
change. Implementation preparation was authorized; the exact package and
resource limits are presented here for the established freeze/execution review.
