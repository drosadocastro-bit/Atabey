# V29A results: local gain, frozen promotion criteria not met

**Decision: NO_GO.** The approved research execution completed and its evidence passed the final audit. TTA improves the aggregate development score, but fails two predeclared regression protections. Do not submit this variant under the V29A contract.

Builder and execution: Codex. Human approval for the frozen research package: Danny. Result verified September 28, 2026. No new competition submission, selection change, scientific retry, commit or push was performed.

## Paired official results

All 199 samples completed. These are local official metrics on previously opened development data, not Kaggle leaderboard scores.

| Metric | V28 control | Four-view XY TTA | Change |
|---|---:|---:|---:|
| Combined score | 0.721055749 | 0.735927590 | +0.014871840 |
| Adjusted-edge Jaccard | 0.721055749 | 0.735927590 | +0.014871840 |
| Edge Jaccard | 0.729042050 | 0.741253811 | +0.012211761 |
| Node recall | 0.961489704 | 0.960945668 | -0.000544036 |
| Summed official edge FP | 16,730 | 15,780 | -950 |

**134 samples improved, 65 regressed, none were unchanged.** 25 samples lost more than 0.020. The worst loss was -0.106430206 on `44b6_40c45f5a`. Both branches detected zero official true-positive divisions; this experiment did not recover division detection.

## Frozen gates

| Required gate | Observed | Verdict |
|---|---|---|
| Aggregate score gain >= 0.003 | +0.014871840 | PASS |
| Adjusted-edge Jaccard does not decrease | +0.014871840 | PASS |
| Score does not decrease in every specified subgroup | All five increased | PASS |
| More improved than regressed samples | 134 vs 65 | PASS |
| No individual loss beyond 0.020 | Worst -0.106430206; 25 breaches | **FAIL** |
| No loss in any of four catastrophic historical cases | One of four worsened | **FAIL** |
| Aggregate recall loss <= 0.002 | 0.000544036 loss | PASS |
| Summed official edge FP does not increase | 16,730 to 15,780 | PASS |

The two failed protections were specified before observing V29A outcomes. They remain binding despite the aggregate gain. No post-result threshold change, sample selector or fallback was introduced.

## Opened subgroup scores

| Group | n | V28 | TTA | Change |
|---|---:|---:|---:|---:|
| checkpoint_training_172 | 172 | 0.716372313 | 0.730655158 | +0.014282845 |
| family_44b6 | 71 | 0.719269731 | 0.724158440 | +0.004888709 |
| family_6bba | 128 | 0.721378768 | 0.738068361 | +0.016689593 |
| held_out_27 | 27 | 0.744350536 | 0.762206648 | +0.017856113 |
| historical_regressions_16 | 16 | 0.779314649 | 0.794498113 | +0.015183464 |

The 27 checkpoint-held-out cases were already opened before this experiment. Their gain is development evidence, not independent validation. These groups overlap and are not independent replications. Official FP counts are annotation-relative and do not establish biological false detections.

## Four protected cases

| Sample | V28 score | TTA score | Change |
|---|---:|---:|---:|
| 6bba_2646afc7 | 0.698109733 | 0.740841937 | +0.042732204 |
| 6bba_2540cd90 | 0.823370437 | 0.866724981 | +0.043354544 |
| 6bba_76db78c1 | 0.738047227 | 0.692509440 | -0.045537786 |
| 6bba_d5eae175 | 0.814450061 | 0.831228648 | +0.016778587 |

## Execution and verification

- Offline Kaggle version 1 completed both branches on 199 samples in 17350.064 seconds (4 h 49 min 10 s), below the 21,600-second cap.
- Initial and complete-cohort projections both independently reproduced 32507.235 seconds (9 h 01 min 47 s), below the 36,000-second gate. The worst measured normalized case was `6bba_05db0fb1`. This remains a workload extrapolation, not a verified hidden-test runtime.
- Seven historical timing controls and two exact TTA repeat signatures passed. All 199 newly inferred baseline graph signatures matched the historical references.
- All four visible samples passed CSV validation. The remote CSV has 300,812 rows; it is a preview, not a new competition submission.
- Retrieved 813 run/receipt files. Every manifest-listed output hash and receipt lineage was verified before evaluation.
- Local official paired scoring completed in 1003.818 seconds (16 min 44 s), below the 10,800-second cap. Its process exited successfully.
- Fresh baseline official metrics reproduced history for all 199 samples, using exact integer/null parity and the frozen absolute float tolerance of 1e-12. The official TTA repeat passed.
- The final audit rechecked the frozen artifact identities, both runtime projections, all 199 row records and GT trees, official aggregation, installed evaluator source/runtime and all eight gates. It did not rerun prediction or per-graph scoring.
- All 76 frozen V28 release artifacts and the pre-existing V25 notebook bytes remain unchanged. Authenticated final-selection verification still returned V28 56631581 (0.728) and V19 54622713 (0.515).

## Retained operational failures and pause

Danny intentionally paused local monitoring for travel while Kaggle continued. On return, output collection first hit HTTP 429 while enumerating auxiliary dependency files. A larger-page request was rejected with HTTP 400. Both failures were retained; supported 100-item pages at a three-second cadence and four concurrent file transfers recovered the output. No scientific run was retried. Local scoring began only after complete retrieval and integrity checks. The heartbeat remains paused.

## Evidence and identities

- Package manifest SHA-256: `7d93749e50dfe95fa1643dceb39e870f9111850ce994c14c30ca1496ddd4dc67`.
- Inference summary SHA-256: `ec669da0ca1ed4799e150281c75a66ca629176d9d8bd5e4f78f4c6291a58aa7d`.
- Official result SHA-256: `d0cad67e4f8f0ad4f9ecbd29784fced7fc31ae2c03652911c56da7723e879d22`.
- Research freeze: `v29a_research_freeze_approved_20260928.json`.
- Inference evidence: `outputs/v29a_execution_20260928/downloaded/v29a_run/summary.json`.
- Full official results and per-sample deltas: `outputs/v29a_execution_20260928/local_evaluation/result.json`.
- Final audit: `outputs/v29a_execution_20260928/final_evidence_verification.json`.
- Selection and V28 preservation check: `outputs/v29a_execution_20260928/closure_verification.json`.

## Recommendation

Keep the selected V28 0.728 entry and preserve V29A as a completed NO_GO research result. TTA showed an aggregate gain with concentrated regressions, which is a useful finding but does not satisfy the agreed promotion rule. Do not convert this opened-cohort result into a claim that a new leaderboard submission would improve. Any future experiment or changed decision rule needs its own explicit contract and authority; it cannot retroactively turn V29A into a passing run.
