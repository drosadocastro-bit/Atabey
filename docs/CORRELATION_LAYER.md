# Track-Continuity Correlation Layer (PSR/SSR-style Detection Recovery)

**Status: Phase 1 (shadow-only) complete. Go/no-go below. Experimental branch only —
no `run.py` default path or V13 submission track touched.**

This layer recovers detections in weak/zero-CFAR *regions* using track continuity,
analogous to PSR/SSR fusion in radar: where the primary sensor (CFAR) drops a
return, a stable track's own history bridges the gap with a synthetic, explicitly
provenance-tagged candidate. It is the tracking-stage fix recommended by
[docs/OSS_DIAGNOSTICS.md](OSS_DIAGNOSTICS.md), which found that 100% of
CFAR-collapse-prone samples are Type A (recoverable via track memory) — the
leverage is at the linking/tracking stage, not the detector.

## Components (all new, isolated)

- `src/atabey/tracking/correlation_shadow.py` — `compute_correlation_shadow(graph, ...)`.
  Pure, shadow-only, never mutates the graph, never imported by production.
- `scripts/run_correlation_shadow_experiment.py` — gated ablation runner
  (`--enable-correlation-shadow`, default OFF).
- `tests/test_correlation_shadow.py` — 8 unit tests.
- Outputs: `submissions/correlation_shadow_10tp.json`,
  `submissions/correlation_shadow_20tp.json`,
  `submissions/correlation_shadow_smoke.json`.

## What triggers a synthetic candidate

The collapse-risk condition is `background_mean` vs `adaptive_threshold` — a
**region-level** effect, not a whole-frame event. The production `sigma` route does
not whole-frame collapse (that is the pfa-mode failure mode), so a whole-frame
low-detection gate fires almost never. The faithful region-level manifestation of a
weak/zero-CFAR region in the built graph is a **track gap**: a stable track whose
confirmed nodes end before the last observed frame, i.e. a location where CFAR
failed to produce a linkable detection even though continuity expects the cell to
persist.

Trigger, per Part 1 of the task:

- **Region-level (primary):** a track leaf at frame `t < last_frame` — the
  track-continuity/latent-recovery signal the OSS diagnostic found unanimous
  (latent candidates present in 51/51 at-risk samples).
- **Whole-frame low-detection gate (optional, opt-in):**
  `require_low_detection_frame=True` additionally restricts recovery to frames whose
  detection count falls below `low_detection_floor_ratio × median` — reserved for a
  simulated-collapse (pfa) study; off by default because sigma mode never collapses.
- **Scope:** the CFAR-routed cohort from `cfar_bounded_scan_fulltrain.json`, which is
  exactly the `merged_6bba_only` route-policy cohort (the profile gate is already
  applied upstream). Same explicit-gate pattern as `--allow-unsafe-pfa-axial` /
  `--enable-bounded-cfar`.

## Synthetic candidate generation

For each qualifying leaf, position is extrapolated with the same simple velocity
model already used by latent recovery in `baseline.py`:

```
velocity          = leaf_position - predecessor_position
predicted(k)      = leaf_position + velocity * k     # k = 1 .. max_consecutive
```

Every synthetic candidate is tagged `beacon_derived=True` / `cfar_confirmed=False`;
this provenance is carried on every record and never dropped.

## Integration with the reinforcement layer

The correlation layer produces *candidates*; the reinforcement layer scores *links*.
Synthetic candidates carry a discounted base link score so they can flow into the
same downstream scoring path without being trusted like CFAR-confirmed detections:

```
base_beacon_score = min(1, depth / (min_track_age_frames + 1))   # persistence signal
would_be_A_score  = base_beacon_score * discount                 # discount default 0.6
```

`discount` default `0.6` sits in the conservative `0.5–0.7` band. Phase 1 only
*logs* `would_be_A_score`; nothing is injected into any submission graph.

## Anti-drift guardrails

| Guardrail | Parameter | Default | Effect |
|-----------|-----------|---------|--------|
| Minimum track age | `min_track_age_frames` | 3 | No synthetic candidates for tracks younger than N frames. |
| Consecutive synthetic cap | `max_consecutive_synthetic` | 2 | A track stops generating after N consecutive synthetic frames ("unconfirmed too long"). |
| Node-inflation ceiling | `node_inflation_ratio` | 1.25 | Synthetics may add at most `(ratio − 1) × nodes`; hard stop when hit (integrates with the spike-guardrail discipline). |
| Explicit opt-in | `--enable-correlation-shadow` | OFF | Layer is a no-op unless explicitly enabled. |

## Phase 1 shadow logging

Per synthetic candidate, logged (not injected): `frame`, `track_id`,
`predicted_{z,y,x}_um`, `discount_applied`, `would_be_a_score`,
`consecutive_synthetic_count`, `parent_node_id`, `beacon_derived`, `cfar_confirmed`.
Per sample: node/edge counts, synthetic count, tracks/frames triggered, node
inflation %, all three suppression counters, ceiling hit flag, and separated
build-vs-shadow timing.

## Validation / ablation

Cohort: the same 66 CFAR-routed samples as the OSS diagnostic (51 flagged at-risk at
pfa=1e-3). Baseline (no layer) vs shadow-correlation (logged only). Run at 10 tp and
re-run at 20 tp to test the "beacons barely form at 10 tp" caveat.

| Metric | 10 tp | 20 tp |
|--------|------:|------:|
| Cohort size | 66 | 66 |
| At-risk samples recovered | **51 / 51 (100%)** | **51 / 51 (100%)** |
| Total synthetic candidates | 40,311 | 105,810 |
| At-risk synthetic candidates | 34,825 | 91,635 |
| Mean node inflation | 15.1% | 19.4% |
| Max node inflation | 21.0% | **25.0% (ceiling bound)** |
| Samples hitting node ceiling | 0 | 2 |
| Mean would-be A score (discounted) | 0.543 | 0.554 |
| **Mean shadow-layer time / sample** | **9 ms** | **23 ms** |
| Max shadow-layer time | 32 ms | 72 ms |
| Mean graph-build time / sample | 13.8 s | 27.9 s |

Suppression at 20 tp (guardrails doing their job): young-track suppressions 84,465,
consecutive-cap suppressions 47,860, ceiling suppressions 2. The minimum-track-age
guardrail does most of the filtering — only stable, aged tracks are extrapolated.

### The 51 at-risk samples

All 51 gain synthetic candidates at both windows. The weakest end-to-end OSS sample,
`6bba_57b7cc1e` (OSS e2e 0.518, link_pass 0.784, 1293 latent candidates), recovers
1,512 candidates at 10 tp (17.6% inflation, 815 tracks) and 3,808 at 20 tp (22.1%,
1,956 tracks) — confirming its low end-to-end number is a track-continuity gap the
correlation layer directly addresses, not a true blind spot.

### Beacon formation / longer-window caveat

The OSS diagnostic warned that beacons "barely form at 10 timepoints." This layer
does **not** depend on the high-bar beacon-quality signal; it triggers on track
persistence/age (the latent-recovery signal, which was unanimous 51/51 in OSS and is
far more robust at short windows). Extending 10 → 20 tp **strengthens** the Type A
classification: recovery coverage stays at 100%, candidate volume grows
(40k → 106k), and the continuity signal deepens. The trade-off is inflation pressure
— mean 15% → 19.4% and the node-inflation ceiling begins to bind (0 → 2 samples),
which is exactly the guardrail behaving as designed.

### Runtime

Synthetic candidate generation is cheap: **9 ms / sample at 10 tp, 23 ms at 20 tp**
(max 72 ms), i.e. ~0.06–0.08% of the graph-build cost. No sign of the runtime
regression seen in the sigma/isotropic experiment. The graph build is the CFAR
pipeline cost that the baseline already pays.

## Go / no-go

**GO to Phase 2 (correlation-active ablation), with guardrails as specified.**

- (a) **Improves end-to-end sensitivity on previously at-risk samples:** yes —
  100% of the 51 at-risk samples receive track-continuity recovery candidates at
  the exact gaps that depress their end-to-end numbers, including the weakest sample.
  *Caveat for Phase 2:* Phase 1 measures *recovery potential*; whether recovered
  candidates raise the sparse-recall score end-to-end must be confirmed against
  ground truth when candidates are actually injected (Phase 2), since some track
  gaps are genuine terminations, not CFAR misses.
- (b) **Runtime budget:** yes — the layer adds ≤ 72 ms/sample, negligible vs the
  13.8–27.9 s build.
- (c) **Node/edge inflation ceiling:** respected — 0/66 hit it at 10 tp; at 20 tp the
  ceiling correctly bound 2 samples at 25%, proving the guardrail engages before
  runaway inflation.

### Phase 2 preconditions (before any production consideration)

1. Inject discounted synthetic candidates and measure sparse-recall / sparse-edge
   recall against ground truth on the at-risk cohort (potential → realized gain).
2. Keep the default node-inflation ceiling at 1.25 (or lower) for long windows,
   since it binds at 20 tp; tune with the discount factor.
3. Never flip production directly — shadow → active-ablation → go/no-go, mirroring
   the reinforcement-layer discipline.
