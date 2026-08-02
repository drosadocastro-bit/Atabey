# V23 Locked Pair-Field Dataset Results

Decision: **GO_TO_BOUNDED_PAIR_FIELD_MODEL_IMPLEMENTATION**.

The locked extractor labeled the complete bounded action universe through the patched official scorer and wrote parent fields only after readiness passed. No model was fit and no graph was mutated.

## Dataset

- parent fields: 54
- events: 29
- actions: 2264
- official TP: 90
- official FP: 2174
- unknown: 0
- selected training actions: 1603

## Readiness

- events containing TP and FP: 29
- family support: {'44b6': 9, '6bba': 20}
- outer-training complements: {'1': 20, '2': 17, '3': 21}

- PASS: `exact_tp_events`
- PASS: `exact_tp_action_variants`
- PASS: `events_with_tp_and_fp_overall`
- PASS: `events_with_tp_and_fp_per_family`
- PASS: `events_with_tp_and_fp_per_training_complement`

Tensor manifest valid: True.

This result authorizes implementation and fitting of the already preregistered bounded ranker only. Assignment and production graph mutation remain disabled.
