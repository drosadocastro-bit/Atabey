# V23 Parallel CFAR vs Encoder-Decoder Detector Shadow

## Objective

Compare the quarantined CFAR route with the frozen encoder-decoder detector
under identical inputs and evaluation rules. The experiment is intended to
decide whether CFAR should remain, be replaced, or become a fallback. It does
not authorize production routing changes.

## Arms

### Arm A: CFAR quarantined control

Run the current `cfar_sidelobe/bipartite` path unchanged. Its metrics are
reported separately and it cannot be used to claim pooled semantic
generalization. The output is shadow-only and does not mutate a graph.

### Arm B: encoder-decoder detector

Use the frozen E016 U-Net encoder-decoder as a detector-native shadow. Export
decoder heatmaps/logits, local confidence, uncertainty/margin, and peaks at a
fixed operating point. Do not retrain or tune against the evaluation cases in
this comparison. Preserve the physical voxel scale and 14 um action contract.

### Arm C: availability-gated fallback

Use Arm B first. If it fails a preregistered detector-availability check, retain
the CFAR output for that case. This arm is diagnostic only: it must report how
often fallback was used and must not hide Arm B failures inside an aggregate.

## Matched protocol

All three arms receive the same raw volumes, event frames, sample-blocked
development split, and patched official metric. Candidate actions are built
from each arm independently, with no cross-arm candidate union in the primary
comparison. Unknown and unsupported actions remain unknown, never negatives.

The initial run is the complete bounded E016 development population: 27
samples and 46 registered events. It includes 7 CFAR-routed events, both
families, and the positive controls. The full 199-sample cohort remains locked
until the bounded gates pass.

## Required reporting

Report each arm separately by fold, family, route, sample, and event:

- detector peak count and candidate density;
- parent/daughter/complete-triplet availability;
- official-positive availability;
- official TP and FP action counts under the patched scorer;
- event and action retrieval at fixed budgets;
- edge-recall/continuation perturbation;
- fallback frequency for Arm C;
- graph mutation and zero-perturbation status.

The central comparison is not a single score. It is the trade-off between
official-positive availability, unsupported candidate volume, false positives,
and normal tracking preservation.

## Preregistered bounded gates

Arm B can advance to an independent CFAR-heavy shadow only if:

- official-positive availability is at least 95% of Arm A;
- CFAR-route event recall@50 is at least 0.70, or the arm shows a documented
  availability gain that makes ranking the next bottleneck;
- candidate density is no more than 10% above Arm A at matched availability;
- no family has event recall@50 below 0.50;
- no measurable degradation appears in normal edge-recall shadow;
- graph mutation is false for every arm.

Arm C is useful only if it improves Arm B without simply reproducing Arm A on
most cases. Its fallback rate must therefore be reported explicitly; a high
fallback rate is a HOLD, not a hidden success.

## Decision states

- **GO replacement shadow:** Arm B passes the bounded gates and proceeds to
  independent CFAR-heavy samples.
- **GO fallback shadow:** Arm B is incomplete, but Arm C improves availability
  without masking a substantial failure population.
- **HOLD:** evidence is promising but route/family stability is insufficient.
- **NO-GO:** neither Arm B nor Arm C improves the quarantined CFAR control
  safely; CFAR remains unchanged.

No threshold tuning, Hungarian assignment, production routing change, or full
199-sample run is authorized by this preregistration.
