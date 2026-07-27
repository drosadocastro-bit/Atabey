# V22 Positive-Unlabeled Semantic Ranker Results

Decision: **NO_GO_POSITIVE_UNLABELED_RANKER**

Unknown actions remained in every held-out ranking pool and were never treated as negatives. No assignment or graph mutation occurred.

## Primary Retrieval

| Stratum | Action R@50 | Event R@50 | MRR |
| --- | ---: | ---: | ---: |
| pooled | 0.163265 | 0.179487 | 0.012877 |
| fold 1 | 0.312500 | 0.285714 | 0.025215 |
| fold 2 | 0.055556 | 0.076923 | 0.004998 |
| fold 3 | 0.095238 | 0.153846 | 0.006583 |
| cfar_sidelobe/bipartite | 0.000000 | 0.000000 | 0.000953 |
| components/greedy | 0.210526 | 0.218750 | 0.016328 |
| local_maxima/motion_mutual | 0.000000 | 0.000000 | 0.000112 |
| family 44b6 | 0.000000 | 0.000000 | 0.000135 |
| family 6bba | 0.170213 | 0.189189 | 0.013416 |

Best univariate baseline: `mean_detection_confidence`, event R@50 `0.128205`.
Primary event R@50 delta: `+0.051282`.

## Frozen Gates

- FAIL: `pooled_action_recall50`
- FAIL: `pooled_event_recall50`
- FAIL: `each_fold_event_recall50`
- FAIL: `cfar_action_recall50`
- FAIL: `cfar_event_recall50`
- FAIL: `components_action_recall50`
- FAIL: `components_event_recall50`
- FAIL: `each_family_event_recall50`
- PASS: `advantage_over_best_univariate`
- FAIL: `fold_spread`
- PASS: `route_gap`

## Local-Maxima

Reported separately as zero-shot/unproven generalization; excluded from the decision.

## Boundary

- This evaluates conditional retrieval of sampled official actions, not biological probability.
- Assignment, calibration, locked validation, and full-199 execution remain closed.
