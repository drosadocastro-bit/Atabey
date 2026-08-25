# V23 Pair-Field Metadata Preflight Results

Decision: **GO_TO_BOUNDED_PAIR_FIELD_MODEL_PREREGISTRATION**.

This pass enumerated metadata and exercised the tensor contract only on synthetic arrays. It wrote no real image tensor, fit no model, and mutated no graph.

## Population

- 29 positive events across 22 samples
- 54 unique cached parent fields
- 2264 full local candidate actions
- 90 patched-official TP action variants reproduced
- maximum 199 actions in one event

## Storage

- cached estimate: 0.029 GiB
- naive assembled estimate: 1.515 GiB
- estimated reduction from parent caching: 98.1%

## Gates

- PASS: `expected_positive_events`
- PASS: `expected_positive_action_variants`
- PASS: `official_metric_relabel_parity`
- PASS: `sample_blocked_folds`
- PASS: `both_families_each_fold`
- PASS: `synthetic_tensor_harness`
- PASS: `zero_tensor_writes`
- PASS: `zero_graph_mutation`
- PASS: `estimated_uncompressed_gib`
- PASS: `actions_per_event`
- PASS: `parent_fields`

A GO authorizes only a separate bounded model preregistration. Real tensor extraction remains disabled until that artifact is reviewed.

Guardrail: unsupported candidates remain unknown and no full-199 run is authorized.
