# V24.3 Full-199 Score Validation Audit

Date: 2026-08-27

Decision: **FULL_199_SCORE_VALIDATION_COMPLETE**.

This completes the authorized population score validation. It does not authorize
submission, threshold tuning, retraining, hybridization, or production graph
mutation.

## Integrity

- Evaluation commit: `2af9cbf3f192171e669db223967f8ba8eedb6d81`
- Frozen checkpoint SHA-256: `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`
- Support predictor SHA-256: `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`
- Shard 0: 100 samples; deterministic replay verified
- Shard 1: 99 samples; deterministic replay verified
- Strict merge: 199 unique samples; no missing, duplicate, or provenance-mismatched records
- Population split: 172 checkpoint-training samples and 27 held-out samples

Artifact fingerprints are recorded in
`v24_3_full_199_score_validation_report.json`. The merged local archive is
`v24_3_full_199_merged_outputs.zip`.

## Population Result

| Metric | V24.3 result |
|---|---:|
| Adjusted edge Jaccard | 0.721056 |
| Edge Jaccard | 0.729042 |
| Node recall | 0.961490 |
| Adjusted-edge delta vs V19 | +0.235028 |
| Total-score delta vs V19 | +0.234923 |
| Improved / regressed vs V19 | 183 / 16 |
| Catastrophic regressions vs V19 | 4 |
| Median predicted-node ratio | 1.206727 |
| P90 predicted-node ratio | 1.647750 |

Both families, all three deterministic folds, and every V19 reference route had
positive population adjusted-edge deltas. These are descriptive population
results rather than new preregistered generalization gates.

## Evidence Strata

The held-out 27 reproduced the authoritative result exactly:

- adjusted edge Jaccard: 0.744351
- adjusted-edge delta versus V19: +0.226518
- improved / regressed: 26 / 1
- catastrophic regressions: 0
- median / p90 node ratio: 1.221235 / 1.420642

The checkpoint-training 172 produced:

- adjusted edge Jaccard: 0.716372
- adjusted-edge delta versus V19: +0.236658
- improved / regressed: 157 / 15
- catastrophic regressions: 4
- median / p90 node ratio: 1.198183 / 1.664921

The 172-sample score is population context only. Those samples were used to fit
the frozen checkpoint and cannot provide independent generalization evidence.

## V24.3 Increment Over V24.2

Across all 199 samples, V24.3 improved 89, tied 109, and regressed 1 relative
to V24.2. The sole decrease was `6bba_87289e13` at -0.000447 adjusted edge
Jaccard. V24.3 removed 40,208 additional detections relative to V24.2.

All four catastrophic V24.3 regressions versus V19 occurred in the
checkpoint-training stratum. V24.3 improved each of those four samples relative
to V24.2, so they are not regressions introduced by the short-fragment rule.
The complete 16-case mechanism and containment analysis is recorded in
`V24_3_FULL_199_REGRESSION_FORENSICS.md`.

## Adjudication

The full-199 run confirms that the frozen V24.3 behavior scales across the
complete labeled population and preserves the held-out result. It does not turn
the 172 training samples into independent evidence and does not authorize a
submission. Any submission decision requires a separate explicit contract and
human review of competition output-schema validity, runtime feasibility, and
the four population catastrophic cases.
