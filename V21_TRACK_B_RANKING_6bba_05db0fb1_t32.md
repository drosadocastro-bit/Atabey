# V21 Track B Ranking Analysis

Track B-only ranking analysis. This does not mutate Track A and does not change which Track B candidates are logged.

## TP Rank Positions

| Sample | GT parent | Candidate parent | Rank | Ranking score | Reason | Density | Volume error | Intensity error |
| --- | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: |
| `6bba_05db0fb1` | `25000381` | `6bba_05db0fb1:t24:cf76` | 10 | 0.754457 | `fallback_broad_angle_balanced_split` | 3 | 1.000000 | 1.570535 |

## Ranking Capture

- Known TP candidates ranked: `1`.
- TPs in top 10: `1/1`.
- TPs in top 50: `1/1`.
- Worst TP rank: `10`.

## Feature Summary

### tp

- n: `1`
- ranking_score_median: `0.754457`
- geometry_score_median: `0.723697`
- angle_deg_median: `135.895743`
- distance_ratio_median: `1.109479`
- max_drift_deg_median: `NA`
- v_sep_1_um_per_frame_median: `NA`
- child_separation_um_median: `12.643561`
- local_density_t1_10um_median: `3.000000`
- volume_conservation_error_median: `1.000000`
- intensity_conservation_error_median: `1.570535`

### fp_sample

- n: `100`
- ranking_score_median: `0.507449`
- geometry_score_median: `0.564235`
- angle_deg_median: `139.552228`
- distance_ratio_median: `1.621217`
- max_drift_deg_median: `12.943288`
- v_sep_1_um_per_frame_median: `1.187287`
- child_separation_um_median: `7.529209`
- local_density_t1_10um_median: `5.000000`
- volume_conservation_error_median: `1.000000`
- intensity_conservation_error_median: `1.005735`

### fp_all

- n: `1039`
- ranking_score_median: `0.501078`
- geometry_score_median: `0.565158`
- angle_deg_median: `138.888700`
- distance_ratio_median: `1.677943`
- max_drift_deg_median: `13.183335`
- v_sep_1_um_per_frame_median: `1.203221`
- child_separation_um_median: `7.729550`
- local_density_t1_10um_median: `5.000000`
- volume_conservation_error_median: `1.000000`
- intensity_conservation_error_median: `0.954710`

## Missed GT Divisions

| Sample | GT parent | Matched nodes | Reachable candidates | Accepted reachable | Rejected reachable | Diagnosis |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `6bba_05db0fb1` | `53001011` | `parent=False, child1=False, child2=False` | 0 | 0 | 0 | `sparse_gt_node_unmatched_to_prediction` |
| `6bba_05db0fb1` | `63001217` | `parent=False, child1=False, child2=False` | 0 | 0 | 0 | `sparse_gt_node_unmatched_to_prediction` |

## Assessment

This ranking is diagnostic. It should be judged by TP rank position and top-N capture, not by changing Track A or committing candidates as lineage edges.
