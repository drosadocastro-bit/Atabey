# V22 Continuation Feature Table Results

Decision: **GO TO OUT-OF-FOLD CONTINUATION HEAD**

This build converts the validated weak V19 continuation population into a
fold-safe feature table. It does not fit a model, score a candidate, run
assignment, use ground truth, or mutate a graph.

## Population

| Population | Count |
|---|---:|
| Development samples | 27 |
| Weak reference groups | 182,996 |
| Weak reference rows | 182,996 |
| Unknown alternative rows | 1,024,536 |
| Total candidate rows | 1,207,532 |
| Compressed shard size | 124.1 MiB |

All preregistered population totals matched exactly.

## Fold Breakdown

| Fold | Candidate rows | Raw share |
|---:|---:|---:|
| 1 | 285,960 | 23.7% |
| 2 | 595,263 | 49.3% |
| 3 | 326,309 | 27.0% |

Fold 2 contains almost half of the raw rows. Sample blocking remains necessary
but is not sufficient; raw row weighting is prohibited.

## Family Breakdown

| Family | Candidate rows | Raw share |
|---|---:|---:|
| `44b6` | 612,949 | 50.8% |
| `6bba` | 594,583 | 49.2% |

The row totals are balanced by family, but they arise from only five `44b6`
samples and twenty-two `6bba` samples. Family is therefore a reporting stratum,
not a weighting or confidence shortcut.

## Route Breakdown

| Route | Candidate rows | Raw share | Interpretation |
|---|---:|---:|---|
| `cfar_sidelobe/bipartite` | 736,500 | 61.0% | Supported across all folds |
| `components/greedy` | 303,520 | 25.1% | Supported across all folds |
| `local_maxima/motion_mutual` | 167,512 | 13.9% | **Unproven generalization** |

All local-maxima rows come from `44b6_5f15d135` in fold 3. Folds 1 and 2
provide no held-out local-maxima observation, and the fold-3 held-out result
will be zero-shot because that route is absent from training. Local-maxima
metrics must remain separate from every pooled result.

## Concentration And Weighting

Raw rows are heavily concentrated:

- largest sample: `44b6_706092f0`, 262,250 rows (**21.7%**);
- top three samples: **47.6%** of all rows;
- effective sample size under raw row weighting: **9.14 of 27**.

The hierarchical sample -> parent frame -> reference -> candidate weight sums
to 1 for every sample. The largest numerical deviation was
`1.34e-13`, well inside the frozen `1e-9` tolerance. Future training must use
these weights and then weight samples equally inside each training fold.

## Feature Integrity

The table contains only the frozen route-neutral geometry and ownership
features. Detector confidence, route, family, intensity, appearance, and volume
are not model features.

Missingness is explicit:

- step-distance ratio missing for 70,237 rows (5.8%) due zero
  anchor-to-parent displacement;
- turning angle missing for 80,098 rows (6.6%) due a zero motion vector.

Every feature marked available was finite. No favorable zero was substituted
for a missing value.

## Parity And Epistemic Checks

- Source reference IDs reproduced exactly.
- Source reference metric maximum delta: **0.0**.
- Recomputed reference-feature maximum delta: **1.78e-15**.
- Candidate IDs: **1,207,532 unique / 1,207,532 rows**.
- Duplicate candidate IDs: **0**.
- Rows marked as ground truth: **0**.
- Alternatives marked as negatives: **0**.
- Semantic scores present: **0**.
- Assignment selections: **0**.
- Graph mutations: **0**.
- Source graph perturbations: **0**.

All preregistered gates passed.

## Decision

The table is a **GO** for the first sample-blocked, out-of-fold continuation-head
experiment. This authorizes model fitting only under a separate frozen training
contract using:

1. the existing three sample-blocked folds;
2. the hierarchical equal-sample weights;
3. weak pairwise preference rather than biological labels;
4. explicit missing-feature masks;
5. fold, family, and route reporting from the start;
6. separate local-maxima results labeled **unproven generalization**;
7. no assignment or graph mutation.

The full 199-sample scope remains closed.
