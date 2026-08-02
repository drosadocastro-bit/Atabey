# V23 CFAR-Native Pair-Field Availability Results

Decision: **GO_TO_CFAR_PAIR_FIELD_EXTRACTION_CONTRACT**.

This is a bounded availability result, not evidence that a pair-field model will rank divisions correctly. It authorizes only the next crop-extraction and validation contract. No crop tensor was extracted, no model was fit, no assignment was made, and no production graph was mutated.

## Fidelity And Population

- The isolated CFAR + watershed detector reproduced a saved production frame exactly: 602/602 coordinates for `44b6_706092f0` at `t=49`.
- The frozen detector cap is 900, below the production spike guardrail's 1,200 absolute trigger, so the event-frame detector stage cannot diverge through that fallback.
- The pre-registered population contained 48 known GT division events across 29 CFAR-routed samples: 14 `44b6` events and 34 `6bba` events.
- Candidate forks were evaluated by the directly integrated patched official scorer at 7 um. The 14 um division-formation bound remained separate from the frozen 9 um ordinary continuation-link gate.

## Availability

| Stratum | Official-positive events | Source events | Positive samples | Source samples |
|---|---:|---:|---:|---:|
| Overall | 29 | 48 | 22 | 29 |
| `44b6` | 9 | 14 | 8 | 11 |
| `6bba` | 20 | 34 | 14 | 18 |

Event availability was 60.4% overall, 64.3% for `44b6`, and 58.8% for `6bba`. Sample coverage was 75.9% overall. The 29 available events yielded 90 official-TP action variants; these are scorer-recognized geometric alternatives around 29 biological events, not 90 independent positive events. Future fitting must weight events or samples rather than raw action multiplicity.

## Failure Anatomy

The 19 unavailable events broke down as:

- 9 with no parent detection within the official 7 um radius;
- 7 with at least one daughter missing within 7 um;
- 1 where both daughter roles mapped only to the same detection, leaving no distinct pair;
- 2 with detections for all roles but no pair surviving the 14 um formation bound;
- 0 projected formed actions rejected by the patched official scorer.

This cleanly separates the new representation question from the remaining upstream problem. Once the correct distinct parent/daughter triplet exists, every formed candidate set in this census contained at least one official TP. The unavailable events are still detector identity or formation failures and must not become easy negatives for the pair-field learner.

## Fold Support

The deterministic sample-blocked folds were assigned before outcomes were opened.

| Held-out fold | Test 44b6 events | Test 6bba events | Train 44b6 events | Train 6bba events |
|---:|---:|---:|---:|---:|
| 1 | 2 | 7 | 7 | 13 |
| 2 | 4 | 8 | 5 | 12 |
| 3 | 3 | 5 | 6 | 15 |

Every fold satisfies the pre-registered minimums of at least 2 held-out and 4 training-complement positive events per family. All five gates pass.

## Representation Boundary

Pair-field representation availability was 100% for the canonical positive actions. Unpadded crop coverage had min/p10/median of 51.7%/70.7%/100%; the explicit crop-coverage channel remains mandatory so boundary padding is observable rather than hidden.

The next artifact should freeze extraction, controls, weighting, and evaluation before any tensors are generated. Mandatory controls remain mask-only, image-shuffled, static-image, and geometry-only. A later model must beat those controls across all folds and both families; pooled success alone is insufficient.

Guardrail: unsupported candidates remain unknown. This GO does not authorize treating sparse-region actions as negatives, fitting a model, enabling assignment, modifying CFAR, mutating graphs, or running a full 199-sample model evaluation.
