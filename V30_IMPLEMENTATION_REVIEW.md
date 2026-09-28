# V30 implementation review

**IMPLEMENTED — awaiting Danny's review; not frozen or authorized to execute.**

This is the implementation of the accepted diagnostic preparation. The original
[methodology](V30_DIAGNOSTIC_CONTRACT.md), [proposal](v30_diagnostic_proposal_20260928.json)
and [preparation review](V30_REVIEW.md) remain unchanged as historical artifacts.
Their implementation-pending status describes that earlier preparation, not this
new candidate. No V28/V29A source, result, threshold or freeze has been changed.

## What is implemented

- [Diagnostic module](src/atabey/tracking/v30_diagnostic.py): validation and faithful
  RAW/P2/P3 reconstruction through the existing functions; exact and isolated-near
  correspondence; link, confidence, predecessor-chain and removal-stage tables;
  arithmetic context from copied official metrics.
- [Runner](scripts/run_v30_diagnostic.py): complete identity preflight, separately
  bound human execution receipt, one sample pair resident at a time, exclusive
  outputs, a parent-enforced two-hour limit, closure checks and a report.
- [Synthetic tests](tests/test_v30_diagnostic.py): instrumentation and failure
  behavior. They do not read the 199 real coordinate pairs or run GT scoring.
- [Implementation candidate](v30_implementation_candidate_20260928.json): hashes
  binding these additions, original method/input inventory and test evidence.

The runner reads saved coordinates and records. It does not read images or GT,
load model weights, invoke the official evaluator, access Kaggle, create a
competition submission, or select a tracking variant per sample.

## Explicit implementation details for review

The original 2.0-micron neighborhood rule, exact-only primary view, cohort and
focus memberships are unchanged. The following details make its implementation
auditable before any real coordinate comparison:

1. A coordinate key duplicated in either arm excludes every occurrence of that
   key in both arms, including a singleton opposite a duplicate. Neighborhood
   degrees count eligible unique coordinates only. NO_NEAR_COUNTERPART therefore
   means no eligible counterpart within the radius; duplicate counts remain visible.
2. Neighborhood degrees are computed once over the full eligible frame, including
   exact anchors. A one-ULP expanded tree lookup is followed by the authoritative
   float64 squared-distance comparison `<= 4.0`. There is no iterative matching.
3. Chain comparison proceeds backwards through mapped predecessors. Both absent
   ends a shared chain; one absent proves a different chain. Different mapped
   predecessors prove a different chain. If both exist and either is unmapped,
   comparison is unresolved at that point; it does not skip that gap to speculate
   about an earlier identity. Equal mapped predecessors inherit the memoized status.
   Full per-arm depths and RAW edges are retained for audit.
4. Unexpected branches, merges, duplicate edges, nonadjacent edges or non-continuation
   relations are invalid for this frozen linker. Relation-change reporting remains
   separate, even though a valid continuation-only replay should report zero.
5. Group coordinate fractions pool counts over nodes within each named group.
   Group link and history tables sum their corresponding counts. These are
   descriptive counts, not independent observations or new official scores.
   Group overlap is explicit; original official aggregates are copied unchanged.
6. Each sample has compressed full tables plus an uncompressed compact summary.
   Tables retain original node IDs, coordinates, RAW edges, stage removals,
   correspondence labels and history classifications. Focus reports link to these
   same full tables; they do not rerun the selected samples.

## Validation evidence

The final [test report](outputs/v30_implementation_20260928/tests_release.xml)
contains **84 passed tests**, including 42 V30 tests and the relevant existing
graph/V29A checks. The V30 suite includes an explicitly synthetic 199-pair fixture
through graph replay, export parity, comparison, output writing and closure.
Its input registry is a test fake; it is not the real scientific cohort or proof
of real-data replay parity.

Other cases exercise anisotropic distances, the radius boundary, duplicate and
crowded coordinates, ambiguous matching chains, confidence-only changes, changed
endpoints with equal totals, missing frames, P2/P3 removal, unresolved histories,
input/hash/parity failures, receipt rejection and a forcibly stopped test worker.
Earlier passing test reports are retained alongside the final run.

The identity-only [implementation preflight](outputs/v30_implementation_preflight_20260928/preflight.json)
checks actual input hashes, original source-bundle parity, both release freezes,
runtime package versions and cohort/route/reference lineage. No graph replay,
coordinate comparison or new scoring is performed by preflight. Real comparison
coverage, replay parity and runtime remain unverified until an approved run.

## Execution authority and terminal evidence

The candidate is unapproved. There is intentionally no V30 approved receipt.
After review, a separate receipt must name Danny as authority, preserve his actual
approval text, bind the candidate SHA-256, and fix one execution ID and absolute
output directory. Its scope is exactly
`ONE_CPU_SAVED_COORDINATE_DIAGNOSTIC_NO_SCORING`; scoring and submission authority
must both be false. The candidate cannot authorize itself.

The runner refuses absent or mismatched approval before scientific work. It never
reuses an output directory. A spawned CPU worker is bounded by its parent, including
preflight and closure; the parent can stop a long native operation at the deadline.
No monitor, retry or resume is created automatically.

Completion requires `finished.json` and matching hashes for `result.json` and
`REPORT.md`, with no `failure.json`. `completed_payload.json` is intermediate
worker output; neither it nor a partial report alone establishes completion.
Input and implementation hashes are checked again at closure, as are written
sample tables. Any mismatch or budget failure preserves the first worker failure,
partial tables and completed IDs; failure takes precedence over other artifacts.

An approved complete result will be descriptive only. V29A stays NO_GO; any
optimization proposal or causal experiment follows a separate review. This
candidate does not authorize GPU work, a Kaggle submission, commit or push.

## Recommendation

Review this candidate and, if accepted, freeze and execute one CPU diagnostic on
the saved 199 pairs. The useful output is a map of observed failure patterns and
their limits, followed by a narrowly specified intervention only if the evidence
supports it. There is no promise that V28 will improve.
