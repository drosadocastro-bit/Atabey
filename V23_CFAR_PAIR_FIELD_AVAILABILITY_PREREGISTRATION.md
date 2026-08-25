# V23 CFAR-Native Pair-Field Availability Preregistration

## Question

Can the frozen CFAR detector supply enough patched-official true division actions, across both families and deterministic sample-blocked folds, to support a later pair-conditioned 3D temporal-field experiment?

This is an availability census, not a scorer experiment. It does not extract crop tensors, fit a model, assign detections, or mutate a lineage graph.

## Frozen Population

- Intersect the 151 GT divisions in `v21_gt_division_distance_audit.csv` with the route labels already frozen in `v22_route_prevalence_199.json`.
- Include only `cfar_sidelobe/bipartite` samples.
- The population is fixed before outcomes are opened: 48 GT division events across 29 samples, with 14 `44b6` and 34 `6bba` events.
- Assign samples to three folds independently within each family by sorting a SHA-256 hash of `v23-cfar-pair-field|sample_id` and distributing round-robin. Availability outcomes must not rebalance the folds.

## Frozen Detector And Action Contract

- Reproduce the V19 pre-firewall detector exactly: frozen CFAR settings, watershed refinement enabled, `(1,5,5)` peak spacing, and the 900-detection cap.
- The production spike fallback cannot activate because its absolute trigger is 1,200 detections while the detector is capped at 900. Event-frame-only detection is therefore equivalent at this stage.
- Require parent and each daughter to lie within the patched official 7 um matching radius of the corresponding GT role.
- Require two distinct daughters and retain only pairs within the existing 14 um division-formation radius of the detected parent. This 14 um division-action gate is distinct from the frozen 9 um normal continuation-link gate.
- Project each isolated parent-to-two-daughter fork through Atabey's direct patched official scorer. An event is available only if at least one projected action is an official TP for that GT fork.
- Unsupported alternatives remain unknown. They are not easy negatives and are not counted as false positives by this census.

## Pair-Field Representation

The later representation remains frozen as a parent-centered 33 x 33 x 33 isotropic field at 1 um spacing with channels for image at `t`, image at `t+1`, parent mask, symmetric daughter-pair mask, and crop-coverage mask. Coordinate scalars are excluded.

This pass records representation availability and unpadded crop coverage for canonical official-positive actions, but does not extract image tensors.

## Gates

All gates must pass:

- at least 6 CFAR-positive samples overall;
- at least 3 positive samples in each family;
- for every held-out fold, at least 2 positive events from each family;
- for every training complement, at least 4 positive events from each family;
- at least 99% pair-field representation availability among official-positive actions.

Passing authorizes only a separate crop-extraction and validation contract. It does not authorize fitting, assignment, graph mutation, threshold tuning, or a full-199 model run.

## Fidelity Check

Before the census, the isolated event-frame detector was compared with the saved production coordinates for `44b6_706092f0` at `t=49`: 602 expected, 602 reproduced, with all 602 coordinates identical at six decimal places.
