# V23 CFAR Route Decision Audit

## Recommendation

**Do not remove CFAR yet. Quarantine it from pooled semantic GO claims and
redesign or audit it as a route-specific detector.**

The V23 ranker failure is strong evidence that the current detector-native
appearance representation does not generalize to CFAR. It is not evidence
that CFAR is disposable.

## Cohort prevalence

The read-only route census across all 199 samples reports:

| Route | Samples | Share |
|---|---:|---:|
| CFAR/sidelobe + bipartite | 66 | 33.2% |
| Components + greedy | 108 | 54.3% |
| Local maxima + motion mutual | 25 | 12.6% |

CFAR is especially concentrated in the 44b6 family: 36 of its samples use
CFAR, compared with 30 in 6bba. Removing it would change a third of the
cohort and disproportionately affect 44b6.

## Development impact

Within the frozen V23 E016 development population:

| Route | Actions | Official TP actions | Official FP actions | TP events |
|---|---:|---:|---:|---:|
| CFAR/bipartite | 159,812 | 11 | 101 | 7 |
| Components/greedy | 40,199 | 38 | 373 | 32 |
| Local maxima | 11,317 | 6 | 95 | 1 |

CFAR contributes approximately 75.6% of all actions but only 20% of the
official TP actions in this development split. That imbalance explains why a
pooled appearance ranker can be dominated by CFAR candidate density while
still failing to surface its positives.

## V23 evidence

The detector-native ranker achieved:

- CFAR action R@50: `0.0000`
- CFAR event R@50: `0.0000`
- Components action R@50: `0.7105`
- Components event R@50: `0.7188`

This is a route-specific representation failure, not a demonstrated failure
of bipartite ownership logic. The ranker was blocked before assignment, so no
claim about Hungarian constraints can be made from this result.

## Decision boundary

CFAR is now **quarantined from pooled GO claims**, but not deleted:

- no pooled ranker or production change may treat CFAR as generalized;
- no full-199 run may be interpreted as improved while CFAR is unvalidated;
- CFAR needs a route-specific detector-native representation or a separate
  availability/quality audit;
- components may continue as a research control, not as proof that CFAR can be
  replaced safely.

The next cheap experiment should compare CFAR-specific evidence sources,
starting with detector logits/peak margins and local patch descriptors, using
the same sample-blocked and positive-unlabeled protocol. Only a demonstrated
CFAR alternative with preserved official-positive availability could justify
retiring or bypassing CFAR.
