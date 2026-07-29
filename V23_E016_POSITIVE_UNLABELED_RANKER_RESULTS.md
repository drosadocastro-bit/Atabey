# V23 E016 Positive-Unlabeled Ranker Results

## Decision

**NO-GO for the V23 detector-native positive-unlabeled ranker.**

The preregistered local ownership-constraint shadow is therefore blocked. An
assignment layer cannot recover candidates that the detector-native ranker
does not surface, and no graph mutation or Track A change was permitted.

## Population and protocol

This was a sample-blocked, three-fold experiment over 27 samples and 46
registered events. It used 211,328 actions, including 55 official TP actions
and 569 official FP actions. Unknown and unsupported actions remained in every
held-out ranking pool but were never treated as negatives. Preprocessing and
regularization selection used training folds only.

## Primary retrieval

| Stratum | Action R@50 | Event R@50 | MRR |
|---|---:|---:|---:|
| Pooled | 0.5510 | 0.5897 | 0.1600 |
| Fold 1 | 0.8125 | 0.8571 | 0.2232 |
| Fold 2 | 0.3889 | 0.4615 | 0.1181 |
| Fold 3 | 0.3333 | 0.3846 | 0.1023 |
| 44b6 family | 0.0000 | 0.0000 | 0.0007 |
| 6bba family | 0.5745 | 0.6216 | 0.1668 |
| CFAR/bipartite | 0.0000 | 0.0000 | 0.0005 |
| Components/greedy | 0.7105 | 0.7188 | 0.2062 |

Local-maxima had one event and was reported descriptively only; it was not
eligible for a pooled GO decision.

## Baseline comparison

The best univariate baseline was `mean_daughter_contrast` with event R@50
`0.5641`. The fitted ranker reached `0.5897`, a delta of only `+0.0256`,
below the preregistered `+0.03` incremental threshold.

## Failed gates

- Pooled action/event R@50 thresholds
- Per-fold minimum and maximum fold-spread threshold
- CFAR action/event thresholds
- Components action/event thresholds
- Family minimum threshold
- Incremental advantage over the best univariate baseline
- Route-gap threshold

The pattern is structurally informative: detector-native appearance evidence
helps some components/6bba cases, but it does not generalize to CFAR or 44b6.
This is not evidence that ownership assignment is useless; it is evidence that
assignment is not the next bottleneck for this feature source.

## Closed next action

Do not run the local Hungarian shadow from this ranker. Do not fit a nonlinear
ranker, tune thresholds, alter candidate formation, or open the 199-sample
scope. The next V23 design decision requires a new detector-native source or a
route-specific representation that explains the CFAR/44b6 failure before any
assignment experiment is reconsidered.

Artifacts:

- Contract: `tests/fixtures/v23_e016_positive_unlabeled_ranker.json`
- Entrypoint: `scripts/run_v23_positive_unlabeled_ranker.py`
- Compact summary: `v23_e016_positive_unlabeled_ranker_summary.json`
- Positive ranks: local-only derived artifact
