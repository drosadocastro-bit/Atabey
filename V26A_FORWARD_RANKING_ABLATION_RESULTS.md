# V26A Forward Motion-Prediction Ranking Ablation Results

Date: 2026-09-03

Status: **COMPLETE; NO-GO**.

V26A replaced only the forward candidate ordering: feasible targets were ranked
by physical step distance instead of motion-prediction error. E016 detections,
both 9 micron gates, reverse mutuality, greedy uniqueness, edge-confidence
inputs, V24.2/V24.3 pruning, routing, and official metric logic remained frozen.

The run used all 16 opened V24.3 regressions and completed deterministic double
replay. This is retrospective intervention-sensitivity evidence, not independent
generalization evidence.

## Result

The ablation recovered 148 V19-credited losses. Of these, 108 came from the 436
forward-ranking bucket, 18 from reverse-mutuality conflicts, 4 from candidate
generation, 8 from post-link pruning, and 10 from adjustment-only effects. The
out-of-bucket recoveries are expected evidence of recursive motion-history and
topology propagation; they are not clean direct effects.

| Transition | Count |
| --- | ---: |
| Recovered V19-credited edges | 148 |
| Newly credited edges | 179 |
| Displaced V24.3-credited edges | 107 |
| Net credited-association delta | +72 |
| Newly incorrect prediction edges | 1,658 |
| Removed incorrect prediction edges | 867 |
| Net incorrect-edge delta | **+791** |
| New incorrect edges per forward recovery | **15.35** |

Here, "incorrect" is the preregistered operational label for a prediction edge
that is unmatched by the pinned official evaluator under sparse ground truth. It
is not proof that the association is biologically false.

The official adjusted edge Jaccard increased from `0.77931465` to `0.78258659`
(`+0.00327194`). Pooled official edge counts changed by TP `+72`, FP `+30`, and
FN `-72`. Nine samples improved and seven regressed. The worst sample was the
catastrophic case `6bba_2646afc7` at `-0.01070395` adjusted edge Jaccard.

The transition ledger and official FP delta measure different surfaces. The
ledger counts newly added versus removed unmatched prediction-edge identities;
the official evaluator rematches nodes and edges globally. Both are retained,
and the preregistered ledger collateral bound remains binding.

## Pruning Interaction

Pruning code was unchanged, but changed linking topology altered its input:

| Stage | Baseline removed | Ablation removed | Delta |
| --- | ---: | ---: | ---: |
| V24.2 nodes | 3,726 | 3,534 | -192 |
| V24.2 edges | 0 | 0 | 0 |
| V24.3 nodes | 3,344 | 2,952 | -392 |
| V24.3 edges | 1,672 | 1,476 | -196 |

This confirms that a ranking intervention propagates through track history and
pruning eligibility even when pruning logic itself is frozen.

## Binding Gate

Passed:

- 108 forward-ranking recoveries exceeds the fixed minimum of 44;
- net credited-association delta is positive;
- worst per-sample adjusted-edge regression remains above the `-0.10` bound;
- deterministic replay passed.

Failed:

- net incorrect-edge delta must be nonpositive; observed `+791`;
- new incorrect edges per forward recovery must be at most `0.25`; observed
  `15.3519`.

The slight official-metric gain cannot override these failures. V26A is a
**NO-GO**. Do not tune a blend, threshold, fallback, or sample selector on this
opened cohort. V26B and V26C remain separate future questions; pruning remains
untouched.

## Provenance

- V26A source commit: `dd2598dc3f5fb1dc7352f844749b307195b13c12`
- V25 kernel-native archive SHA-256:
  `0984e11446817f83b678612c5f79a4ed9c9a7fb94aa150f250e28149e9199d21`
- V26A result archive SHA-256:
  `36f0559d09f213e675a83df285a8b8f5d53cd0957b67b27053b39d0acb919b39`
- Archive: 45,397 bytes, 19 entries, 16 sample artifacts
- Relinking runtime: 27.34 seconds total, 1.71 seconds mean
- Peak Python-traced memory: 1,431,248 bytes

The raw result ZIP remains local evidence and is not required in Git history.