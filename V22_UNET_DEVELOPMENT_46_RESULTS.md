# V22 Temporal U-Net Full Development Shadow Results

Decision: **GO**

## Primary Gates

- Previously unavailable complete triplets: **23/25**.
- Official-positive controls preserved: **13/13**.
- Recovered families: **44b6, 6bba**.
- Unique event-frame U-Net/V19 peak ratio: median **1.200**, p90 **1.725**.
- Graph mutation: **False**.
- Edge inference: **False**.

## Gate Outcomes

- `availability`: **PASS**
- `controls`: **PASS**
- `families`: **PASS**
- `frame_ratio_median`: **PASS**
- `frame_ratio_p90`: **PASS**
- `zero_perturbation`: **PASS**

## Complete Triplets By Baseline Status

| status | complete | incomplete |
|---|---:|---:|
| `fewer_than_two_daughter_lineages_within_7um` | 12 | 0 |
| `no_pair_inside_14um_formation_radius` | 1 | 1 |
| `no_parent_detection_within_7um` | 10 | 1 |
| `official_positive` | 13 | 0 |
| `projected_actions_not_official_tp` | 6 | 2 |

## Complete Triplets By Family

| family | complete | incomplete |
|---|---:|---:|
| `44b6` | 3 | 3 |
| `6bba` | 39 | 1 |

## Interpretation Boundary

A complete triplet is detector availability, not an official division TP. This shadow does not evaluate learned edges, semantic division scoring, or production graph integration.
