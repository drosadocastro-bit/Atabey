# V22 Proxy-Resistant Continuation Gate Results

Decision: **NO_GO_INDEPENDENT_DENSITY_SIGNAL**

This development-only result measures weak-reference compatibility, not biological continuation truth. No assignment or graph mutation occurred.

## Pooled Comparison

| Model | Top-1 | Pairwise | MRR |
| --- | ---: | ---: | ---: | ---: |
| density only | 0.311385307 | 0.516963353 | 0.560392713 |
| nearest distance | 0.996515679 | 0.999388799 | 0.998219677 |
| distance plus density | 0.994550347 | 0.999089576 | 0.997187104 |

Random-within-group expected top-1: `0.304732857`; density-only advantage: `+0.006652450`.

## Density-Only Fold And Route Results

| Stratum | Top-1 | Pairwise | MRR |
| --- | ---: | ---: | ---: | ---: |
| fold 1 | 0.317543795 | 0.538641448 | 0.561006341 |
| fold 2 | 0.274901913 | 0.495056458 | 0.529352944 |
| fold 3 | 0.345500826 | 0.517220752 | 0.594622122 |
| cfar_sidelobe/bipartite | 0.221041922 | 0.610900460 | 0.440461110 |
| components/greedy | 0.344669712 | 0.482354945 | 0.604578041 |

## Incremental Fold And Route Results

| Stratum | Nearest top-1 | Hybrid top-1 | Delta |
| --- | ---: | ---: | ---: |
| fold 1 | 0.995451598 | 0.994517885 | -0.000933713 |
| fold 2 | 0.996789278 | 0.995623894 | -0.001165385 |
| fold 3 | 0.997404973 | 0.993379126 | -0.004025847 |
| cfar_sidelobe/bipartite | 0.987058237 | 0.986478279 | -0.000579958 |
| components/greedy | 1.000000000 | 0.997524266 | -0.002475734 |

## Frozen Gates

- FAIL: `density_only_pairwise_accuracy_min`
- FAIL: `density_only_top1_advantage_over_random_min`
- FAIL: `folds_with_positive_top1_delta_min`
- PASS: `hybrid_existing_hard_gates`
- PASS: `hybrid_no_existing_generalization_flags`
- FAIL: `minimum_fold_top1_delta`
- PASS: `minimum_route_top1_delta`
- FAIL: `pooled_pairwise_delta_over_nearest_min`
- FAIL: `pooled_top1_delta_over_nearest_min`
- FAIL: `routes_with_nonnegative_top1_delta_min`

## Boundary

- Local-maxima is excluded from the decision and remains unproven generalization.
- A GO would authorize only the development joint-assignment shadow.
- `assignment_enabled=false`, `graph_mutated=false`, and `full_199_authorized=false`.
