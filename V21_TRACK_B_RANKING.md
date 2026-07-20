# V21 Track B Ranking

Date: 2026-07-19
Branch: `mitosis_hough_audit`

## Objective

Track B recovered sparse true-division signal, but the initial broad candidate channel is too noisy for direct use. This ranking layer is Track B-only: it changes candidate ordering and diagnostic exports, not Track A, not V20 firewall thresholds, and not the committed lineage graph.

## Implemented Ranking Features

`src/atabey/tracking/division_recovery_shadow.py` now records these per candidate:

- directional geometry: fallback split angle and distance ratio, or multi-frame drift and first separation growth;
- child distances and child-child separation;
- local density at `t+1` within `10 um` of the parent;
- parent/component volume vs daughter volume sum, when component volumes are available;
- parent intensity vs daughter intensity sum, when intensity fields are available;
- `ranking_score`, a diagnostic ordering score.

The current ranking score is deliberately not a pass/fail gate. It emphasizes daughter separation, balanced child distances, geometry consistency, and lower local density. Volume and intensity are kept as weak diagnostic terms because the first bounded result suggests they are not strong separators in this candidate population.

## Analysis Tooling

New script:

```bash
python -u scripts/analyze_v21_track_b_ranking.py \
  --sample-ids 6bba_05db0fb1 6bba_b329af44 6bba_ebdf3b34 \
  --max-timepoints 100 \
  --candidate-output v21_track_b_ranked_candidates_3tp.csv \
  --missed-output v21_track_b_missed_gt_divisions_3tp.csv \
  --feature-output v21_track_b_feature_summary_3tp.csv \
  --report-output V21_TRACK_B_RANKING.md | tee v21_track_b_ranking_3tp.log
```

The script exports:

- ranked accepted Track B candidates with TP/FP labels;
- TP rank positions per sample;
- TP vs sampled-FP vs all-FP feature summaries;
- missed GT division diagnostics, including whether GT nodes failed sparse matching or whether a candidate existed but was rejected.

## Bounded First-Sample Result

Local bounded run:

```bash
python scripts/analyze_v21_track_b_ranking.py \
  --sample-ids 6bba_05db0fb1 \
  --max-timepoints 32 \
  --candidate-output v21_track_b_ranked_candidates_6bba_05db0fb1_t32.csv \
  --missed-output v21_track_b_missed_gt_divisions_6bba_05db0fb1_t32.csv \
  --feature-output v21_track_b_feature_summary_6bba_05db0fb1_t32.csv \
  --report-output V21_TRACK_B_RANKING_6bba_05db0fb1_t32.md
```

Result:

| Sample | GT parent | Candidate parent | Rank | Accepted candidates | Reason |
| --- | ---: | --- | ---: | ---: | --- |
| `6bba_05db0fb1` | `25000381` | `6bba_05db0fb1:t24:cf76` | `10` | `1040` | `fallback_broad_angle_balanced_split` |

Feature contrast from this bounded run:

| Feature | TP | FP median |
| --- | ---: | ---: |
| ranking score | `0.754457` | `0.501078` |
| geometry score | `0.723697` | `0.565158` |
| child separation | `12.643561 um` | `7.729550 um` |
| local density | `3` | `5` |
| volume conservation error | `1.000000` | `1.000000` |
| intensity conservation error | `1.570535` | `0.954710` |

Interpretation: separation, balance, and density are promising ranking signals on this bounded case. Volume is non-separating here, and intensity conservation is not helpful for this TP. The rank improvement is real but not yet generalized.


## Three-Sample Ranking Result

Completed on the three reconstructed V19 true-positive samples at `max_timepoints=100`.

| Sample | GT parent | Candidate parent | Rank | Accepted candidates | Ranking score | Reason |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `6bba_05db0fb1` | `25000381` | `6bba_05db0fb1:t24:cf76` | `24` | `2592` | `0.754457` | `fallback_broad_angle_balanced_split` |
| `6bba_b329af44` | `83001755` | `6bba_b329af44:t82:cf38` | `1805` | `3006` | `0.479983` | `multi_frame_positive_divergence` |
| `6bba_ebdf3b34` | `85001151` | `6bba_ebdf3b34:t84:cf39` | `1018` | `2137` | `0.523229` | `fallback_broad_angle_balanced_split` |

Top-N capture:

- Top 10: `0/3`
- Top 20: `0/3`
- Top 50: `1/3`
- Top 100: `1/3`
- Top 500: `1/3`
- Top 1000: `1/3`
- Top 2000: `3/3`

Feature summary across all accepted candidates:

| Feature | TP median | FP-all median |
| --- | ---: | ---: |
| ranking score | `0.523229` | `0.503439` |
| geometry score | `0.568874` | `0.586919` |
| child separation | `9.029673 um` | `7.420417 um` |
| local density | `5` | `5` |
| distance ratio | `1.562232` | `1.609108` |
| max drift | `11.212534 deg` | `12.773973 deg` |
| first separation growth | `1.494934 um/frame` | `1.252070 um/frame` |
| volume conservation error | `1.000000` | `1.000000` |
| intensity conservation error | `0.623928` | `0.949146` |

Interpretation: the ranking does not generalize from the first bounded case. It keeps `6bba_05db0fb1` reasonably reviewable at rank `24`, but the other two known TPs are still buried at ranks `1805` and `1018`. The feature distributions are heavily overlapped: geometry is not better for TPs than FPs in aggregate, local density has the same median, and volume remains non-separating. Child separation and intensity error show mild aggregate separation, but not enough for useful top-N capture.

This is a Track B ranking NO-GO in its current form for human review. It remains useful as diagnostic evidence: true divisions can be recovered in the side channel, but simple geometric/density/mass ranking is insufficient to surface them reliably.

## Missed GT Diagnostic

For the bounded `6bba_05db0fb1` window, the two missed GT divisions had no matched sparse GT parent or daughter predictions, so Track B could not recover them as ranking failures. They are upstream detection/matching misses in this bounded context.

The three-sample missed-output CSV is now available. It reports three missed GT divisions:

| Sample | GT parent | Matched prediction nodes | Reachable Track B candidates | Diagnosis |
| --- | ---: | --- | ---: | --- |
| `6bba_05db0fb1` | `53001011` | parent=False, child1=False, child2=True | `0` | `sparse_gt_node_unmatched_to_prediction` |
| `6bba_05db0fb1` | `63001217` | parent=False, child1=False, child2=False | `0` | `sparse_gt_node_unmatched_to_prediction` |
| `6bba_ebdf3b34` | `14000412` | parent=True, child1=True, child2=True | `0` | `no_track_b_candidate_reaches_gt_division` |

Additional bounded graph inspection for `6bba_ebdf3b34` through frame 20 shows the exact structural miss:

- GT parent prediction: `6bba_ebdf3b34:t13:cf520`
- GT child predictions: `6bba_ebdf3b34:t14:cf601` and `6bba_ebdf3b34:t14:cf555`
- The parent is present and has two outgoing division edges, but they are to `t14:cf31` and `t14:cf601`.
- The matched second daughter `t14:cf555` is present but has no incoming edge.
- Track B has one candidate for the matched parent, but it is the wrong pair (`cf31`, `cf601`) and is itself rejected by fallback geometry: angle `115.564`, ratio `1.396`.

Interpretation: the extra `6bba_ebdf3b34` FN is not a ranking failure. It is an upstream pairing/linking failure where the candidate graph selects the wrong orphan child and never connects the actual second daughter. Ranking cannot recover a candidate that does not include the correct child pair.

## Current Assessment

The three-sample result is a NO-GO for the current ranking formula as a practical human-review list: only `1/3` known TPs appears in the top 100, and all three require looking through the top 2000. The next step should be richer candidate evidence or a learned ranker after full-cohort measurement, not a hard threshold or Track A change.

Guardrail remains unchanged: ranking does not touch Track A and does not change the candidate set, only ordering and diagnostics.


