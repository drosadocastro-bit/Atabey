# V27A implementation and freeze review

Date: 2026-09-24

Status: **IMPLEMENTED AND SYNTHETICALLY VALIDATED; AWAITING HUMAN REVIEW**.
No real-data V27 factorial run has been performed. V27B remains a future phase.
The earlier proposal is retained unchanged as the scientific design reference.

## Implemented behavior

- `src/atabey/tracking/association_factorial_audit.py` measures H, M0, M1, S0
  and S1 on a single immutable frame/history context. The original V25 audit
  module is pinned by hash, so this is a composed auxiliary extension using
  the existing prediction, greedy and executable anchor functions. It does not
  introduce another production tracker or modify any historical module.
- All four factorial conditions share distance tables, target order, reverse
  ownership and confidence definition. Telemetry distinguishes selection,
  gate eligibility, reverse rejection and final acceptance; all five paired
  contrasts preserve before/after target identities and signed acceptance.
- Exact forward and reverse ties, no-predecessor context, gate-order exposure,
  historical loss memberships and the acceptance interaction remain visible.
  Differences in H/M0 gates or confidence, or non-tie target choices, are
  validation failures; no tolerance is introduced to conceal them.
- `scripts/run_v27_association_decomposition.py` provides `prepare-freeze`
  and guarded `run` commands. The latter reconstructs only the historical
  baseline, validates its 48 signatures, and streams per-frame JSONL into
  deterministic gzip files. Each sample is replayed twice. Alternate decisions
  are never fed back into history or sent through pruning or official scoring.
- Scientific failure frames are written before the runner stops. Partial sample
  files and `invalid_execution.json` are retained. Existing output directories,
  frame streams and manifests cannot be overwritten by the runner.

## Validation evidence

Final battery: **71 passed; zero failures, errors or skips**. It includes 32 V27
tests plus 39 existing V25/V26 and association-audit tests. The V27 tests cover:

- both directions of the order effect, opposing feasible ranks, and target
  identity changes hidden by equal acceptance counts;
- inclusive gates, infeasible/empty targets, no predecessor and invalid inputs;
- original-index forward ties, unchanged reverse ties, uniqueness and confidence;
- exact local H/S1 anchors, input preservation and deterministic replay;
- synthetic multi-frame proof that an alternative predecessor is never propagated;
- persistence of a failed frame before stopping;
- rejection of a proposed freeze, missing manifest approval digest, missing
  review/authority, builder self-review, changed or omitted sources, changed
  payload, runtime drift, failed test evidence and a changed scientific arm;
- inclusion of transitive local runner imports in the source manifest;
- runtime inventory invariance to duplicate package discovery, while retaining
  distinct installed versions.

Final raw JUnit evidence:
`outputs/v27a_implementation_validation_20260924_r3.xml`

SHA-256:
`aa5451618958ca0d7b5b7c3c4e7fd7dc06ca43d89f25a4a3c13d9c174a61c8cc`

These tests establish synthetic behavior and enforcement paths. They do not
establish that the real-data H/M0 tie-only check will pass, that V27 improves
tracking, or that recursive effects have been quantified.

## Preserved development findings

1. The initial V27-only test run had 28 passes and two failures. NaN and infinity
   were rejected by JSON hashing before the intended physical-coordinate
   validator. The observed message was `Out of range float values are not JSON
   compliant`. Physical finiteness validation now precedes hashing. The failure
   was diagnostic ordering; no non-finite input was accepted.
2. A subsequent 69-test battery passed. Final source review identified imported
   historical helper scripts not yet covered by the candidate's source list.
   The manifest now includes their static local import closure; 70 tests passed.
3. The first candidate's runtime fingerprint differed between CLI and imported
   invocations because editable `project-atabey==0.1.0` was discovered one extra
   time through repeated Python search paths. All unique package/version pairs
   were identical. The inventory now records unique name/version pairs, with
   a regression test. The final battery has 71 passes.

The first candidate, `v27a_freeze_candidate_20260924.json`, and the earlier
JUnit files are retained. That candidate is **superseded**: its implementation
hashes no longer describe current code, and it must not be approved for a run.
No frozen or executed experiment was revised during these implementation checks.

## Active candidate for review

File: [v27a_freeze_candidate_20260924_r2.json](v27a_freeze_candidate_20260924_r2.json)

- Status: `READY_FOR_HUMAN_REVIEW`
- Review: null
- Human execution authorization: null
- Sources: 89 canonical hashes, including scientific references, all Atabey
  source modules, required local helper imports and V27 tests
- Runtime: Python/platform identity and 146 unique package/version pairs
- Inputs: the original archive and gate-order evidence identities
- Test evidence: the final JUnit report above

Candidate file SHA-256:
`babf9b45fa5cacedb78a65831c4a520b65be4e8bc9e3b28d11409a2da93e6fea`

Reviewed-content payload SHA-256:
`f671c838f5ea3373d9259a1f36f0671624e041ba56603ec734d5a3833021f310`

Source and runtime identities were independently rechecked after candidate
creation from a second imported invocation. The candidate is a content snapshot
of local work, not a claimed new Git commit. The existing `main` baseline and
V26A NO-GO are unchanged.

## Review and execution boundary

The [proposed contract](V27_ASSOCIATION_CAUSAL_DECOMPOSITION_PREREGISTRATION.md)
requires reviewing the implementation against its decision table and recording
human authorization for the exact frozen content before a real-data run.
The user's request to build V27 has been fulfilled by this implementation and
candidate; the builder has not supplied its own human review record.

After human review, create a separate approved manifest with the same payload,
status `FROZEN`, a reviewer distinct from the builder, the actual review record,
and human execution authorization naming this payload hash and V27A scope.
Keep the candidate unchanged. These fields record authority provenance; they
are not cryptographic authentication of a person's identity. The CLI additionally
requires the externally supplied SHA-256 of that approved manifest, and checks
sources, runtime, test evidence and inputs before execution and again afterward.

```powershell
.\.venv\Scripts\python.exe scripts/run_v27_association_decomposition.py run `
  --freeze <approved-manifest.json> `
  --approved-freeze-sha256 <approved-manifest-sha256> `
  --output-dir <new-output-directory>
```

The current candidate deliberately cannot execute. A real-data failure must be
reported as `INVALID_EXECUTION`, with its evidence retained; it cannot trigger
an automatic code adjustment, threshold change, rerun or arm selection.
