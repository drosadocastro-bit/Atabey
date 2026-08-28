# V24.3 Full-199 Regression Forensics

Date: 2026-08-27

Status: **read-only causal decomposition complete; automatic fallback not authorized**.

This audit examines the 16 samples where frozen V24.3 scored below V19 in the
complete 199-sample validation. It does not tune or mutate either graph.

## Cohort Localization

All 16 regressions share the same route:

- family: `6bba`
- V19 detector: `components`
- V19 linker: `greedy`

Fifteen are in the checkpoint-training 172 stratum. The only held-out case is
`6bba_3c5691b6`, previously observed at -0.027854. The 108-sample
`components + greedy` route still contains 92 V24.3 wins, so route identity
alone cannot justify fallback to V19.

## Verified Mechanisms

Six cases are **association losses**: V24.3 has fewer true-positive edges and
more false-positive edges than V19. These include all four catastrophic
regressions. Ten cases are **precision tradeoffs**: V24.3 recovers more true
edges but adds still more false-positive edges. Fourteen cases regress in raw
edge Jaccard. In `6bba_b204cac7` and `6bba_ed9377fd`, raw edge Jaccard improves,
but the adjusted metric falls after node-count adjustment.

| Sample | Mechanism | Adj. delta | TP delta | FP delta | Node delta |
|---|---|---:|---:|---:|---:|
| `6bba_2646afc7` | association loss | -0.217286 | -54 | +115 | +2259 |
| `6bba_2540cd90` | association loss | -0.185074 | -45 | +53 | +616 |
| `6bba_76db78c1` | association loss | -0.136909 | -17 | +68 | +1755 |
| `6bba_d5eae175` | association loss | -0.106688 | -22 | +32 | +886 |
| `6bba_718b21f9` | association loss | -0.090216 | -25 | +48 | -17 |
| `6bba_5f89039d` | association loss | -0.078020 | -36 | +38 | +387 |
| `6bba_d0fc38b5` | precision tradeoff | -0.066002 | +25 | +82 | +1484 |
| `6bba_5b28472a` | precision tradeoff | -0.049051 | +9 | +32 | +1572 |
| `6bba_96833384` | precision tradeoff | -0.037991 | +38 | +65 | +1549 |
| `6bba_372c8cb8` | precision tradeoff | -0.034311 | +25 | +61 | +889 |
| `6bba_05b6850b` | precision tradeoff | -0.033846 | +48 | +64 | +2771 |
| `6bba_fc516dc6` | precision tradeoff | -0.032441 | +17 | +32 | +2516 |
| `6bba_23af9eeb` | precision tradeoff | -0.031215 | +38 | +53 | +1382 |
| `6bba_3c5691b6` | precision tradeoff | -0.027854 | +50 | +71 | +1648 |
| `6bba_b204cac7` | adjustment-only tradeoff | -0.009445 | +44 | +21 | +2377 |
| `6bba_ed9377fd` | adjustment-only tradeoff | -0.004443 | +37 | +38 | +1146 |

Division handling is not causal: 14 cases have no division events, and the two
cases with division false negatives have identical V19 and V24.3 division
counts.

The dominant failure is upstream of V24.3: the E016 detection plus
motion-mutual relink path is less edge-precise than the specialized V19
component plus greedy path on this stratum. The retained artifacts do not
contain edge coordinates or candidate margins, so exact edge-level mislink
causes cannot be inferred without new telemetry.

## Existing Containment Benefit

The two bounded pruning stages already contain, rather than cause, this cohort:

- V24.2 scores above unpruned E016 relink on all 16 cases.
- V24.3 scores above V24.2 on all 16 cases.
- Mean adjusted score rises from 0.709385 (relink) to 0.757283 (V24.2) to
  0.779985 (V24.3), versus 0.851285 for V19.

More aggressive short-component pruning is therefore unsupported.

## Runtime-Observable Signals

Simple graph-count thresholds do not isolate the regressions:

- V24.3/V19 node ratio above 1.25 catches 12 of 16 regressions but also flags
  58 winning samples and misses one catastrophic case.
- V24.3/V19 edge ratio above 1.25 catches 15 of 16 but also flags 82 winners.
- The short-fragment removal fraction is not elevated in the regression cohort.

A post-hoc **review-only** signal is:

```text
family == 6bba
and V19 route == components + greedy
and (V24.3 edges / V24.3 nodes) / (V19 edges / V19 nodes) <= 1.15
```

It flags 17 of 199 samples, catches 10 of 16 regressions and all four
catastrophic cases, but also flags 7 winners. The flagged winners retain a
positive aggregate V24.3 delta, so replacing all flagged outputs with V19 would
remove legitimate gains. The threshold was observed after opening the full-199
labels and has no untouched validation cohort.

## Containment Decision

1. Keep V24.3 frozen; do not add more pruning.
2. Keep submission unauthorized.
3. Use the low-density disagreement condition only to prioritize human review
   or a read-only telemetry rerun. Do not use it as an automatic selector.
4. Before any selector is considered, collect edge-length, mutuality-conflict,
   nearest-versus-second-nearest margin, and unmatched-detection telemetry on
   the flagged cohort.
5. An automatic V19/V24.3 routing rule requires a new preregistered validation
   design. All 199 labeled samples are now opened, so this repository currently
   has no untouched labeled cohort for an unbiased selector claim.
