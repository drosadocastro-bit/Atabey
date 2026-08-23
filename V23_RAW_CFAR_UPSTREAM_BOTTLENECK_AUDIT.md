# V23 Raw CFAR Upstream Bottleneck Audit

Decision: **READ-ONLY SHADOW DIAGNOSTIC**.

The seven raw-CFAR failures were decomposed into local-maximum, global-floor, adaptive-threshold, and top-900-cap stages. A single narrower `(1,3,3)` peak footprint was evaluated as a frozen shadow for distinct-daughter retention. Production candidates and graphs were not changed.

| Event | Control failure | Missing-role blockers | Narrow shadow |
|---|---|---|---|
| 44b6_706092f0 t49 | missing_parent | parent=global_floor | missing_parent |
| 44b6_74d0c52e t58 | missing_daughter_1 | daughter_1=global_floor | missing_daughter_1 |
| 44b6_aaf8b0ea t61 | no_distinct_daughter_pair | none | no_distinct_daughter_pair |
| 6bba_3abfe10a t81 | missing_parent | parent=adaptive_threshold | missing_parent |
| 6bba_57b7cc1e t23 | missing_parent | parent=global_floor, daughter_1=global_floor | missing_parent |
| 6bba_57b7cc1e t77 | missing_parent | parent=global_floor, daughter_1=global_floor | missing_parent |
| 6bba_fc5f39dc t24 | missing_daughter_1 | daughter_1=global_floor | missing_daughter_1 |

Aggregate:

- Control failures: `{'missing_daughter_1': 2, 'missing_parent': 4, 'no_distinct_daughter_pair': 1}`.
- Missing-role first blockers: `{'global_floor': 7, 'adaptive_threshold': 1}`.
- Cases recovered by the narrower shadow: **0/7**.
- Zero perturbation: no candidate set or graph was changed.
