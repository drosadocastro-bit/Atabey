# V25 Failure Taxonomy Audit

Date: 2026-08-30

Status: **INITIAL CLASSIFICATION FROM RETAINED EVIDENCE; TELEMETRY PENDING**.

The fixed cohort is the 16 samples where V24.3 regressed against V19. Existing
artifacts contain aggregate official metrics but not edge coordinates or
candidate margins. They therefore cannot answer whether a correct association
was absent from the candidate set or entered and lost.

## Initial Classification

| Stratum | Samples | Current V25 class | Evidence |
| --- | ---: | --- | --- |
| Catastrophic association loss | 4 | `unresolved_insufficient_telemetry` | Adjusted delta below -0.10; correct-candidate presence is unknown. |
| Mild association loss | 2 | `unresolved_insufficient_telemetry` | TP falls and FP rises; correct-candidate presence is unknown. |
| Precision tradeoff | 8 | `unresolved_insufficient_telemetry` | TP and FP both rise; individual wrong-edge mechanisms are unknown. |
| Adjustment-only tradeoff | 2 | `metric_node_adjustment_only_effect` | Raw edge Jaccard improves; official node adjustment reverses the result. |

The two adjustment-only samples are `6bba_b204cac7` and `6bba_ed9377fd`.
The four catastrophic samples are `6bba_2646afc7`, `6bba_2540cd90`,
`6bba_76db78c1`, and `6bba_d5eae175`.

## Preserved Negative Findings

- V24.2 and V24.3 improve every regression over their immediate predecessor;
  existing sample-level evidence does not identify pruning as the cause.
- Division handling is not causal in the retained aggregate evidence.
- Route identity cannot authorize fallback: the same `components + greedy`
  stratum contains 92 V24.3 wins.
- Node-ratio, edge-ratio, and short-fragment-removal thresholds do not isolate
  the regressions without many false positives.
- V24.7 commitment plus ILP does not supply a rescue mechanism.

## Pending Answer

For 14 of 16 samples, the key V25 question remains unanswered. The first V25
telemetry run must classify local official edge losses using direct candidate
presence, acceptance, and pruning-survival evidence. Until then, replacing
`unresolved_insufficient_telemetry` with generation or ranking failure would be
an unsupported claim.