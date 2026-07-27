# V22 Positive-Unlabeled Semantic Ranker Results

Decision: **NO_GO_POSITIVE_UNLABELED_RANKER**

Unknown actions remained in every held-out ranking pool and were never treated as negatives. No assignment or graph mutation occurred.

## Primary Retrieval

| Stratum | Action R@50 | Event R@50 | MRR |
| --- | ---: | ---: | ---: |
| pooled | 0.366667 | 0.526316 | 0.103050 |
| fold 1 | 0.400000 | 0.538462 | 0.120730 |
| fold 2 | 0.333333 | 0.538462 | 0.056779 |
| fold 3 | 0.300000 | 0.461538 | 0.120463 |
| cfar_sidelobe/bipartite | 0.000000 | 0.000000 | 0.001092 |
| components/greedy | 0.488889 | 0.645161 | 0.137036 |
| local_maxima/motion_mutual | 0.000000 | 0.000000 | 0.000883 |
| family 44b6 | 0.000000 | 0.000000 | 0.002354 |
| family 6bba | 0.385965 | 0.555556 | 0.108247 |

Best univariate baseline: `mean_daughter_contrast`, event R@50 `0.526316`.
Primary event R@50 delta: `+0.000000`.

## Frozen Gates

- FAIL: `pooled_action_recall50`
- FAIL: `pooled_event_recall50`
- FAIL: `each_fold_event_recall50`
- FAIL: `cfar_action_recall50`
- FAIL: `cfar_event_recall50`
- FAIL: `components_action_recall50`
- FAIL: `components_event_recall50`
- FAIL: `each_family_event_recall50`
- FAIL: `advantage_over_best_univariate`
- PASS: `fold_spread`
- FAIL: `route_gap`

## Local-Maxima

Reported separately as zero-shot/unproven generalization; excluded from the decision.

## Boundary

- This evaluates conditional retrieval of sampled official actions, not biological probability.
- Assignment, calibration, locked validation, and full-199 execution remain closed.
