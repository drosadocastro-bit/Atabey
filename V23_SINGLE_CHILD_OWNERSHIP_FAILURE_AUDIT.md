# V23 Single-Child Ownership Failure Audit

Decision: **READ-ONLY UPSTREAM DIAGNOSTIC**.

Population: the eight frozen `missing_single_child_anchor` events from the independent parent-isolation audit. GT is used only to label parent/daughter identity after the unchanged V19 graph is built.

| Event | Family | Registered parents | Outgoing counts | Nearest daughter ownership | Distinct daughters | Diagnosis |
|---|---|---:|---|---|---|---|
| 44b6_74d0c52e t58 | 44b6 | 1 | [0] | owned_by_other_parent, missing_detection | no | registered_parent_childless_daughter_claimed_elsewhere |
| 44b6_7a302da0 t90 | 44b6 | 3 | [2, 0, 2] | unowned, unowned | yes | registered_parent_has_multiple_children |
| 44b6_9be80b04 t77 | 44b6 | 2 | [0, 2] | owned_by_registered_parent, owned_by_registered_parent | yes | registered_parent_has_multiple_children |
| 44b6_c50204e0 t28 | 44b6 | 2 | [2, 0] | owned_by_registered_parent, owned_by_registered_parent | yes | registered_parent_has_multiple_children |
| 44b6_d2f34f90 t51 | 44b6 | 1 | [0] | missing_detection, missing_detection | no | registered_parent_childless_missing_daughter_detection |
| 6bba_05db0fb1 t24 | 6bba | 1 | [2] | owned_by_registered_parent, owned_by_registered_parent | yes | registered_parent_has_multiple_children |
| 6bba_207c6aaf t41 | 6bba | 2 | [0, 0] | unowned, owned_by_other_parent | yes | registered_parent_childless_daughter_claimed_elsewhere |
| 6bba_474be664 t63 | 6bba | 1 | [2] | owned_by_registered_parent, unowned | yes | registered_parent_has_multiple_children |

## Aggregate

- Diagnoses: `{'registered_parent_childless_daughter_claimed_elsewhere': 2, 'registered_parent_has_multiple_children': 5, 'registered_parent_childless_missing_daughter_detection': 1}`
- Nearest-daughter ownership states: `{'owned_by_other_parent': 2, 'missing_detection': 3, 'unowned': 4, 'owned_by_registered_parent': 7}`
- Events with two distinct nearest daughter detections: 6/8

Guardrail: this audit is descriptive only. It did not change candidates, edges, graph topology, thresholds, or routing.
