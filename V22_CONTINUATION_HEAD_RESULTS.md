# V22 Out-of-Fold Continuation Head Results

Decision: **GO_TO_JOINT_SEMANTIC_SHADOW**

> **Interpretation correction:** the mandatory teacher-feature ablation was proxy-preserving, not teacher-independent. Retained distance/speed/angle features deterministically reconstruct `prediction_error_um` and correlate strongly with the other removed teacher features. The GO applies only to weak-reference imitation consistency; see `V22_CONTINUATION_TEACHER_PROXY_AUDIT.md`.

This is weak-reference imitation evidence, not biological continuation validation. No assignment was run and no graph was mutated.

## Full Model

| Stratum | Samples | Top-1 | Pairwise | MRR |
| --- | ---: | ---: | ---: | ---: |
| pooled decision routes | 26 | 0.999109675 | 0.999819615 | 0.999554837 |
| fold 1 | 9 | 0.999006406 | 0.999806668 | 0.999503203 |
| fold 2 | 9 | 0.999301808 | 0.999882327 | 0.999650904 |
| fold 3 | 8 | 0.999009703 | 0.999763627 | 0.999504852 |
| cfar_sidelobe/bipartite | 7 | 0.997141090 | 0.999447610 | 0.998570545 |
| components/greedy | 19 | 0.999834943 | 0.999956669 | 0.999917472 |
| 1|cfar_sidelobe/bipartite | 3 | 0.997135931 | 0.999478361 | 0.998567966 |
| 1|components/greedy | 6 | 0.999941643 | 0.999970822 | 0.999970822 |
| 2|cfar_sidelobe/bipartite | 3 | 0.998316945 | 0.999784157 | 0.999158473 |
| 2|components/greedy | 6 | 0.999794239 | 0.999931413 | 0.999897119 |
| 3|cfar_sidelobe/bipartite | 1 | 0.993628998 | 0.998345716 | 0.996814499 |
| 3|components/greedy | 7 | 0.999778376 | 0.999966186 | 0.999889188 |
| local_maxima/motion_mutual (zero-shot; unproven generalization; excluded from GO) | 1 | 0.984717129 | 0.998191109 | 0.992293187 |

## Teacher-Feature Ablation

| Stratum | Samples | Top-1 | Pairwise | MRR |
| --- | ---: | ---: | ---: | ---: |
| pooled decision routes | 26 | 0.996281230 | 0.999047620 | 0.998113423 |
| fold 1 | 9 | 0.996917707 | 0.999418290 | 0.998456997 |
| fold 2 | 9 | 0.995716257 | 0.998610071 | 0.997832031 |
| fold 3 | 8 | 0.996200789 | 0.999122859 | 0.998043468 |
| cfar_sidelobe/bipartite | 7 | 0.993119455 | 0.998812386 | 0.996515969 |
| components/greedy | 19 | 0.997446095 | 0.999134285 | 0.998701959 |

## Frozen Decision Gates

- PASS: `pooled_reference_top1_min`
- PASS: `each_fold_reference_top1_min`
- PASS: `reference_top1_max_fold_spread`
- PASS: `pooled_pairwise_accuracy_min`
- PASS: `each_fold_pairwise_accuracy_min`
- PASS: `pairwise_accuracy_max_fold_spread`
- PASS: `each_fold_mrr_min`
- PASS: `maximum_fold_drop_from_other_two_mean`
- PASS: `each_route_reference_top1_min`
- PASS: `each_route_pairwise_accuracy_min`
- PASS: `reference_top1_max_route_gap`
- PASS: `pairwise_accuracy_max_route_gap`
- PASS: `each_route_fold_reference_top1_min`
- PASS: `maximum_route_fold_drop_from_route_oof`

## Flagged Concerns

- clear: `reference_top1_fold_spread`
- clear: `pairwise_accuracy_fold_spread`
- clear: `fold_drop_from_other_two_mean`
- clear: `reference_top1_route_gap`
- clear: `pairwise_accuracy_route_gap`
- clear: `route_fold_drop_from_route_oof`

## Boundaries

- Local-maxima is zero-shot-only in held-out fold 3 and cannot carry the pooled decision.
- The ablation is mandatory diagnostic evidence; the frozen GO/HOLD/NO_GO call is made on the preregistered full model.
- `assignment_enabled=false`, `graph_mutated=false`, and `full_199_authorized=false`.
