# V23 Pair-Field Ranker Implementation Smoke

Status: **implementation path validated; locked scientific fit not yet run**.

## Purpose

This smoke validates the executable form of the frozen V23 bounded pair-field preregistration. It does not estimate model quality and must not be used for a GO, HOLD, or NO-GO scientific decision.

The implementation consumes the immutable locked dataset containing 54 parent fields, 29 official-positive events, and 2,264 officially labeled candidate actions. Parent tensors and all three manifest hashes are verified before fitting.

## Implemented Path

- exact 20,145-parameter 3D CNN;
- on-demand five-channel action assembly from four-channel parent caches plus sparse daughter-pair masks;
- deterministic XY D4 augmentation only;
- sample -> event -> action weighted TP-versus-official-FP preferences;
- two inner-fold swaps and median-epoch outer refit;
- pessimistic full-action ranking;
- nearest-distance, fold-safe geometry, mask-only, shuffled-image, and static-image controls;
- seed/fold checkpoints and atomic score/fit shards;
- explicit `--resume` support with held-out index verification;
- no assignment, graph mutation, full-199 evaluation, or submission path.

## Local Smoke

The local CPU smoke used seed 314159, outer fold 1, and one epoch only. It exercised both inner swaps, both final CNN refits, all five controls, checkpoint publication, metrics, and report serialization.

The resulting scores are intentionally non-scientific. In particular, the one-epoch main ranker underperformed simple geometry and nearest-distance controls. This says only that the untrained execution path is not accidentally receiving labels or a shortcut feature.

## Resume Verification

The completed fold produced:

- `seed_314159_fold_1_scores.npz`;
- `seed_314159_fold_1_record.json`;
- main and mask-only checkpoints.

An immediate replay with `--resume`:

- skipped model fitting;
- completed in 3.55 seconds;
- reconstructed the result byte-identically;
- preserved summary SHA-256 `594E6F3889A4A9A3E3A34627A688D2021957473CD99DE6552D06BE5DB3040A25`.

## Next Authorized Run

The next experiment is the unchanged three-seed, three-outer-fold locked fit on a CUDA runtime. The default command retains the preregistered 60-epoch ceiling and early stopping. If interrupted, the identical command may be repeated with `--resume`; completed fold shards are reused and incomplete folds are recomputed.

The final result may authorize only a read-only local-assignment shadow preregistration. It cannot authorize graph mutation or a full-cohort rollout.
