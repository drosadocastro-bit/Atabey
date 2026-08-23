# V20 Firewall Cohort Analysis

Guardrail: this report is pure measurement and classification of the frozen V20 firewall ruleset. No thresholds were tuned.

Source log: `D:\Project-Atabey\v20_bipartite_firewall_199_RECONSTRUCTED_168.log`
Parsed samples: 168

## Aggregate Distributions

| Version | Metric | n | mean | median | p10 | p90 |
|---|---:|---:|---:|---:|---:|---:|
| V13 | division_jaccard | 78 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| V13 | edge_recall | 167 | 0.7871 | 0.8231 | 0.5946 | 0.9456 |
| V13 | division_fp | 168 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| V19 | division_jaccard | 102 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| V19 | edge_recall | 168 | 0.7986 | 0.8260 | 0.6113 | 0.9456 |
| V19 | division_fp | 168 | 2028.0952 | 0.0000 | 0.0000 | 7183.0000 |
| V20 (Bipartite) | division_jaccard | 102 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| V20 (Bipartite) | edge_recall | 168 | 0.8247 | 0.8425 | 0.6849 | 0.9528 |
| V20 (Bipartite) | division_fp | 168 | 176.0774 | 0.0000 | 0.0000 | 674.9000 |

## V20 FP-Per-Sample Distribution

All parsed V20 samples: n=168, mean=176.0774, median=0.0000, p10=0.0000, p90=674.9000
Firewall-active samples only: n=48, mean=616.2708, median=549.0000, p10=236.7000, p90=1107.1000
Near expected calibration band, FP 0-5: 0 / 48 active samples
Intermediate residual, FP 6-99: 0 / 48 active samples
High residual outliers, FP >=100: 48 / 48 active samples

## Behavior Buckets

Primary buckets are mutually exclusive. High residual FP and meaningful FP reduction are also tracked separately because they can overlap.

| Bucket | Count | Percent |
|---|---:|---:|
| no_cfar_or_firewall_not_applicable | 120 | 71.4% |
| firewall_insufficient_high_residual | 48 | 28.6% |

Meaningful V19->V20 FP reduction among firewall-active samples: 48 / 48
High residual FP among firewall-active samples: 48 / 48

## Route Confirmation

### V13
- `components|greedy`: 100
- `local_maxima|motion_mutual`: 68

### V19
- `components|greedy`: 100
- `cfar_sidelobe|bipartite`: 48
- `local_maxima|motion_mutual`: 20

### V20 (Bipartite)
- `components|greedy`: 100
- `v20_firewall|bipartite`: 48
- `local_maxima|motion_mutual`: 20

## Edge Recall Net Impact

V20 vs V13: improved=41, flat=120, regressed=6, missing=1
V20 vs V19: improved=44, flat=121, regressed=3, missing=0
V20-V13 Edge Recall delta distribution: n=167, mean=0.0366, median=0.0000, p10=0.0000, p90=0.1683
V20-V19 Edge Recall delta distribution: n=168, mean=0.0261, median=0.0000, p10=0.0000, p90=0.1166

## Division TP Signal

- V13: total TP=0, samples with TP>0=0, total FP=0, total FN=141
- V19: total TP=3, samples with TP>0=3, total FP=340720, total FN=138
- V20 (Bipartite): total TP=0, samples with TP>0=0, total FP=29581, total FN=141

## High-FP Outlier Correlates

### Cohort Prefix
| Prefix | Active samples | High-FP samples | High-FP rate |
|---|---:|---:|---:|
| 44b6 | 18 | 18 | 100.0% |
| 6bba | 30 | 30 | 100.0% |

### Density Proxies From Log Metrics

This log includes per-sample predicted node counts, so V20 nodes are included as a density proxy. Edge counts and raw image density are not present in the log.
- Firewall active V19 division FP: n=48, mean=7098.3333, median=6223.5000, p10=3247.6000, p90=12736.0000
- Firewall active V20 division FP: n=48, mean=616.2708, median=549.0000, p10=236.7000, p90=1107.1000
- Firewall active V20 predicted nodes: n=48, mean=14263.7708, median=13491.0000, p10=6902.3000, p90=23118.1000
- High residual FP V19 division FP: n=48, mean=7098.3333, median=6223.5000, p10=3247.6000, p90=12736.0000
- High residual FP V20 division FP: n=48, mean=616.2708, median=549.0000, p10=236.7000, p90=1107.1000
- High residual FP V20 predicted nodes: n=48, mean=14263.7708, median=13491.0000, p10=6902.3000, p90=23118.1000

### Top V20 Residual-FP Samples

| Sample | Bucket | Prefix | V19 FP | V20 FP | V20 Edge Recall | V20 route |
|---|---|---|---:|---:|---:|---|
| 44b6_e31261b4 | firewall_insufficient_high_residual | 44b6 | 12476 | 1582 | 0.8784 | `v20_firewall|bipartite` |
| 6bba_767a1e17 | firewall_insufficient_high_residual | 6bba | 12806 | 1576 | 0.7653 | `v20_firewall|bipartite` |
| 44b6_2a2eff9f | firewall_insufficient_high_residual | 44b6 | 8852 | 1346 | 0.7407 | `v20_firewall|bipartite` |
| 44b6_eb2880fc | firewall_insufficient_high_residual | 44b6 | 6157 | 1151 | 0.8796 | `v20_firewall|bipartite` |
| 44b6_cf2536e8 | firewall_insufficient_high_residual | 44b6 | 8999 | 1140 | 0.8421 | `v20_firewall|bipartite` |
| 44b6_66f9292d | firewall_insufficient_high_residual | 44b6 | 6885 | 1093 | 0.8333 | `v20_firewall|bipartite` |
| 44b6_18ced818 | firewall_insufficient_high_residual | 44b6 | 16770 | 1056 | 0.7037 | `v20_firewall|bipartite` |
| 6bba_b329af44 | firewall_insufficient_high_residual | 6bba | 10061 | 968 | 0.7890 | `v20_firewall|bipartite` |
| 6bba_ebdf3b34 | firewall_insufficient_high_residual | 6bba | 7093 | 950 | 0.7922 | `v20_firewall|bipartite` |
| 6bba_05db0fb1 | firewall_insufficient_high_residual | 6bba | 9063 | 821 | 0.7753 | `v20_firewall|bipartite` |
| 44b6_c50204e0 | firewall_insufficient_high_residual | 44b6 | 13775 | 811 | 0.7143 | `v20_firewall|bipartite` |
| 44b6_e35b117d | firewall_insufficient_high_residual | 44b6 | 14613 | 810 | 0.8280 | `v20_firewall|bipartite` |
| 6bba_32db13fc | firewall_insufficient_high_residual | 6bba | 6022 | 808 | 0.7367 | `v20_firewall|bipartite` |
| 6bba_f8ffd5e7 | firewall_insufficient_high_residual | 6bba | 5397 | 784 | 0.7578 | `v20_firewall|bipartite` |
| 44b6_144b256d | firewall_insufficient_high_residual | 44b6 | 6218 | 758 | 0.7447 | `v20_firewall|bipartite` |
| 6bba_57b7cc1e | firewall_insufficient_high_residual | 6bba | 14750 | 684 | 0.7911 | `v20_firewall|bipartite` |
| 6bba_edf14583 | firewall_insufficient_high_residual | 6bba | 7393 | 677 | 0.8848 | `v20_firewall|bipartite` |
| 6bba_3abfe10a | firewall_insufficient_high_residual | 6bba | 9043 | 674 | 0.8238 | `v20_firewall|bipartite` |
| 6bba_1f58c2f6 | firewall_insufficient_high_residual | 6bba | 5840 | 629 | 0.7200 | `v20_firewall|bipartite` |
| 44b6_ddf577ad | firewall_insufficient_high_residual | 44b6 | 5067 | 605 | 0.7958 | `v20_firewall|bipartite` |
| 6bba_5dfe9ad1 | firewall_insufficient_high_residual | 6bba | 3102 | 580 | 0.8646 | `v20_firewall|bipartite` |
| 6bba_78a7bd97 | firewall_insufficient_high_residual | 6bba | 10499 | 562 | 0.6900 | `v20_firewall|bipartite` |
| 44b6_e57ff5c6 | firewall_insufficient_high_residual | 44b6 | 6988 | 558 | 0.7612 | `v20_firewall|bipartite` |
| 6bba_786893ac | firewall_insufficient_high_residual | 6bba | 8656 | 551 | 0.7764 | `v20_firewall|bipartite` |
| 44b6_d5e7d891 | firewall_insufficient_high_residual | 44b6 | 9128 | 547 | 0.7634 | `v20_firewall|bipartite` |

## Recommendation

NO-GO for treating the current firewall as a division-scoring improvement: it produced no confirmed division TP signal while leaving high-FP residuals in a meaningful share of active samples.

