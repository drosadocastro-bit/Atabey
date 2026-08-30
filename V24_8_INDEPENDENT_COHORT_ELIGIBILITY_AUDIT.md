# V24.8 Independent Cohort Eligibility Audit

Date: 2026-08-30

Decision: **NO QUALIFYING INDEPENDENT COHORT AVAILABLE**.

This audit inventories the repository evidence available for the V24.8
post-pruning commitment-plus-ILP shadow. It does not authorize implementation,
execution, threshold tuning, selection, graph mutation, or submission.

## Reproducible Evidence

The machine-readable audit is
`v24_8_independent_cohort_eligibility_audit.json`. It pins newline-stable hashes
for the labeled checkpoint manifest, the historical internal split, and the
completed V24.3 full-population report.

Direct set comparison against the retained V24.3 per-sample records produced:

| Check | Count |
| --- | ---: |
| Unique labeled manifest samples | 199 |
| Checkpoint-training samples | 172 |
| Held-out development samples | 27 |
| Opened V24.3 per-sample records | 199 |
| Labeled samples not opened | 0 |
| Opened records outside the manifest | 0 |

The sorted union of the 172 checkpoint-training IDs and 27 held-out IDs has
SHA-256
`9dcf4f774e02c9d818227ba25831ff4a29eafb4749418c862c3dd42a1c8a0dcb`,
which matches the population identity recorded by the completed V24.3 audit.

## Candidate Adjudication

| Candidate | Eligibility | Reason |
| --- | --- | --- |
| Checkpoint-training 172 | Ineligible | Used to fit the frozen checkpoint and later scored in V24.3. |
| Held-out development 27 | Ineligible | Opened during V24 development and later scored in V24.3. |
| Historical internal-validation 34 | Ineligible | All 34 are members of the checkpoint-training 172; `test` denotes an internal split, not new competition evidence. |
| Route-90 | Ineligible | It is a subset of the opened 199 and was explicitly evaluated in V24.7. |
| Competition hidden test | Not currently eligible | Labels and per-sample official outcomes are not locally available or auditable, so the required immutable labeled manifest and raw-denominator contract cannot be frozen. |

The older internal-validation split does not preserve independent evidence for
V24.8. Its name alone cannot override its membership or prior checkpoint use.

## Decision Boundary

No labeled repository sample satisfies the V24.8 independent-evidence gate.
The experiment therefore remains blocked. Opened samples may support only
invariant and implementation tests and must not influence thresholds, gates, or
promotion decisions.

The gate may be reconsidered only after acquiring genuinely new labeled samples
with an immutable source manifest and documented non-use in V24 development. A
hidden-test submission is not a substitute unless the competition interface can
satisfy the preregistered per-sample evidence and raw-denominator requirements.