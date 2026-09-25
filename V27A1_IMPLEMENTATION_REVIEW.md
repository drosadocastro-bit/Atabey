# V27A.1 implementation review

Date: 2026-09-24

Status: **IMPLEMENTED; VALIDATED; NEW CANDIDATE AWAITS HUMAN REVIEW**.

The [amendment](V27A1_TIE_GATE_AMENDMENT.md) replaces selected-outcome equality
with candidate-wise predicate validation for the H/M0 exact-tie contrast.
No new run of the 16-sample cohort has been performed. The already opened
failure witness was replayed as a regression test, not independent evidence.

## What changed

The additive observer `association_factorial_audit_v27a1.py` calls the unchanged
V27A frame observer. It copies and annotates that result. For both selected
candidates it independently checks recorded identities, physical-coordinate
distances, exact global motion minima, original-index choice, candidate-wise
eligibility and confidence consistency.

Only the old `h_m0_gate_mismatch` criterion can become a recorded outcome under
the new contract, and only when the check establishes
`EXACT_TIE_DIFFERENT_ELIGIBILITY`. All other original failures remain blocking.
The original failure list, original frame digest and each criterion disposition
are retained explicitly. Original target choices, confidence, reverse ownership,
distance tables, contrasts, interaction values and inputs are unchanged.

The separately named runner preserves the parent's execution/replay pipeline.
Its differences are its description, amended observer import, contract path,
scope ID, own source identity in the manifest, and an amendment-identity check.
Tests verify identical ASTs for the replay, execute, freeze-validation, input
validation, runtime-inventory and test-report functions. No global monkeypatch
or replacement of the old runner is used.

## Known-failure regression fixture

`tests/fixtures/v27a1_exact_tie_gate_witness.json` reconstructs the input context
from the stored failing t=38 frame and the preceding t=37 frame. It contains
71 previous detections, 70 targets and 57 baseline predecessors. Source archive
and approved-parent-manifest hashes are included.

The test verifies that the original observer still reports precisely its
original `h_m0_gate_mismatch`, while the amended observer preserves all decisions
and labels the witness `EXACT_TIE_DIFFERENT_ELIGIBILITY`. This does not amend the
parent run's `INVALID_EXECUTION` status.

## Validation

- Amendment-only run: **22 tests passed**.
- Combined amendment, V27, V26 and V25 battery: **93 tests passed**, zero failures,
  errors or skips.
- Tests cover opposite eligibility in either tie-selection direction, same
  eligibility ties, near-ties, incorrect candidate identity/distance/confidence,
  same-candidate predicate inconsistency, unrelated hard failures, determinism,
  preserved input/results, unchanged execution pipeline and scope separation.
- The original approved scope and a new unreviewed candidate are rejected by
  the amended execution entry points.
- All **89 parent source hashes** remain unchanged, as do the raw failure
  stream, original approved manifest and invalid-execution record.
- The new candidate's **97 source hashes**, runtime and input identities were
  checked again after creation in a separate imported invocation.

Final test report: `outputs/v27a1_validation_20260924.xml`

SHA-256: `5480e8d8abf92c0450682ab50d1796183754209e778794e30fcc77b81e93b256`

Adding versioned modules expands the current repository's source inventory;
the parent snapshot is preserved by its recorded 89 file identities. This is
not a claim that its old whole-workspace preflight accepts the expanded tree.

## Candidate to review

File: [v27a1_freeze_candidate_20260924.json](v27a1_freeze_candidate_20260924.json)

- Status: `READY_FOR_HUMAN_REVIEW`
- Scope: `V27A1_FIXED_HISTORY_CANDIDATE_WISE_GATES`
- Review and human execution authorization: null
- Same cohort, arms, contrasts, radii, histories and no-scoring boundary
- New lineage inputs pin the parent approval, invalid record and partial stream

Candidate SHA-256:
`d5a6b1c386a5b9b7b85783bee64a7da9071b171c53086d0f32514153f01c2dff`

Payload SHA-256:
`2e95327df40245deb2a885265b5ccef88aafb44e52fe6fd32408e4a2bcd19913`

This candidate has not inherited the parent authorization. After human review,
a separate approved manifest must name this exact payload and the new scope.
The original candidate and parent artifacts must remain unchanged. The new run
must start from sample one in a new output directory, with no append/resume of
the parent attempt and no automatic remediation on a subsequent failure.

```powershell
.\.venv\Scripts\python.exe scripts/run_v27a1_association_decomposition.py run `
  --freeze <new-approved-manifest.json> `
  --approved-freeze-sha256 <new-approved-manifest-sha256> `
  --output-dir <new-v27a1-output-directory>
```

V26A remains NO-GO, V27A remains INVALID_EXECUTION, and V27A.1 remains unexecuted
on the full cohort. No recursive experiment, scoring, promotion or submission
is authorized by this preparation.
