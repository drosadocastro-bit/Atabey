# V27A.1 amendment: candidate-wise gates under exact forward ties

Date: 2026-09-24

Status: **IMPLEMENTATION AUTHORIZED; NEW FREEZE AND EXECUTION NOT YET APPROVED**.

Danny accepted the recommendation to prepare an explicit amendment after
reviewing V27A's invalid execution. This authorizes preparing and validating the
amendment. The previous execution authorization covered the original payload;
it does not silently extend to this new revision.

## Parent evidence and preserved result

Parent payload: `f671c838f5ea3373d9259a1f36f0671624e041ba56603ec734d5a3833021f310`.
The parent remains `INVALID_EXECUTION`, with its original code, contract,
approved manifest, partial frame stream and failure record unchanged.

The observed source `unet:6bba_05b6850b:n00003034` at t=38 selected two different
targets with exactly equal squared prediction distance, 34.328125 um². Their
squared physical steps were 0 and 132.031250 um². The unchanged 9 um step gate
therefore gave different eligibility. See [the failure audit](V27A_EXECUTION_FAILURE_AUDIT.md).

## Single amendment to execution validity

Replace the requirement that H and M0 have the same **selected-target eligibility**
with verification that both use the same **candidate-wise predicate**:

`eligible(source, target) = finite(motion_error, physical_step) AND motion_error <= 9 AND physical_step <= 9`.

Different selected-target eligibility is permitted only when:

1. H and M0 selected distinct recorded candidate indices and identities.
2. Both selected candidates are exact global minima of the same motion-error
   table, H's recorded query distance agrees exactly, and M0 selects the first
   original index among those exact minima. No epsilon, rounding or jitter.
3. Recorded distances agree exactly with the physical-coordinate calculation
   for both selected candidates.
4. Each arm's eligibility agrees with the predicate on its own chosen target.
5. Existing executable H/S1 anchors, confidence, input immutability and all
   other checks still pass. This amendment cannot excuse those failures.

Keep same-candidate eligibility discrepancies, non-tie selection discrepancies,
unexplained numerical differences, incorrect predicate application and confidence
discrepancies invalid. Reverse ownership and its tie behavior remain unchanged.

Label an admitted difference `EXACT_TIE_DIFFERENT_ELIGIBILITY` and report it as
a tie-mediated downstream outcome, not a change to the gate implementation.
Also record `SAME_SELECTION`, `EXACT_TIE_SAME_ELIGIBILITY`, `NO_TARGETS` and
invalid-evidence classifications. Counts do not imply tracking quality.

## Implementation and provenance boundary

Use an additive observer adapter over the frozen V27A frame function. Preserve
its original validity failures and the digest of its unmodified frame result.
The revised result lists every disposition of the old gate-outcome criterion;
it does not rewrite the old run as valid. The adapter may annotate results and
validate them but must not change decisions, confidence, distances, contrasts,
interaction values, predecessor inputs or target order.

Use a separately named V27A.1 runner and manifest. The runner retains the
original pipeline and output behavior, with explicit imports of the amended
observer and scope. A versioned runner is required because the original runner
is part of the approved immutable parent payload. No process-wide monkeypatch
or hidden replacement of the old runner is permitted.

All arms, contrasts, cohort IDs, archive identities, radii, tie policies,
baseline histories, pruning reference checks, no-scoring boundary and replay
requirements remain as originally proposed. The new run, if approved, starts
from the first sample in a new output directory. It must not resume or append
to the invalid parent stream. V27B remains outside scope.

## Validation and interpretation

Include a provenance-linked fixture reconstructed from the saved failed frame
and its preceding frame. It is a known regression witness from opened data,
not independent evidence. Require the original observer to retain its original
failure on that witness and the adapter to preserve every original decision.

Test opposite eligibility in both selection directions, equal-eligibility ties,
non-ties and near-ties, wrong candidate IDs/distances, same-candidate predicate
inconsistency, confidence errors and unrelated hard failures. Test the amended
runner's rejection of a candidate and of the old approved scope.

Recompute and review a new source/runtime/test payload. Do not reuse the old
human review or authorization fields. Real-data execution requires human review
of that exact amended payload. This is a prospective validity-definition change
motivated by one observed failure, not a blind validation or a production gain.
