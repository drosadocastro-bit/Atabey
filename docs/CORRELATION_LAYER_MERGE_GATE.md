# Correlation Layer — Phase 3: Identity De-Duplication / Merge Gate

**Status: QUALIFIED GO (mechanism fix validated).** Experimental branch only.
No change to `run.py`, V13 defaults, or `hybrid_config` production defaults.

## Motivation

Phase 2 (active injection, see `CORRELATION_LAYER_PHASE2.md`) was a **QUALIFIED
NO-GO**: synthetic (beacon-derived) candidates delivered a real **node-recall gain**
(+0.0157 at-risk, 10tp) but **regressed edge recall** (−0.0075 at-risk). The
hypothesis was a *double-target collision*: a synthetic candidate and a real,
CFAR-confirmed candidate compete for the same ground-truth identity. Because the
sparse matcher is geometry-only and greedy, the synthetic can win the node match
(node recall holds) while its extrapolated `beacon_recovery` edge is not the true
lineage edge — orphaning the real node's correct edge (edge recall drops).

Phase 3 adds a **merge gate**: before a synthetic is injected, check for a real
detection in a small spatio-temporal neighbourhood. If one exists, the real
detection already covers that identity, so the synthetic is suppressed. Synthetics
are then only ever injected into **genuine gaps**, restoring the layer's original
intent (track-continuity recovery) rather than identity competition.

## Merge gate design

Implemented in `src/atabey/tracking/correlation_shadow.py` (shadow layer; the
active injector inherits it verbatim via `build_active_graph`).

For every would-be synthetic at `(gap_frame, predicted_position)`:

1. Search real detections within `merge_gate_radius_um` (Euclidean, µm) across the
   frame window `[gap_frame − merge_gate_frame_window, gap_frame + merge_gate_frame_window]`.
2. **Exclude the track's own confirmed nodes** (leaf + ancestors) from this search —
   otherwise the track's own predecessor at `gap_frame − 1` (≈ the extrapolation
   origin) would trivially register as a "collision".
3. Flag the candidate `collides_with_real`. This is always computed (diagnostic).
4. When `apply_merge_gate=True`, a colliding candidate is **suppressed** (counted in
   `suppressed_by_merge_gate`) and extrapolation for that leaf stops — a real
   detection covers the immediate gap, so it is not a genuine gap.

### Tolerance chosen

| Parameter | Default | Rationale |
|---|---|---|
| `merge_gate_radius_um` | **3.0** | Conservative. Below the 7.0 µm GT match radius so it only fires when a real detection is *clearly* the same identity; small enough to avoid suppressing legitimately close-but-distinct cells in dense regions. |
| `merge_gate_frame_window` | **1** | Same/adjacent frame temporal tolerance, matching the "same/adjacent frame" requirement. |
| `apply_merge_gate` | `False` (default OFF) | Explicit opt-in; diagnostic-only unless enabled. |

## Part 1 — Double-target hypothesis: confirmation

Diagnostics come from the no-gate run (all synthetics emitted, each flagged
`collides_with_real`). At-risk cohort, 10tp, 47 scored samples:

- **27%** of synthetics (9,542 / 34,825) land within 3 µm of a real detection —
  i.e. roughly one in four synthetics is a potential double-target.
- Of the **15** at-risk samples that regressed on edge recall (no-gate), the **4
  worst** are the clearest double-target cases:

  | sample | collision frac | no-gate node Δ | no-gate edge Δ | **gated edge Δ** |
  |---|---|---|---|---|
  | 44b6_66f9292d | 0.377 | +0.000 | −0.111 | **0.000** |
  | 44b6_8cc6506c | 0.319 | +0.000 | −0.111 | **0.000** |
  | 44b6_9bfa6a0a | 0.331 | +0.000 | −0.056 | **0.000** |
  | 44b6_144b256d | 0.353 | +0.050 | −0.037 | **0.000** |

  These have **high collision fractions** and, critically, **zero (or gate-removable)
  node gain** — the synthetics contributed no genuine node recovery but broke real
  edges. The merge gate neutralises them **completely**. This is the textbook
  identity-theft signature and directly confirms the hypothesis.

- **11 of 15** regressed samples improve under the gate; **6** become fully
  neutral-or-positive.

### Second cause (honest caveat, Part 1.2)

Not all regression is double-target collision. `44b6_40c45f5a` holds **+0.10 node /
−0.089 edge in *both* conditions** — the gate barely touches it (only 81 suppressed).
Its synthetics land in **genuine gaps** (no nearby real detection) and genuinely
recover nodes, but their velocity-extrapolated `beacon_recovery` edges are the *wrong
lineage*. This is a distinct failure mode (gap recovery with incorrect edges) that a
merge gate cannot and should not fix — correctly, the gate leaves these synthetics in
place. It accounts for most of the residual at-risk edge regression.

## Part 3 — Three-way ablation (10tp, identical cohort & GT scoring)

| Condition | node recall Δ | edge recall Δ |
|---|---|---|
| **At-risk (51 samples, primary bar)** | | |
| baseline (no correlation layer) | — (0.8482) | — (0.6944) |
| Phase 2, **no** merge gate | **+0.0157** | **−0.0075** |
| Phase 3, **with** merge gate | **+0.0111** | **−0.0017** |
| **Overall cohort (66 samples)** | | |
| baseline | — (0.8143) | — (0.6896) |
| Phase 2, no gate | +0.0155 | +0.0004 |
| Phase 3, with gate | **+0.0117** | **+0.0019** |

Additional (at-risk, gated): 6,942 of 34,825 synthetics suppressed (collisions);
23,175 genuine-gap synthetics injected (66.5% retained); 0 displaced matches;
injection stays ms-scale (mean ≈ 189 ms/sample incl. both injections + scoring).

**Interpretation:**
- **Edge regression essentially neutralised**: −0.0075 → −0.0017 (77% removed). The
  residual is dominated by the genuine-gap-wrong-edge second cause, not collisions.
- **Node gain persists** (+0.0111) but is **~29% smaller** than no-gate. Per Part 3.4,
  this is expected and honest: part of the original node "gain" *was* double-target
  collision (a synthetic matching a GT node the real detection already covered). The
  remaining gain is genuine — 53 uniquely-recovered GT nodes (overall 65), 0 displaced.
- **Overall cohort is net-positive on both node and edge** with the gate.

## Part 4 — Dense-region stress check

Densest at-risk samples (by baseline node count), gated vs no-gate:

| sample | nodes | synth → gated | suppressed | collision frac | node Δ (no→gate) | edge Δ (no→gate) |
|---|---|---|---|---|---|---|
| 6bba_57b7cc1e | 8615 | 1512 → 952 | 326 | 0.297 | +0.040 → +0.017 | −0.023 → −0.019 |
| 6bba_b329af44 | 8407 | 1672 → 1207 | 289 | 0.225 | +0.044 → +0.044 | +0.012 → +0.005 |
| 44b6_144b256d | 7855 | 994 → 579 | 243 | 0.353 | +0.050 → +0.000 | −0.037 → +0.000 |
| 44b6_18ced818 | 7641 | 1364 → 929 | 267 | 0.262 | 0.000 → 0.000 | 0.000 → 0.000 |
| 6bba_ebff6e76 | 7413 | 1294 → 789 | 298 | 0.320 | +0.026 → +0.009 | −0.026 → −0.015 |

No over-suppression: the gate retains the majority of synthetics even in the densest
samples (e.g. 952/1512, 1207/1672), densest samples remain net-positive on node
recall, and no dense sample flips from positive to negative. The conservative 3.0 µm
radius does not collapse legitimately close-packed cells.

## Go / No-Go

**QUALIFIED GO — mechanism fix validated; promotable to further consideration.**

Against the bar ("genuine node recall gain WITH edge recall neutral-to-positive and
no dense-region over-suppression"):

- ✅ **Genuine node recall gain preserved** (+0.0111 at-risk, +0.0117 overall;
  53 uniquely recovered, 0 displaced).
- ◐ **Edge recall**: overall cohort **positive** (+0.0019); at-risk **near-neutral**
  (−0.0017, 77% of the regression removed). Not strictly ≥ 0 on the at-risk cohort —
  the residual is the *genuine-gap-wrong-edge* second cause, not double-targeting.
- ✅ **No dense-region over-suppression.**

The merge gate resolves the specific identity-theft failure that made Phase 2 a
NO-GO. The remaining at-risk edge shortfall is a **different, smaller mechanism**
(extrapolated lineage error in true gaps) and is a candidate for a follow-up
(e.g. edge-confidence-aware matching or extrapolation validation), not a blocker.

## Artifacts

- Gate + diagnostics: `src/atabey/tracking/correlation_shadow.py`
  (`merge_gate_radius_um`, `merge_gate_frame_window`, `apply_merge_gate`;
  `collides_with_real`, `synthetic_collision_count`, `synthetic_gap_count`,
  `suppressed_by_merge_gate`).
- Injection threading: `src/atabey/tracking/correlation_active.py` (`build_active_graph`).
- 3-way ablation runner: `scripts/run_correlation_active_experiment.py`
  (`--merge-gate-radius`, `--merge-gate-frame-window`; reports no-gate vs gated +
  `dense_region_check`).
- Results: `submissions/correlation_merge_gate_10tp.json`,
  `submissions/correlation_merge_gate_smoke.json`.
- Tests: `tests/test_correlation_shadow.py` (collision flag, suppression,
  genuine-gap injection, radius tunability).

---

# Integration Test — Merge-Gated Recovery vs. V13 (Real Pipeline Path)

Phase 3 validated the merge gate in isolation (`run_correlation_active_experiment.py`).
This section integrates it into the **production runners** and measures it on the
**real scoring path** used for V13, behind an explicit opt-in flag, default OFF.
**V13 remains the protected, frozen baseline throughout — `run.py` / kernel defaults
are untouched.**

## Part 1 — Wiring (gated OFF)

New opt-in flag `--enable-correlation-recovery` (default **OFF**) added to both
`scripts/run_hybrid_submission.py` and `scripts/run_hybrid_train_evaluation.py`,
consistent with existing experimental gates (`--allow-unsafe-pfa-axial`,
`--enable-correlation-shadow`, `--enable-correlation-active`). Tunables:
`--correlation-merge-gate-radius` (3.0), `--correlation-merge-gate-frame-window` (1),
`--correlation-discount` (0.6). Recovery calls the validated
`build_active_graph(..., apply_merge_gate=True)` and applies **only on the CFAR route**
(`use_cfar` / `detector == "cfar_sidelobe"`); it never mutates the input graph.

**Regression (flag OFF = V13, byte-identical):**
- Flag-OFF submission CSV is deterministic and byte-identical across repeat runs.
- With flag ON, all **non-CFAR sample rows are byte-identical** to flag-OFF; only the
  CFAR-routed sample changes.
- Full suite: **70 passed**. v9_style_adaptive route metrics are **unchanged**
  (Δnode = Δedge = Δquality = 0.000000) between ON and OFF.

## Part 2 — Bounded smoke + provenance

`run_hybrid_submission.py --input-dir train --max-samples 3 --max-timepoints 8
--enable-correlation-recovery`: CFAR-routed `44b6_0c582fdc` injected **286 synthetic
recovery nodes (107 merge-gate-suppressed)**; Kaggle CSV schema stayed valid.
The **Kaggle CSV is schema-locked** (`KAGGLE_SUBMISSION_COLUMNS`, no provenance
columns); provenance survives instead in (a) the internal graph (`synth::` node ids,
`beacon_recovery` edge relation) and (b) the **report JSON** record fields
`correlation_recovery_enabled`, `correlation_synthetic_count`,
`correlation_suppressed_by_merge_gate`, `correlation_merge_gate_radius_um`.

## Part 3 — Full train-eval, real metric (66-sample CFAR cohort, 10 tp, ON vs OFF)

Official pipeline metric `quality_score = 0.5·node + 0.5·edge`
(`evaluate_sparse_ground_truth`, match_radius 7.0 µm), hybrid_cfar_sidelobe route:

| metric | OFF | ON | Δ |
|---|---|---|---|
| mean sparse node recall | 0.074676 | 0.076227 | **+0.001550** |
| mean sparse edge recall | 0.688735 | 0.691028 | **+0.002292** |
| **mean quality_score** | 0.350400 | 0.352217 | **+0.001817** |

- **Translation is weak.** The isolated node gain (+0.0117) **compressed to +0.00155**
  on the real pipeline metric; edge (+0.0019 → +0.0023) translated roughly intact.
  Synthetic nodes mostly fill gaps that are not at sparse-GT anchor locations, so node
  recall over sparse anchors barely moves.
- **Runtime: no regression.** Recovery injection is ms-scale; end-to-end hybrid-route
  time did not increase (ON 14.37 s vs OFF 19.71 s/sample — the ON run was second with
  a warm disk cache; recovery cost itself is negligible).

## Part 4 — Wrong-edge caveat confirmed

The known second-cause sample **`44b6_40c45f5a` is the single worst regression**
(Δquality **−0.039444**, synth 275 / gated 81). The genuine-gap-wrong-edge mechanism
flagged in Phase 3 is a **real, measurable drag** on the full path.

## Part 5/6 — Distribution & outside-cohort check

Per-sample hybrid-route quality Δ (66 samples): **16 improved, 11 regressed, 39 unchanged.**

| cohort | n | mean Δquality | improved / regressed / unchanged |
|---|---|---|---|
| ALL | 66 | +0.001817 | 16 / 11 / 39 |
| AT-RISK (51, the target) | 51 | **+0.000243** | 9 / 9 / 33 |
| OUTSIDE at-risk (15) | 15 | +0.007168 | 7 / **2** / 6 |

- The **target at-risk cohort is essentially flat (+0.00024)**; the net gain is driven
  incidentally by the **outside** cohort.
- **Part 5 "no outside regression" criterion is VIOLATED**: two not-at-risk CFAR
  samples regress — `6bba_6feb10f0` (−0.0147), `6bba_4ffd3da3` (−0.0144).

## Go / No-Go — V15 submission candidacy

**NO-GO for V15 submission candidacy under the stated criteria.**

Promotion required (Part 5): measurable positive gain on the **real** metric for the
**target** cohort, acceptable runtime, **and no outside-cohort regressions**.

- ◐ Overall quality gain is positive but **small (+0.0018)** and does **not** come from
  the intended at-risk cohort (flat at +0.00024).
- ✅ Runtime within bounds (recovery is ms-scale).
- ❌ **Outside-cohort regressions present** (`6bba_6feb10f0`, `6bba_4ffd3da3`), and the
  worst-drag caveat sample (`44b6_40c45f5a`, −0.039) is confirmed on the real path.

**V13 stays the protected, submitted baseline.** The merge-gated recovery mechanism is
correctly wired and safe (clean default-OFF no-op, provenance surfaced), but the gain
does not robustly translate to the real scoring path on the target cohort and
introduces outside-cohort regressions. Follow-up candidate before any resubmission:
edge-confidence-aware / extrapolation-validated recovery to remove the wrong-edge drag,
plus scoping recovery to only the samples where it demonstrably helps.

## Integration artifacts

- Runner flags: `scripts/run_hybrid_submission.py`,
  `scripts/run_hybrid_train_evaluation.py` (`--enable-correlation-recovery` +
  merge-gate/discount tunables; default OFF; CFAR-route only).
- Full ON/OFF results: `submissions/v15_traineval_OFF.json`,
  `submissions/v15_traineval_ON.json` (+ `_summary.json`).
</content>
</invoke>
