# Correlation Layer — Phase 2: Active Injection + Ground-Truth Validation

**Status: complete. Decision = QUALIFIED NO-GO for the current naive injection.**
The node-recovery hypothesis is *confirmed* (synthetic candidates land on real
ground-truth cells), but the naive edge-injection method is *net-harmful to lineage
(edge) recall on the exact at-risk cohort it targets*, and the harm grows with the
timepoint window. Experimental branch only — no `run.py`, V13 defaults, or protected
submission path touched.

See [CORRELATION_LAYER.md](CORRELATION_LAYER.md) for Phase 1 (shadow) context.

## What was built (all new / isolated)

- `src/atabey/tracking/correlation_active.py` — `build_active_graph(graph, ...)`
  returns a NEW graph = input + injected `beacon_derived` synthetic candidates; the
  input graph is never mutated. Synthetic nodes carry the id prefix `synth::` and
  edges carry `relation="beacon_recovery"`, so real vs. recovered detections are
  separable through to final output. Guardrails are inherited verbatim from
  `compute_correlation_shadow` (min track age, consecutive cap, node-inflation
  ceiling, discount on `A_synthetic`).
- `scripts/run_correlation_active_experiment.py` — gated ablation runner
  (`--enable-correlation-active`, default OFF, separate from the shadow flag),
  `merged_6bba_only` scope, ground-truth scoring, discount sweep.
- `tests/test_correlation_active.py` — 5 tests (no-mutation, tagging, discounted
  confidence, chained edges, guardrails).
- Outputs: `submissions/correlation_active_{10tp,20tp,smoke}.json`.

## Injection method

For each shadow-proposed synthetic candidate (identical trigger/guardrails as
Phase 1), a `Detection` is inserted at the extrapolated position with
`detection_confidence = would_be_a_score` (discounted). A `beacon_recovery` edge
links it from the confirmed track leaf (or the previous synthetic frame, so
consecutive synthetics chain). Nothing is injected into any submission graph.

## Scoring methodology

Ground truth is the sparse GEFF label graph (`train/{sample_id}.geff`), scored with
the existing `evaluate_sparse_ground_truth` (greedy per-timepoint centroid match,
`match_radius_um=7.0`). Ground truth is **windowed to the built timepoints** for an
interpretable in-window recall. Two views per discount: whole cohort (66) and the
isolated at-risk subset (51, the samples with track gaps from the OSS diagnostic).

Beyond sparse recall / sparse edge recall, provenance-aware counters were added:
- **matched_by_synthetic** — GT nodes matched to a `synth::` prediction (true recovery).
- **uniquely_recovered** — GT nodes matched in active but *not* in baseline (net recall source).
- **displaced_matches** — GT nodes whose active match error is *worse* than baseline (node-level harm).

*Caveat:* sparse labels cannot measure true precision (unmatched predictions are not
necessarily false positives — same caution as every prior experiment). Node
inflation and the edge-recall delta are the precision-side proxies.

## Ablation results

| View | Metric | Baseline | 10tp active | 20tp active |
|------|--------|---------:|------------:|------------:|
| **At-risk (51)** | sparse **node** recall | 0.8482 | 0.8639 (**+0.0157**) | 0.8753 (**+0.0277**) |
| **At-risk (51)** | sparse **edge** recall | 0.6944 | 0.6869 (**−0.0075**) | 0.6856 (**−0.0137**) |
| At-risk (51) | GT nodes matched by synthetic | — | 128 | 355 |
| At-risk (51) | uniquely recovered nodes | — | 53 | 166 |
| At-risk (51) | displaced (worse) node matches | — | 0 | 0 |
| At-risk (51) | node inflation | — | 14.9% | 19.3% |
| Overall (66) | sparse node recall | 0.8143 | 0.8298 (+0.0155) | 0.8405 (+0.0276) |
| Overall (66) | sparse edge recall | 0.6896 | 0.6900 (+0.0004) | 0.6882 (−0.0104) |
| Overall (66) | injection time / sample | — | 17 ms (max 62) | 47 ms (max 116) |

**Per-sample edge outcome (10tp at-risk, 51 samples):** node recall improved on 17,
regressed on **0**; edge recall improved on 9, regressed on **15**, flat on 27. The
worst edge regressions are all `44b6_*` samples (−0.11 to −0.05).

## Core validation questions — answered

1. **True recovery vs. false continuity?** *Both.* Synthetic nodes land within 7 µm
   of real GT cells (128 → 355 GT nodes matched by synthetics; 0 node displacements),
   so node recovery is genuine. But the recovery is *positional only* — the
   `beacon_recovery` edge follows the extrapolated velocity, not the true lineage, so
   at the edge/lineage level it is partly false continuity.
2. **Quantified delta on the 51 at-risk:** node recall **+1.6% (10tp) / +2.8% (20tp)**;
   edge recall **−0.75% (10tp) / −1.4% (20tp)**. The node gain and the edge loss both
   grow with the window.
3. **False-positive cost:** yes, at the edge level. When a synthetic node is
   geometrically closer to a GT node than the real detection that had *correctly
   linked* it, the synthetic steals the node-match (node recall holds/improves) but
   the correct GT edge match is lost (edge recall drops). 15/51 at-risk samples
   regress on edges vs. 9 improving.
4. **Runtime:** still cheap — injection 17–47 ms/sample (max 116 ms at 20tp), ~0.1%
   of the CFAR graph-build cost. No regression.

**Discount factor is invariant:** discounts 0.5 / 0.6 / 0.7 produced *identical*
recall, edge-recall, and match counts. The sparse centroid matcher is geometry-only
and ignores `detection_confidence`, so the discount is invisible to this metric. It
would only matter in a confidence-weighted downstream linker/scorer, not in sparse
recall. This is an honest limitation of the available ground-truth metric, not a bug.

## Go / no-go

**NO-GO for the current naive active injection**, decided against the
pre-registered criterion (§5.1): promote only if there is a measurable positive gain
on the 51 at-risk samples *with no meaningful precision cost and no runtime regression.*

- Node recall gain: **met** (positive, measurable, 0 displacement).
- No meaningful precision cost: **not met** — edge/lineage recall regresses on the
  at-risk cohort (−1.4% at 20tp, worsening with window, 15/51 samples regress). For a
  lineage-tracking task, edge correctness is not a secondary concern.
- Runtime: met.

Per §5.2 this is logged as a clear NO-GO with the same rigor as the bounded-CFAR and
pfa/axial NO-GOs. It is a legitimate outcome, not a failure of the exercise: Phase 1
recovery *potential* was real, but converting it to end-to-end *gain* with this naive
"inject node + extrapolated edge + steal the greedy match" method costs more lineage
accuracy than it buys.

### Why it fails and what a Phase 3 would need

The defect is **node-match theft**: synthetics displace real detections at the
greedy matcher even when the real detection already carried the correct edge. A
viable Phase 3 must stop injecting where a real detection already links the cell, e.g.

1. **Gap-only injection:** inject a synthetic *only* when no real detection exists
   within the match radius at that frame (fill true holes, never overwrite a
   confirmed link) — this should preserve edge recall while keeping the node gain.
2. **Confidence-aware matching:** make the scorer/linker prefer `cfar_confirmed`
   detections over `beacon_derived` at equal-ish distance, which would also finally
   make the discount factor meaningful.
3. **Edge-provenance-preserving evaluation:** never let a `beacon_recovery` edge
   count against a real GT edge that a confirmed detection would have matched.

Until one of those is implemented and re-validated (shadow → active → go/no-go),
active injection stays off and nothing from this branch moves toward production.

### Critical guardrail (unchanged)

Even though node recovery is real, **no** promotion happens in this pass. `run.py`,
V13 defaults, and the protected submission path are untouched. Any future promotion
requires its own explicit, separately reviewed decision.
