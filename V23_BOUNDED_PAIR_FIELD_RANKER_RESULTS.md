# V23 Bounded Pair-Field Ranker Results

Decision: **`NO_GO_PAIR_FIELD_RANKER`**.

The preregistered development-only, sample-blocked fit completed all three folds for all three frozen seeds. No seed passed, every seed fell below the catastrophic Recall@10 floor, and the main image model was materially worse than the deterministic nearest-distance and fold-safe geometry-only controls.

| Seed | Recall@10 | MRR | Pairwise accuracy | Pass |
|---:|---:|---:|---:|---|
| 314159 | 0.206897 | 0.107656 | 0.420088 | No |
| 271828 | 0.344828 | 0.113220 | 0.452231 | No |
| 161803 | 0.241379 | 0.157510 | 0.518386 | No |

Median-seed control results:

| Source | Recall@10 | MRR | Pairwise accuracy |
|---|---:|---:|---:|
| Main image model | 0.241379 | 0.157510 | 0.518386 |
| Nearest distance | 0.862069 | 0.524786 | 0.866853 |
| Geometry only | 0.896552 | 0.598950 | 0.885955 |
| Mask only | 0.724138 | 0.298317 | 0.735623 |
| Image shuffled | 0.310345 | 0.126810 | 0.512436 |
| Static image | 0.241379 | 0.145022 | 0.482363 |

The experiment supplies no evidence that the tested local two-frame image field adds independent ranking signal. This is not a claim that microscopy images are intrinsically uninformative; it is a bounded rejection of this representation, model, objective, and development cohort.

Assignment remained disabled, no graph was mutated, the full 199-sample run was not authorized, and no submission path changed.

See [V23_SESSION_CLOSURE_2026-08-02.md](V23_SESSION_CLOSURE_2026-08-02.md) for the complete interpretation, surviving evidence, and next-version boundary.
