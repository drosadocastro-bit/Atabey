# V21 Track B Ranking Analysis

Track B-only ranking analysis. This does not mutate Track A and does not change which Track B candidates are logged.

## TP Rank Positions

| Sample | GT parent | Candidate parent | Rank | Ranking score | Reason | Density | Volume error | Intensity error |
| --- | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: |
| `6bba_05db0fb1` | `25000381` | `6bba_05db0fb1:t24:cf76` | 477 | 0.549436 | `fallback_broad_angle_balanced_split` | 3 | 1.000000 | 1.570535 |

## Ranking Capture

- Known TP candidates ranked: `1`.
- TPs in top 10: `0/1`.
- TPs in top 50: `0/1`.
- Worst TP rank: `477`.

## Feature Summary

### tp

- n: `1`
- ranking_score_median: `0.549436`
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
- ranking_score_median: `0.457916`
- geometry_score_median: `0.575912`
- angle_deg_median: `140.197060`
- distance_ratio_median: `1.522290`
- max_drift_deg_median: `13.124509`
- v_sep_1_um_per_frame_median: `0.983606`
- child_separation_um_median: `6.840628`
- local_density_t1_10um_median: `5.000000`
- volume_conservation_error_median: `1.000000`
- intensity_conservation_error_median: `0.945453`

### fp_all

- n: `2591`
- ranking_score_median: `0.464068`
- geometry_score_median: `0.581666`
- angle_deg_median: `139.865106`
- distance_ratio_median: `1.619487`
- max_drift_deg_median: `12.917358`
- v_sep_1_um_per_frame_median: `1.180313`
- child_separation_um_median: `7.210183`
- local_density_t1_10um_median: `5.000000`
- volume_conservation_error_median: `1.000000`
- intensity_conservation_error_median: `0.948243`

## Missed GT Divisions

| Sample | GT parent | Matched nodes | Reachable candidates | Accepted reachable | Rejected reachable | Diagnosis |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `6bba_05db0fb1` | `53001011` | `parent=False, child1=False, child2=True` | 0 | 0 | 0 | `sparse_gt_node_unmatched_to_prediction` |
| `6bba_05db0fb1` | `63001217` | `parent=False, child1=False, child2=False` | 0 | 0 | 0 | `sparse_gt_node_unmatched_to_prediction` |

## Assessment

This ranking is diagnostic. It should be judged by TP rank position and top-N capture, not by changing Track A or committing candidates as lineage edges.
