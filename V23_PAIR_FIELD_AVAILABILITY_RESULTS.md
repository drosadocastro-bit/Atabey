# V23 Pair-Conditioned 3D Field Availability Results

Decision: **NO_GO_CURRENT_E016_PAIR_FIELD_TRAINING**.

The proposed representation is a 33 x 33 x 33 isotropic field centered on the parent with two image frames, symmetric candidate masks, and an explicit crop-coverage mask. No coordinate scalar, model, crop tensor, assignment, or graph edit was created.

Representation availability: TP 100.0%; official FP 100.0%. TP unpadded crop coverage min/median/p10: 55.1%/100.0%/58.9%.

| Held-out fold | Train CFAR | Test CFAR | Train 44b6 | Test 44b6 | Train 6bba | Test 6bba |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7 | 0 | 3 | 0 | 23 | 14 |
| 2 | 3 | 4 | 1 | 2 | 26 | 11 |
| 3 | 4 | 3 | 2 | 1 | 25 | 12 |

## Gates

- PASS: `tp_representation_availability_min`
- PASS: `fp_representation_availability_min`
- FAIL: `cfar_positive_samples_min`
- FAIL: `each_family_positive_samples_min`
- FAIL: `each_fold_training_cfar_events_min`
- FAIL: `each_fold_heldout_cfar_events_min`
- FAIL: `each_fold_training_44b6_events_min`
- FAIL: `each_fold_heldout_44b6_events_min`

The image field is technically extractable, but the current E016 labels cannot support honest CFAR and 44b6 generalization. The next allowed step is a CFAR-native official-action availability census over the 66 routed samples, not model training.

Guardrail: unknown actions remain unknown. This result does not authorize crop extraction at scale, fitting, assignment, graph mutation, or a full-cohort evaluation.
