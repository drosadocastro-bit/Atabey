# V24 Score-First Tracking Results

Status: **HOLD; score gain observed, but full-199 validation is not authorized**.

Kaggle version 5 completed the preregistered full-sequence evaluation on all 27
checkpoint-held-out samples. The E016 detections with frozen Atabey relinking
improved official adjusted edge Jaccard substantially, but failed the hard
median node-inflation gate. Under the frozen decision contract, the result is
`HOLD_SCORE_GAIN_WITH_STRATUM_OR_INFLATION_CONCERN`.

## Integrity Checks

- Exact frozen cohort: 27 unique samples (`44b6`: 5; `6bba`: 22).
- Deterministic folds: 10, 9, and 8 samples.
- All samples ran as complete sequences; no timepoint cap was applied.
- Repeated graph signatures were byte-identical for all three arms on
  `44b6_5f15d135`.
- Source commit: `3ef5190ceaf6180096dc6893563944fc42cfd98b`.
- Checkpoint SHA-256: `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`.
- Public predictor SHA-256: `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`.
- Assignment, hybridization, training, and production graph mutation remained
  disabled.
- The raw run and bundled copies of the summary, per-sample table, provenance,
  and determinism record were byte-identical.
- Total notebook-run time was 2,856.12 seconds.

## Official Results

| Arm | Adjusted edge Jaccard | Delta vs V19 | Edge Jaccard | Node recall |
| --- | ---: | ---: | ---: | ---: |
| V19 frozen reference | 0.51783 | - | 0.51317 | 0.72906 |
| E016 + Atabey relink | 0.69914 | +0.18131 | 0.71138 | 0.97273 |
| E016 native graph | 0.00000 | -0.51783 | 0.00000 | unavailable |

The relink arm improved 24 samples and regressed 3. Its adjusted-edge deltas
were positive in both families (`44b6`: +0.34013; `6bba`: +0.17204) and all
three folds (+0.20646, +0.18362, and +0.14733). The regressed samples were:

| Sample | Adjusted-edge delta |
| --- | ---: |
| `6bba_3c5691b6` | -0.11430 |
| `6bba_2819ca14` | -0.04782 |
| `6bba_6321a359` | -0.01212 |

The native graph emitted zero edges for every sample and therefore failed the
score, family, fold, direction, catastrophic-regression, and median-inflation
gates. This remains the frozen predictor behavior; V24 does not tune or repair
it after observing the result.

## Gate Adjudication

The relink arm passed every frozen gate except median predicted-node inflation:

| Gate | Observed | Limit | Result |
| --- | ---: | ---: | --- |
| Pooled adjusted-edge delta | +0.18131 | at least +0.02000 | Pass |
| Family deltas | +0.34013 / +0.17204 | at least -0.01000 | Pass |
| Fold deltas | +0.20646 / +0.18362 / +0.14733 | at least -0.02000 | Pass |
| Improved vs regressed | 24 / 3 | improved > regressed | Pass |
| Regressions below -0.10 | 1 | at most 2 | Pass |
| Median node ratio vs V19 | 1.35105 | at most 1.25000 | **Fail** |
| P90 node ratio vs V19 | 1.57898 | at most 1.75000 | Pass |

The gain is broad enough to justify further diagnosis, but the failed hard gate
prevents promotion. The result does not authorize full-199 execution,
threshold tuning, hybrid construction, retraining, submission, or production
mutation. Any continuation must be preregistered as a new bounded experiment;
the V24 outcome cannot be used to retrofit this frozen arm.

Compact machine-readable evidence is preserved in
`v24_score_first_tracking_27_evidence.json`.