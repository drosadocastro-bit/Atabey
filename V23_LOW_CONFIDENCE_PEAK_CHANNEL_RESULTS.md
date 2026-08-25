# V23 Low-Confidence Peak Channel Results

Decision: **HOLD_FOR_CONDITIONED_ROUTER_REVIEW**.

The frozen CFAR primary was unioned in shadow with a lower-confidence `(1,3,3)` echo-peak pool. Sparse GT was used only for registered fork availability; unrelated echo peaks were measured as candidate inflation, not labeled false positives.

| Profile | Recovered failures | Raw+echo geometry on production controls | Added/frame median | Added/frame p90 | Added/frame max |
|---|---:|---:|---:|---:|---:|
| `floor_0.35_k_0.80` | 7/7 | 4/4 | 706.0 | 1932.9 | 2324 |
| `floor_0.35_k_0.50` | 7/7 | 4/4 | 710.5 | 1935.5 | 2328 |
| `floor_0.30_k_0.80` | 7/7 | 4/4 | 872.5 | 2016.9 | 2521 |
| `floor_0.30_k_0.50` | 7/7 | 4/4 | 876.0 | 2021.4 | 2525 |
| `floor_0.25_k_0.80` | 7/7 | 4/4 | 962.0 | 2085.5 | 2644 |
| `floor_0.25_k_0.50` | 7/7 | 4/4 | 965.5 | 2091.8 | 2648 |
| `floor_0.35_k_1.10` | 6/7 | 3/4 | 693.0 | 1905.0 | 2300 |
| `floor_0.30_k_1.10` | 6/7 | 3/4 | 859.0 | 1986.4 | 2492 |
| `floor_0.25_k_1.10` | 6/7 | 3/4 | 947.0 | 2051.0 | 2611 |
| `floor_0.40_k_0.80` | 4/7 | 4/4 | 630.0 | 1817.3 | 2041 |
| `floor_0.40_k_0.50` | 4/7 | 4/4 | 634.5 | 1819.9 | 2045 |
| `floor_0.40_k_1.10` | 3/7 | 3/4 | 619.0 | 1791.4 | 2020 |
| `floor_0.45_k_0.80` | 2/7 | 4/4 | 582.5 | 1587.5 | 1668 |
| `floor_0.45_k_0.50` | 2/7 | 4/4 | 586.5 | 1590.0 | 1670 |
| `floor_0.45_k_1.10` | 1/7 | 3/4 | 574.0 | 1578.7 | 1644 |

Pareto profiles: `floor_0.45_k_1.10`, `floor_0.45_k_0.80`, `floor_0.40_k_1.10`, `floor_0.40_k_0.80`, `floor_0.35_k_1.10`, `floor_0.35_k_0.80`.

Production preservation remains 4/4 by construction because this is a non-mutating shadow. One production control lacks valid raw-peak geometry and is recovered by the unchanged watershed stage; the control column therefore reports raw+echo availability, not a production regression.

Guardrail: this result does not authorize production detections or graph mutation. Any retained profile must next be constrained by track prediction, temporal continuity, and ownership evidence.
