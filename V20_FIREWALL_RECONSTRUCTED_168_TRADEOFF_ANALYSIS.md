# V20 Firewall Reconstructed 168-Sample Trade-Off Analysis

Source: `v20_bipartite_firewall_199_RECONSTRUCTED_168.log`

Guardrail: this is measurement only. No firewall, detector, bipartite, angle, drift, or velocity thresholds were tuned.

## Cohort Scope

- Parsed complete samples: 168 / 199
- CFAR/firewall-active samples: 48 / 168
- Structurally unaffected samples: 120 / 168
- CFAR active split: 30 `6bba_*`, 18 `44b6_*`

Only the 48 `v20_firewall|bipartite` samples are used for firewall-specific FP reduction and trade-off interpretation. The other 120 samples routed through `components|greedy` or `local_maxima|motion_mutual`, so bipartite/firewall was not actually applicable there.

## Aggregate FP Reduction, CFAR-Only

| Metric | V19 FP | V20 FP | Absolute Reduction | Percent Reduction |
|---|---:|---:|---:|---:|
| n | 48 | 48 | 48 | 48 |
| mean | 7098.3333 | 616.2708 | 6482.0625 | 90.9356% |
| median | 6223.5000 | 549.0000 | 5607.0000 | 91.6374% |
| p10 | 3247.6000 | 236.7000 | 3008.1000 | 86.2498% |
| p25 | 4646.2500 | 346.5000 | 4353.5000 | 88.9371% |
| p75 | 9010.0000 | 808.5000 | 8139.2500 | 93.8496% |
| p90 | 12736.0000 | 1107.1000 | 11556.1000 | 94.4015% |
| min | 2343 | 152 | 2103 | 81.3024% |
| max | 16770 | 1582 | 15714 | 97.2452% |

Total aggregate FP reduction: 91.3181%.

Interpretation: the manually observed ~93-95% reduction is directionally real but slightly optimistic for the reconstructed 168-sample set. The median/p75/p90 reduction is in that band, but the mean is closer to 91% because several samples reduce less strongly. This is still a major FP suppression effect.

## V20 Residual FP Distribution, CFAR-Only

| V20 FP Band | Count | Share of CFAR-active |
|---|---:|---:|
| 0-5 | 0 | 0.0% |
| 6-99 | 0 | 0.0% |
| 100-499 | 20 | 41.7% |
| 500-999 | 21 | 43.8% |
| 1000+ | 7 | 14.6% |

Interpretation: the firewall is very effective as a noise reducer, but the small-sample calibration expectation of ~0-5 FP/sample does not generalize. Every CFAR-active sample still has at least 100 residual division false positives in this reconstructed set.

## Division Jaccard Reality Check

| Version | Total TP | Samples With TP > 0 | Total FP | Total FN |
|---|---:|---:|---:|---:|
| V13 | 0 | 0 | 0 | 141 |
| V19 | 3 | 3 | 340720 | 138 |
| V20 | 0 | 0 | 29581 | 141 |

CFAR-only TP signal:

| Version | Total TP | Samples With TP > 0 |
|---|---:|---:|
| V13 | 0 | 0 |
| V19 | 3 | 3 |
| V20 | 0 | 0 |

Interpretation: V20 removes essentially all true positive division-edge signal that V19 had, while still leaving substantial residual FP. For division scoring specifically, the current frozen firewall is not a win. It suppresses noise, but it is too strict or structurally misaligned with the true sparse division labels.

## EdgeRecall Delta

### All Parsed Samples

| Comparison | Improved | Flat | Regressed | Missing | Mean Delta | Median Delta | p90 Delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| V20 vs V13 | 41 | 120 | 6 | 1 | +0.0366 | 0.0000 | +0.1683 |
| V20 vs V19 | 44 | 121 | 3 | 0 | +0.0261 | 0.0000 | +0.1166 |

### CFAR/Firewall-Active Samples Only

| Comparison | Improved | Flat | Regressed | Missing | Mean Delta | Median Delta | p10 Delta | p90 Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V20 vs V13 | 41 | 0 | 6 | 1 | +0.1300 | +0.1192 | -0.0021 | +0.2740 |
| V20 vs V19 | 44 | 1 | 3 | 0 | +0.0914 | +0.0741 | +0.0026 | +0.2198 |

Largest CFAR V20-vs-V13 regressions:

| Sample | Delta | V13 EdgeRecall | V20 EdgeRecall | V19 FP | V20 FP |
|---|---:|---:|---:|---:|---:|
| 44b6_2a2eff9f | -0.0277 | 0.7684 | 0.7407 | 8852 | 1346 |
| 44b6_0db75fae | -0.0259 | 0.9172 | 0.8913 | 2343 | 240 |
| 6bba_5dfe9ad1 | -0.0228 | 0.8874 | 0.8646 | 3102 | 580 |
| 6bba_1f58c2f6 | -0.0227 | 0.7427 | 0.7200 | 5840 | 629 |
| 6bba_c73a1d11 | -0.0041 | 0.5813 | 0.5772 | 5785 | 329 |
| 6bba_6479435d | -0.0007 | 0.7348 | 0.7341 | 4605 | 474 |

Interpretation: the positive EdgeRecall side-effect is real in the reconstructed set and is strongest exactly where the firewall is active. This suggests the pruning is cleaning graph topology in a way that benefits general sparse edge matching, even though it fails to capture true division edges.

## Route Breakdown

| V20 Route | Count | Interpretation |
|---|---:|---|
| `components|greedy` | 100 | structurally unaffected |
| `local_maxima|motion_mutual` | 20 | structurally unaffected |
| `v20_firewall|bipartite` | 48 | firewall active |

Route conclusion: any whole-cohort average is diluted by the 120 unaffected samples. Firewall-specific conclusions should be based on the 48 active samples.

## Bottom-Line Assessment

This is a real partial win, not a division-detection win.

What is real:

- V20 reduces CFAR/bipartite division FP by 91.3% total and 91.6% median.
- V20 improves EdgeRecall on most CFAR-active samples: 41 improved vs 6 regressed against V13, and 44 improved vs 3 regressed against V19.
- The EdgeRecall improvement is large enough to treat the firewall as a useful topology-cleanup mechanism.

What is not real yet:

- V20 does not improve Division Jaccard.
- V20 recovered 0 division TP in the reconstructed 168-sample set.
- V19 had only 3 TP, but V20 removed even those.
- V20 residual FP remains high in every CFAR-active sample, with median 549 FP/sample.

Recommendation for the frozen ruleset:

- Keep the firewall concept as a topology/noise-control component.
- Do not claim it solves mitosis/division detection.
- Do not tune thresholds sample-by-sample.
- The next design question is structural: can we preserve the EdgeRecall/topology cleanup while adding a separate, more permissive true-division candidate path that recovers TP without reopening the V19-level FP flood?

Provisional go/no-go:

- GO as a graph-cleanup mechanism worth keeping for further experiments.
- NO-GO as a division-scoring improvement in its current frozen form.
- CONDITIONAL for submission only if aggregate official-style score benefits from EdgeRecall enough to outweigh the residual division FP/TP failure.

## Final 199-Sample Follow-Up

When the remaining 31 samples are available, merge them with this reconstructed log and rerun the same analysis. The key stability checks are:

- CFAR-active FP reduction remains near 90-92% total/median, or shifts toward the originally expected 93-95%.
- V20 TP remains 0 or near 0, versus any recovered true division positives in the remaining samples.
- CFAR-active EdgeRecall remains net positive against V13 and V19.
- The 31 missing samples, all `44b6_*`, do not introduce a qualitatively different firewall failure mode.
