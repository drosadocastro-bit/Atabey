# V24 Score-First Tracking Smoke Results

Status: **PASS; frozen 27-sample evaluation authorized**.

Kaggle version 4 completed the preregistered three-sample smoke on
`44b6_5f15d135`, `44b6_74d0c52e`, and `6bba_3c5691b6`. Versions 1-3 failed
before scoring because of notebook packaging or input-discovery defects and are
not experimental evidence.

## Contract Checks

- Source commit: `3ef5190ceaf6180096dc6893563944fc42cfd98b`.
- Checkpoint SHA-256: `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`.
- Public predictor SHA-256: `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`.
- All three frozen samples completed as full sequences.
- Repeated graph signatures were byte-identical for every arm.
- Official scoring and output serialization completed.
- Assignment, hybridization, training, threshold tuning, submission, and
  production mutation remained disabled.
- Total notebook-run time was 383.39 seconds.

## Smoke Metrics

These scores are execution diagnostics only. They do not select an arm or alter
the frozen 27-sample contract.

| arm | adjusted edge Jaccard | edge Jaccard | node recall | division Jaccard |
| --- | ---: | ---: | ---: | ---: |
| V19 frozen reference | 0.61836 | 0.62291 | 0.71183 | 0.00000 |
| E016 + Atabey relink | 0.67796 | 0.71225 | 0.96689 | 0.00000 |
| E016 native graph | 0.00000 | 0.00000 | unavailable | 0.00000 |

The native predictor emitted zero edges on all three samples despite producing
87,612 detections. The Atabey converter preserved that output. Inspection of the
pinned public predictor confirmed that the frozen native arm used its documented
defaults: softmax edge activation, threshold `0.5`, one parent per target, and up
to two children per source. This is retained as a frozen-arm observation rather
than repaired or tuned from smoke evidence.

## Authorization

The smoke passed its execution, provenance, coordinate-conversion,
determinism, official-metric, and serialization checks. The next authorized
action is the unchanged full-sequence evaluation on all 27 held-out samples.

Still unauthorized: full-199 execution, threshold tuning, retraining,
hybrid construction, submission, or production graph mutation.