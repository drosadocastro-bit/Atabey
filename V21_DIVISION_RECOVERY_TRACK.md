# V21 Division Recovery Track

Date: 2026-07-19
Branch: `mitosis_hough_audit`

## Objective

V20 Track A remains frozen: gated bipartite linking plus the strict division firewall is kept as the topology-cleanup path. V21 adds a separate Track B shadow path for true-division recovery measurement. Track B logs candidate annotations only; it does not add, remove, or relabel lineage graph edges.

## Root Cause: V19's 3 True Positives Lost By V20

The reconstructed 168-sample V20 cohort analysis showed V19 had 3 sparse-label division TPs and V20 had 0. The traced V19 TP samples are:

| Sample | GT parent | V19 pred parent | Firewall scoring on V19 branch | Finding |
| --- | ---: | --- | --- | --- |
| `6bba_05db0fb1` | `25000381` | `6bba_05db0fb1:t24:cf76` | accept, fallback angle `135.896`, ratio `1.109` | Not killed by firewall when evaluated on the V19 branch. A bounded V20 rebuild through frame 32 showed the V19 parent and both child node IDs were absent in V20, so this TP was lost upstream before the firewall could preserve it. |
| `6bba_b329af44` | `83001755` | `6bba_b329af44:t82:cf38` | accept, multi-frame drift `11.213`, first separation growth `1.495` | Not killed by the firewall predicate on the V19 branch. Most likely an upstream graph/detection-path loss like the first sample; this still needs an actual bounded V20 rebuild around frame 90 to confirm node presence. |
| `6bba_ebdf3b34` | `85001151` | `6bba_ebdf3b34:t84:cf39` | reject, fallback angle `154.597`, ratio `2.015` | Killed by the strict fallback distance-ratio guard. This is the only one of the three where the frozen firewall rule itself is directly implicated by current evidence. |

Evidence files:

- `v21_lost_tp_trace.csv`: pure V19-branch firewall scoring for the three V19 TPs.
- `v21_lost_tp_trace_6bba_05db0fb1_check_v20_t32.csv`: bounded V20 rebuild confirming the first V19 TP branch's node IDs were absent in V20.

Important interpretation: the loss of V19's 3 TPs is not explained by a single firewall threshold. At least one TP is upstream-detection/graph divergence, one is directly firewall fallback-ratio rejection, and one still needs bounded V20 node-presence confirmation.

## Track A: Frozen Production Topology Path

Track A is unchanged. No V20 firewall thresholds were modified. The firewall remains responsible for the broad V20 cleanup win measured in the reconstructed cohort:

- CFAR-active V19 to V20 division FP reduction: about `91%` total reduction.
- CFAR-active EdgeRecall side effect: V20 mean delta about `+0.13` vs V13 and `+0.09` vs V19 in the 168-sample reconstruction.
- Division detection caveat: V20 Track A remains too conservative as a committed-division detector, with `0` sparse-label division TPs in the reconstructed cohort.

## Track B: Shadow-Only Candidate Recovery

Implemented module: `src/atabey/tracking/division_recovery_shadow.py`

Track B consumes a candidate graph, currently intended to be the V19-style pre-firewall bipartite graph, and returns `DivisionRecoveryCandidate` annotations. It never mutates the graph. This follows the repo's existing shadow pattern: measure possible signals independently before considering any active integration.

Current guardrails are intentionally shaped differently from Track A:

- Multi-frame candidate: accept when branch axis drift is below `30 deg` and first separation growth is positive.
- Fallback candidate: accept when the immediate split is broad-angle and not extremely imbalanced: angle at least `120 deg`, distance ratio at most `2.5`.
- No candidate is committed as an edge; accepted means only `track_b_candidate=True` for measurement.

Why this shape:

- It recovers the directly firewall-killed V19 TP signature in `6bba_ebdf3b34` without changing Track A's strict ratio cutoff.
- It preserves the two V19 TP signatures that already satisfy stable/broad split behavior.
- It gives us a separate precision/recall accounting path instead of reopening V19's FP explosion in the production graph.

## Validation Tooling

Implemented runner: `scripts/run_v21_division_recovery_shadow.py`

The runner reports, per sample:

- Track A detector/link strategy, EdgeRecall, division TP/FP/FN from frozen V20.
- Track B candidate count, accepted count, TP/FP/FN/Jaccard measured against sparse GT using the same reachability discipline.
- `track_a_zero_perturbation`, verifying Track B measurement did not alter Track A edges.

Smoke command run locally:

```powershell
python scripts\run_v21_division_recovery_shadow.py --sample-ids 6bba_05db0fb1 --max-timepoints 2 --output v21_division_recovery_shadow_smoke.csv
```

Smoke result:

- Track A: `v20_firewall/bipartite`, `track_a_zero_perturbation=True`
- Track B: accepted `13`, TP `0`, FP `13`, FN `3` on the tiny two-frame slice. This was only a wiring check, not biological validation.

Focused tests:

```powershell
python -m pytest tests\test_division_recovery_shadow.py tests\test_division_firewall.py -q
```

Result: `5 passed`.

## Full-Cohort Validation Command

For Colab or another long-running host:

```bash
python -u scripts/run_v21_division_recovery_shadow.py \
  --sample-ids all \
  --max-timepoints 100 \
  --output v21_division_recovery_shadow_199.csv | tee v21_division_recovery_shadow_199.log
```

Recommended first bounded run:

```bash
python -u scripts/run_v21_division_recovery_shadow.py \
  --sample-ids 6bba_05db0fb1 6bba_b329af44 6bba_ebdf3b34 \
  --max-timepoints 100 \
  --output v21_division_recovery_shadow_3tp.csv | tee v21_division_recovery_shadow_3tp.log
```


## Bounded Three-TP Validation

Completed on the three reconstructed V19 true-positive samples at `max_timepoints=100`.

| Sample | Track A EdgeRecall | Track A Div TP/FP/FN | Track B accepted | Track B TP/FP/FN | Zero perturbation |
| --- | ---: | --- | ---: | --- | --- |
| `6bba_05db0fb1` | `0.775330396475771` | `0/821/3` | `2592` | `1/2591/2` | `True` |
| `6bba_b329af44` | `0.7890410958904109` | `0/968/1` | `3006` | `1/3005/0` | `True` |
| `6bba_ebdf3b34` | `0.7921686746987951` | `0/950/2` | `2137` | `1/2136/1` | `True` |

Aggregate bounded result:

- Track B recovered all `3/3` known V19 sparse-label true-positive divisions.
- Track B accepted `7,735` candidates, with `3` TP and `7,732` FP.
- Track B precision on this calibration subset is about `0.039%`.
- Track A zero-perturbation held for all three samples.

Interpretation: Track B proves the true signal is still recoverable in a side channel, including the `6bba_ebdf3b34` candidate rejected by Track A's strict fallback ratio. It is not yet a deployable policy: the current broad shadow rule reopens thousands of candidate false positives. The next V21 step should be ranking or feature analysis of Track B candidates, not injecting them into the production graph.

## GO / NO-GO Criteria

V21 GO only if the full-cohort validation shows all of the following:

- `track_a_zero_perturbation=True` for every sample.
- Track A EdgeRecall/FP metrics remain identical to V20.
- Track B recovers more sparse-label TP signal than V19's original `3` TPs, or recovers those TPs with materially lower candidate FP burden than committed V19 bipartite.
- Track B's FP distribution is bounded enough to justify future integration as a submission-side annotation or candidate export.

V21 NO-GO if Track B cannot improve on V19's tiny TP count without producing V19-like FP scale. That would be useful negative evidence: clean topology and true-division recovery may need separate model evidence, not more geometric threshold work.

## Current Status

Implemented and locally smoke-tested:

- `src/atabey/tracking/division_recovery_shadow.py`
- `tests/test_division_recovery_shadow.py`
- `scripts/run_v21_division_recovery_shadow.py`
- `scripts/trace_v21_lost_division_tps.py`

Still open:

- Run bounded V20 node-presence checks for `6bba_b329af44` and possibly `6bba_ebdf3b34` if runtime allows.
- Three-TP Track B validation completed: recovered `3/3` known V19 TPs but with `7,732` FP.
- Run full 199-sample Track B validation and aggregate candidate precision/recall.
- Do not tune Track A. Do not inject Track B candidates into submission output until the shadow validation has a clear GO.

## NIC-Inspired Confidence Gate and Extractive Fallback

NIC's implementation was inspected directly at commit `14649f157554d119106b1c60d8c42bf17893a532` before designing the Atabey analog. The source has two separate controls, not one generic 60% rule:

- a pre-generation retrieval-confidence gate in `core/handlers/query_handler.py`, defaulting to 0.75, which averages retrieved-document confidence and skips LLM generation when evidence is weak;
- a post-generation grounding gate, defaulting to 0.60, which measures statement-to-source token overlap and replaces weak synthesis with source snippets; confidence below 0.35 plus weak grounding causes abstention;
- the extractive response contains bounded text from retrieved chunks plus source, page, and document identifiers. It is evidence exposure, not lower-confidence generation.

Atabey adopts the routing shape, not NIC's text-specific confidence calculation.

### Track B Routing

Implemented in `src/atabey/tracking/division_recovery_shadow.py`:

- `division_proposal`: geometrically accepted and supplied with an independently calibrated confidence at or above 0.60;
- `extractive_flagged`: geometrically accepted but below threshold or missing a calibrated confidence;
- `rejected`: fails Track B's geometric candidate guardrails, even if a high confidence is supplied.

The extractive equivalent is the unchanged candidate evidence record: parent and child IDs, mechanism, angle or drift, separation growth, distances, density, volume, intensity, and diagnostic ranking score. Flagged candidates are logged but do not become division decisions or graph edges.

The old `ranking_score` is deliberately not reused as confidence. It was designed for ordering, is not probabilistically calibrated, and failed the three-sample ranking test.

### Threshold Calibration Result

The saved three-sample CSV contains 7,735 accepted candidates: 3 TP and 7,732 FP.

Applying the 0.60 hypothesis directly to the old ranking score would retain:

- 1 of 3 known TPs;
- 1,444 FPs;
- no usable precision region.

The mechanisms also overlap heavily with their FP populations:

- fallback: 2 TP among 5,835 candidates;
- multi-frame: 1 TP among 1,900 candidates;
- fallback TP scores were 0.7545 and 0.5232 while the FP median was 0.5231;
- the multi-frame TP score was 0.4800 while the FP median was 0.4551.

Conclusion: 0.60 remains the explicit routing threshold, but no current feature score qualifies as calibrated confidence. The production default supplies no calibrated confidence, so accepted candidates route to `extractive_flagged`. This is intentional abstention from overclaiming, not a hidden threshold failure. A future calibrator must be trained and evaluated on more positive divisions before it may populate `calibrated_confidence_by_parent_id`.

The V21 runner now reports broad geometric accepted counts separately from proposal and flagged counts, and computes proposal-only TP/FP/FN without changing the prior diagnostic accounting.

## Fixed Adversarial Battery

Added:

- `ATABEY_ADVERSARIAL_BATTERY.md`
- `tests/fixtures/atabey_adversarial_battery.json`
- `tests/test_atabey_adversarial_battery.py`

The battery is append-only and starts with the 90-110 degree collision band, the three known V19/V21 TPs, the newer `6bba_ebdf3b34` upstream pairing FN, and the 9-to-14 um formation-gate regression. The test contains a required baseline ID set, so future cases may be added while removal of an original case fails.

This mirrors the useful part of NIC's checked-in 90-case full-suite runner and report. The inspected NIC source confirms a fixed, version-controlled full-suite rerun with regression accounting; it does not visibly enforce an append-only invariant. Atabey adds that rule explicitly.

Battery command:

```powershell
python -m pytest tests/test_atabey_adversarial_battery.py tests/test_division_recovery_shadow.py tests/test_division_firewall.py -q
```

This battery must pass before bounded real-data validation and before any 199-sample Colab run.
