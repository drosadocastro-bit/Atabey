# V22 Route-Robust Temporal Semantic Evidence Audit Results

Decision: **NO_GO_TEMPORAL_SEMANTIC_EVIDENCE**

This is conditional discrimination among sampled official TP/FP actions, not biological truth or full-candidate precision.

## Availability

| Population | Completeness |
| --- | ---: |
| official TP actions | 1.000000 |
| official FP actions | 1.000000 |

## Best Evidence

- Best temporal feature: `minimum_daughter_contrast_emergence` AUC `0.804836`.
- Static baseline: `mean_daughter_contrast` AUC `0.817892`.
- Temporal advantage: `-0.013057`.

## Best Temporal Feature By Stratum

| Stratum | OOF event-balanced AUC |
| --- | ---: |
| fold 1 | 0.801324 |
| fold 2 | 0.783931 |
| fold 3 | 0.829252 |
| family 44b6 | 0.673189 |
| family 6bba | 0.815806 |
| cfar_sidelobe/bipartite | 0.739231 |
| components/greedy | 0.821212 |
| local_maxima/motion_mutual | 0.756410 |

Stable temporal features: `minimum_daughter_contrast_emergence`.

## Feature Families

| Family | Best OOF event-balanced AUC |
| --- | ---: |
| parent_transition | 0.581079 |
| daughter_emergence | 0.804836 |
| daughter_persistence | 0.697418 |
| temporal_conservation | 0.562138 |
| temporal_shape | 0.411109 |

## Frozen Gates

- PASS: `official_tp_descriptor_completeness_min`
- PASS: `official_fp_descriptor_completeness_min`
- FAIL: `temporal_feature_families_passing_min`
- PASS: `stable_temporal_feature_exists`
- FAIL: `best_temporal_auc_advantage_over_static_baseline_min`
- PASS: `source_graph_mutations_required`
- PASS: `assignment_decisions_required`

## Boundaries

- Unknown and unsupported actions were not negatives.
- Local-maxima is descriptive zero-shot evidence and cannot carry the decision.
- Fixed-coordinate temporal sampling used no future peak reassociation.
- No assignment, graph mutation, locked validation, or full-199 evaluation was used.
