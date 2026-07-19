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

## Missed GT Diagnostic

For the bounded `6bba_05db0fb1` window, the two missed GT divisions had no matched sparse GT parent or daughter predictions, so Track B could not recover them as ranking failures. They are upstream detection/matching misses in this bounded context.

The still-open target from the three-sample run is the second GT division in `6bba_ebdf3b34` (`FN=1`). The ranking analyzer's missed-output CSV is designed to classify it as one of:

- sparse GT nodes unmatched to predictions;
- candidate exists but Track B gate rejected;
- accepted candidate exists but one-to-one TP matching assigned another candidate;
- no Track B candidate reaches the GT division.

## Current Assessment

The first bounded result makes Track B more plausible as a human-review candidate list: the known TP moved from rank `179` under the original score to rank `10` under the separation/balance/density ranking. This is not yet a GO. The next evidence must be the full three-known-TP ranking run, followed by full-cohort validation.

Guardrail remains unchanged: ranking does not touch Track A and does not change the candidate set, only ordering and diagnostics.
