# V22 Official-Positive Semantic Evidence Audit Results

Decision: **GO_TO_POSITIVE_UNLABELED_RANKER_PREREGISTRATION**

This is conditional discrimination among sampled official TP/FP actions, not biological truth or full-candidate precision.

## Availability

| Population | Completeness |
| --- | ---: |
| peaks | 1.000000 |
| official TP actions | 1.000000 |
| official FP actions | 1.000000 |

## Best Evidence

- Best confidence baseline: `mean_detection_confidence` AUC `0.607822`.
- Best raw feature: `mean_daughter_contrast` AUC `0.817892`.
- Raw advantage: `+0.210070`.

## Best Raw Feature By Stratum

| Stratum | OOF event-balanced AUC |
| --- | ---: |
| fold 1 | 0.740653 |
| fold 2 | 0.845190 |
| fold 3 | 0.867834 |
| family 44b6 | 0.669816 |
| family 6bba | 0.830232 |
| cfar_sidelobe/bipartite | 0.569036 |
| components/greedy | 0.874415 |
| local_maxima/motion_mutual | 0.807692 |

Stable raw features: `minimum_daughter_contrast, mean_daughter_contrast, contrast_conservation_error, daughter_mass_balance, mean_daughter_anisotropy`.

## Feature Groups

| Group | Best OOF event-balanced AUC |
| --- | ---: |
| contrast | 0.817892 |
| mass | 0.686959 |
| shape | 0.682868 |
| volume | 0.655963 |

## Frozen Gates

- PASS: `best_raw_auc_advantage_over_best_confidence_min`
- PASS: `official_fp_action_completeness_min`
- PASS: `official_tp_action_completeness_min`
- PASS: `peak_descriptor_completeness_min`
- PASS: `raw_feature_groups_passing_min`
- PASS: `stable_raw_feature_exists`

## Boundaries

- Unknown and unsupported actions were not negatives.
- Local-maxima is descriptive only and cannot carry the decision.
- CFAR is the weakest supported route and should remain an explicit generalization watchpoint.
- No model, assignment, graph mutation, locked validation, or full-199 evaluation was used.
