# V27A frozen execution: exact tie with different gate outcomes

Date: 2026-09-24

Status: **FROZEN AND EXECUTED; INVALID_EXECUTION**.

Danny explicitly confirmed review of the presented candidate and authorized
freeze and execution. The exact reviewed payload was retained in a separate
approved manifest. The first real-data run stopped at a binding validity check.
No scientific comparison across the cohort is available and no automatic retry
or change to the frozen implementation was made.

## Authority and integrity

- Approved manifest: `v27a_freeze_approved_20260924.json`
- Manifest SHA-256:
  `1011ace2bf79da1e044188c742880eae1694bed6b5a4fe15cc1d551109af3b49`
- Unchanged reviewed payload SHA-256:
  `f671c838f5ea3373d9259a1f36f0671624e041ba56603ec734d5a3833021f310`
- Preflight passed: source coverage/hashes, runtime, test evidence and input
  identities agreed with the approved payload.
- After failure, all 89 source hashes, runtime and input identities were
  rechecked and remained unchanged. The saved `freeze_used.json` is identical
  to the approved manifest.

The approval record quotes the user's actual instruction:
"si baby acabo de revisarlo y me parece bien congelado y ejecuta".
Codex recorded the human's stated review and authorization; it did not act as
the reviewer or grant itself approval.

## First causal failure

- Sample: `6bba_05b6850b`, the first of the 16 prescribed samples
- Source frame: t=38 (association to t=39)
- Source: `unet:6bba_05b6850b:n00003034`
- Predecessor: `unet:6bba_05b6850b:n00002964`
- Failed check: `h_m0_gate_mismatch`
- Process exit: 1

The saved record contains exactly this failure for the frame. It reports no
H/S1 executable-anchor mismatch or non-tie-selection mismatch there.

| Decision | H: historical cKDTree | M0: original-index tie rule |
| --- | --- | --- |
| Selected target suffix | `n00003104` | `n00003103` |
| Target index | 67 | 66 |
| Prediction error (um) | 5.859020822628983 | 5.859020822628983 |
| Physical step (um) | 0.0 | 11.490485194281398 |
| Prediction gate, at most 9 um | Pass | Pass |
| Physical-step gate, at most 9 um | Pass | Fail |
| Accepted target | `n00003104` | None |

Both choices belong to the recorded exact forward tie `[66, 67]`. An independent
Decimal calculation on the stored physical coordinates gives squared prediction
distance **34.328125 um² for both targets**, so no approximate tie tolerance is
needed to explain this case. Squared physical steps are 0 and 132.031250 um².

The shared source position is `[100.75, 50.375, 73.125]` um. Its prediction is
`[100.75, 47.125, 68.25]` um. Target 67 is at the source position; target 66 is at
`[100.75, 42.25, 65.0]` um. These coordinates explain equal prediction errors
with different physical-step eligibility.

M1, S0 and S1 select and accept target 67 in this recorded context. The source
has no archived V25 loss membership in the frame record. These observations
describe the failure witness, not a newly scored recovery or a biological claim.

## Interpretation of the failed criterion

The proposed contract required H/M0 tie normalization to preserve gate outcomes.
That requirement is stronger than preserving the gate definitions. A different
choice among equally ranked targets can legitimately cross the unchanged
physical-step boundary. Here the tie decision changes which candidate receives
the test; it does not change the threshold or gate implementation.

The observed witness therefore supports an exact-tie-mediated eligibility
change, rather than a rounding discrepancy. The run is still invalid under its
actual frozen criterion. The builder's earlier design treated an invariant
downstream outcome as a prerequisite for studying tie effects; this example
exposes that limitation. The passing synthetic battery did not cover this
specific tied-prediction/opposite-step-eligibility case.

Do not silently reinterpret the failed condition as passed, patch it away,
claim that the rest of the cohort would pass, or use the partial counts to
compare tracking quality.

## Extent and preserved evidence

- Samples started: 1; samples completed: **0**; other samples unattempted: 15
- Complete scientific passes: **0**; the second pass was not started
- Frame records persisted: 39, including the failing frame
- Frames without a reported validity failure before that frame: 38
- Source rows persisted: 3,037
- The first sample's three baseline/pruning signature checks preceded the
  failure in the guarded runner; full-cohort verification of 48 signatures
  was not completed during this run.

Raw files under `outputs/v27a_frozen_20260924/`:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `6bba_05b6850b.pass1.jsonl.gz` | 3,383,326 | `4bc89a688438a1002a3b45d59b83b3a10941c4d7ac5383e219b921bfb01ea3f3` |
| `freeze_used.json` | 21,774 | `1011ace2bf79da1e044188c742880eae1694bed6b5a4fe15cc1d551109af3b49` |
| `invalid_execution.json` | 351 | `cbcd557fd2cf62f86b60241605bec908d87373d316389ef56537b7aed7f68bc7` |

The additive machine review,
[v27a_execution_failure_review_20260924.json](v27a_execution_failure_review_20260924.json),
contains the original error, the full offending source row, coordinate checks,
progress, authority link, and raw evidence hashes. It does not replace raw output.

## Next research decision

A separately reviewed prospective amendment could distinguish unchanged
candidate-wise gate definitions from changed gate outcomes caused by selecting
another exactly tied target. It should add this failure witness to its synthetic
coverage and continue rejecting unexplained non-tie or numerical discrepancies.
The present artifact does not implement, freeze or authorize that amendment.

V24.3 remains the reference, V26A remains NO-GO, and V27A has an invalid partial
execution. No new official scoring, recursive history, promotion, tuning or
submission was performed.
