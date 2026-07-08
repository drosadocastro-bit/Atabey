# V18 Coverage Forensics

## Objective

Determine whether the 3319 `unmapped_or_unevaluable` records from the V18 disagreement-first validation are mostly:

1. a real sparse-ground-truth coverage ceiling, or
2. a fixable prediction-to-GT matching / lookup failure.

This pass was read-only. It did not change `global_window_optimizer.py`, the disagreement runner, or the sparse GT matching code.

## Inputs

- `submissions/v18_disagreement_subset_validate.json`
- `submissions/v18_disagreement_subset_records.jsonl`
- `scripts/run_v18_coverage_forensics.py`
- output artifact: `submissions/v18_coverage_forensics.json`

The forensic classifier rebuilt the 50 at-risk samples used in the disagreement-first pass, then classified each unevaluable record using:

- strict same-frame GT proximity: `7.0um`
- relaxed same-frame GT proximity: `14.0um`
- adjacent-frame GT proximity checks for context

## Result

The dominant failure mode is real GT absence near the disputed detections, not optimizer logic.

| category | count | percent of 3319 | interpretation |
| --- | ---: | ---: | --- |
| `no_gt_nearby` | 2931 | 88.31% | No GT within `14um` in the same or adjacent frame around the source/candidate region. |
| `matching_lookup_failed_nearby_gt` | 373 | 11.24% | A nearby GT signal exists, but current evaluation lookup does not convert it into an evaluable mapping. |
| `mapped_but_target_unclaimed` | 15 | 0.45% | The source side is mapped and the expected GT successor exists, but the candidate link is still not claimed by the current lookup path. |
| `ambiguous_identity_region` | 0 | 0.00% | No dominant evidence that branching/merging ambiguity is driving this bucket. |
| `structural_incomplete` | 0 | 0.00% | No dominant evidence that missing graph structure explains this bucket. |

Breakdown of the 373 `matching_lookup_failed_nearby_gt` records:

| detail | count | percent of 3319 | percent of nearby-GT bucket |
| --- | ---: | ---: | ---: |
| `nearby_gt_only_within_relaxed_radius_radius_mismatch_candidate` | 313 | 9.43% | 83.91% |
| `nearby_gt_within_strict_radius_not_mapped_by_current_lookup` | 60 | 1.81% | 16.09% |

## Representative Evidence

### 1. Real sparse-GT ceiling dominates

Representative `no_gt_nearby` records show the nearest GT tens of microns away, which is far outside both the current `7um` match rule and the relaxed `14um` forensic band.

- `44b6_144b256d:t2:cf52`: nearest same-frame GT `80.50um`, nearest adjacent-frame GT `79.63um`
- `44b6_144b256d:t2:cf687`: nearest same-frame GT `69.46um`, nearest adjacent-frame GT `68.58um`
- `44b6_144b256d:t2:cf483`: nearest same-frame GT `59.59um`, nearest adjacent-frame GT `58.41um`

These are not close-call lookup misses. They are regions where the sparse annotation does not provide local evidence for either the greedy or global choice.

### 2. There is a real but bounded lookup / coverage-loss slice

The nearby-GT bucket is non-trivial, but it is much smaller than the true no-GT bucket.

Examples:

- `44b6_144b256d:t4:cf703` was classified as `nearby_gt_only_within_relaxed_radius_radius_mismatch_candidate`; the candidate had nearest same-frame GT at `12.16um`, inside the relaxed forensic band but outside the current strict match radius.
- `44b6_18ced818:t2:cf191` shows the same pattern; the greedy target had nearest same-frame GT at `10.57um`.
- `44b6_144b256d:t5:cf463` was classified as `nearby_gt_within_strict_radius_not_mapped_by_current_lookup`; the greedy/global target sat `4.00um` from GT `335000000009`, which means this is not just a loose-radius issue.

Interpretation:

- Most of this 373-record slice looks like radius sensitivity in the `7um` matching rule.
- A smaller subset looks like a real lookup / claiming failure even when a strict-radius GT candidate exists.

### 3. A tiny tail has mapped source and expected successor, but still no claimed candidate

The `mapped_but_target_unclaimed` bucket is only 15 records.

Example:

- `6bba_32db13fc:t5:cf326` has a mapped source, an expected GT successor (`7000280`), and only one source neighbor within radius, but the candidate sits `7.46um` from the nearest same-frame GT, narrowly outside the current strict rule.

This is evidence of evaluation fragility, but not enough volume to change the branch decision.

## Interpretation

The 99.5% unevaluable rate in the disagreement-first validation is primarily an evidence ceiling from sparse GT coverage, not a sign that the bounded global optimizer is obviously wrong or that the graph build is structurally broken.

The important nuance is that there is still a measurable evaluation-loss slice:

- `88.31%` of unevaluable records have no nearby GT even under the relaxed forensic search.
- `11.24%` have some nearby GT signal that the current evaluator does not convert into an outcome.
- only `1.81%` of the full unevaluable set show strict-radius nearby GT that still fails to map.

So the dominant explanation is sparse annotation coverage, but the current sparse matching pathway is also leaving some evidence on the table.

## Decision

`NO-GO` for promoting V18 bounded global optimization into the main graph build.

Reason:

- The disagreement-first pass already had only 33 evaluable records out of 3337 disagreements.
- This forensic pass shows that most of the missing evidence is not recoverable by optimizer changes.
- The remaining lookup-failure slice is real, but not large enough to justify changing V18 status in this branch.

Recommended branch position:

- keep V18 shadow-only
- record the evidence ceiling explicitly
- do not treat the current 5-0 mapped directional signal as promotion-grade evidence

## If We Reopen This Later

If a follow-up is warranted, it should target evaluation coverage, not optimizer logic.

Priority order:

1. Audit the sparse GT matching boundary in the `7um` to `14um` band.
2. Audit why a small strict-radius subset remains unclaimed despite nearby GT.
3. Re-run the disagreement-first validation only after that targeted evaluation audit.

The next investigation should not start by changing the V18 optimizer. The evidence says the bottleneck is mostly coverage, with a secondary matching-path sensitivity.