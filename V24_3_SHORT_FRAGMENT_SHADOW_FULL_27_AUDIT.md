# V24.3 Short-Fragment Shadow Full-27 Audit

Date: 2026-08-26

Decision: **GO_TO_FULL_199_SCORE_VALIDATION**.

This decision authorizes only frozen full-199 score validation of
`e016_atabey_relink_v24_3_short_fragment_shadow`. It does not authorize
threshold tuning, retraining, hybridization, production graph mutation, or
submission generation.

## Provenance

- Artifact: `v24_score_first_tracking_outputs (7).zip`
- Artifact SHA-256: `b180f98c6d80e714440e0dab3d5594abe2dd97fe4698abb1977bf4b883b727e9`
- Atabey commit: `905671f0ad1b7e2ab868e5a84a322c565d52f273`
- Checkpoint SHA-256: `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`
- Support pack: `pilkwang/biohub-tracking-support-pack-50ep-v1`
- Complete cohort: 27 of 27 expected samples, with no missing or extra IDs
- Deterministic replay: verified
- Training during evaluation: none
- Runner and V24.2/V24.3/telemetry source hashes: verified against the frozen contract

## Frozen Gate Result

| Gate | V24.3 result | Pass |
|---|---:|:---:|
| Pooled adjusted-edge delta | +0.226518 | Yes |
| Pooled total-score delta | +0.226518 | Yes |
| 44b6 adjusted-edge delta | +0.340127 | Yes |
| 6bba adjusted-edge delta | +0.219686 | Yes |
| Fold 1 adjusted-edge delta | +0.243587 | Yes |
| Fold 2 adjusted-edge delta | +0.235913 | Yes |
| Fold 3 adjusted-edge delta | +0.196405 | Yes |
| Improved / regressed samples | 26 / 1 | Yes |
| Catastrophic regressions | 0 | Yes |
| Median predicted-node ratio | 1.221235 | Yes |
| P90 predicted-node ratio | 1.420642 | Yes |
| Complete samples | 27 / 27 | Yes |
| Determinism | Verified | Yes |

V24.3 removed 9,212 additional detections relative to V24.2 across the cohort,
with a median of 344 per sample. Relative to V24.2, 18 samples improved, 8 were
unchanged, and 1 decreased by 0.000447 adjusted-edge Jaccard.

The sole V24.3 regression relative to V19 was `6bba_3c5691b6` at -0.027854.
It remained above the preregistered catastrophic threshold and improved by
+0.021540 relative to V24.2 on that sample.

## Adjudication

Every preregistered full-27 gate passed for V24.3. V24.2 remained blocked by
its median node-ratio gate, and the native graph arm failed multiple score and
regression gates. Therefore V24.3 alone advances to frozen full-199 score
validation. The V24.3 rule and evaluation settings remain frozen for that run.
