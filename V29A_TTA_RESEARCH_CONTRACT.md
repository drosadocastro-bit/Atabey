# V29A: one four-view XY detector experiment

Status: **PROPOSED; implementation preparation authorized, exact execution freeze pending**.
Builder: Codex. Reviewer and execution authority: Danny. This contract authorizes
no competition submission. V28 submission 56631581 / public score 0.728 remains
frozen. The authenticated selected-submissions query on September 28 confirmed
V28 and V19 are already selected; no selection was changed.

## Question and intervention

Does the public predictor's existing four-view XY detection-logit average improve
the delivered V28 graphs sufficiently to justify reviewing one additional submission?
The only predictor configuration change is `det_tta: false -> true`: original,
X reflection, Y reflection and XY reflection, inverse-aligned and averaged in
logit space before the unchanged peak detector. No rotations or Z reflections
are introduced. This is four views, not the older V22 eight-view configuration.

Keep the E016 checkpoint, normalization, threshold 0.97, 5-micron pooling, window
size 2, downsampling, predictor code, physical coordinate conversion, motion_mutual
9-micron linker, source/candidate order, exact ties, operation order, reverse
mutuality, confidence computation, P2-then-P3 pruning and image-only routing fixed.
Different detections may change links, ties, pruning and recursive histories;
this is an upstream detection intervention with downstream effects, not a
ranking-only or history-fixed causal comparison. No threshold sweep, retraining,
ensemble of graphs, sample-ID selector, fallback or V27 promotion is permitted.

## Population and interpretation

The machine contract names all 199 previously opened samples, their metadata,
historical baseline graph signatures, GT tree hashes and subgroup memberships.
The 172 checkpoint-training and 27 checkpoint-held-out samples are both opened
development evidence. There is no unopened validation cohort and no claim of
independent generalization. The visible test samples only check output delivery.

The local baseline is reconstructed from newly generated no-TTA coordinates in
the same GPU experiment. All 199 baseline final-graph signatures must equal the
historical V24.3 references before paired official evaluation is valid. The
historical archive contains metrics and counts, not full-cohort coordinates;
therefore baseline inference is explicitly included in the budget.

## Phase A: timing, reproducibility, then full image inference

One offline T4 Kaggle research version, maximum **6 hours wall time**, including
setup. Enforce both outer job timeout and remaining-time child timeout. A T4
allocation may charge two devices: budget up to **12 GPU quota hours**. Use the
V28-tested software image, support pack version 10 and checkpoint version 1.

Before any inference, check exact package/support/weight identities, all 199
sample IDs and image metadata. Run control and TTA on the seven pre-existing V28
parity cases, which include the four catastrophic regressions. Controls must
match historical signatures. Repeat TTA on `44b6_5f15d135` and `6bba_2646afc7`;
both final-graph signatures must match exactly. Process all four fixed visible
samples and validate their CSV. This phase never reads GEFF labels or scores.

Apply the unchanged V28 conservative runtime formula to the seven TTA cases and
four visible cases: worst measured complete cost per voxel-frame, twice the
199-sample workload, scaled CSV validation, observed initialization and a
600-second reserve. **Projection must be at most 10 hours.** The hidden workload
assumption is unchanged and is not a guarantee. Averaging four views requires
four encoder calls; it does not imply a measured fourfold total runtime.

If timing fails, preserve `NO_GO_RUNTIME` and stop before the remaining cohort.
If it passes, generate the remaining control/TTA coordinates and final graph
signatures for all 199 samples. Persist each sample incrementally. Recompute the
same runtime formula including every measured TTA case; a failure blocks Phase B.
Control-inference and research-coordinate storage costs are research overhead,
not part of the proposed TTA-only submission workload.

## Phase B: fresh official paired scoring

Local CPU evaluation, maximum **3 hours**, with an outer process timeout as well
as per-sample budget checks. It starts only from the complete, hash-verified
Phase A output with passing timing and repeat gates. The same research receipt
binds both phases to one exact package. Do not regenerate missing outputs.

Reconstruct both final graphs from saved coordinates, verify signatures and
export structure, and evaluate each independently against the same frozen GEFF
graph with the existing official adapter. Pin tracking-cellmot commit
`075fc5f5a52d11077f9dc2b074644618f26939e2`, tracksdata commit
`39dccf3a243e44274759468cb31b2ad9e7fc1d09`, their installed source identities and
the existing 7-micron matching radius. Verify GT trees before scoring and around
each sample. No shared old correspondence or inferred metric shortcuts.

Every fresh baseline metric must reproduce its historical value: exact integer
and null fields, absolute float tolerance 1e-12, relative tolerance zero. Repeat
the TTA official evaluation on the first repeat sample with the same tolerance.
Use the official host's run-level aggregation, not a new mean or reweighting.
Preserve individual metrics and subgroup results, including undefined division
values; undefined primary score, adjusted edge or node-recall values invalidate
the decision. Record official FP separately from biological interpretation.

## Fixed quality gates, all required

Compare TTA to V28, never to the public 0.728 or to V19:

- Complete 199 paired samples with verified identities and valid graph exports.
- Official aggregate combined score improves by **at least 0.003**.
- Aggregate adjusted-edge Jaccard does not decrease.
- Aggregate score does not decrease in either family, the opened 27 held-out
  cases, the 172 training cases, or the 16 historical regression cases.
- More samples improve than regress, using 1e-12 only for the directional count.
- No individual combined-score loss exceeds **0.020**.
- No score loss on any of the four named catastrophic regression cases.
- Aggregate node recall falls by at most **0.002**.
- Summed official edge FP does not increase.

These are conservative operational choices fixed before any V29A outcome, not
confidence intervals or independently calibrated thresholds. A quality failure
is `NO_GO`, not permission to weaken a gate. Integrity, parity, dependency or
budget failure is `INVALID_EXECUTION`; preserve partial output and diagnose.

## Deadline and authority

Aim to finish research and review by September 28, 23:59 UTC. Do not start a new
submission run after the existing September 29, 05:59 UTC cutoff without explicit
rescheduling. Competition deadline remains September 29, 23:59 UTC. Protect time
for completed evaluation and final-selection verification; unused GPU quota is
not a reason to run another variant.

Passing all gates yields **GO_TO_HUMAN_SUBMISSION_REVIEW**, not automatic
submission authority. A separate exact submission package, visible validation
and Danny's approval would precede one additional competition submission.
Research approval does not change the selected V28/V19 entries, permit a retry,
publish code or authorize a parameter search. Any amended run receives a new
identified contract/package and preserves the first attempt.
