# Overall System Sensitivity (OSS) Budget Diagnostic

Status: **READ-ONLY DIAGNOSTIC / CALIBRATION**. No new detection or linking logic,
no production defaults touched. This pass re-uses the production CFAR + sidelobe
primitives, the production linker, and the shadow-only reinforcement summaries to
measure where end-to-end sensitivity is lost and to classify collapse-prone
samples as recoverable (Type A) vs. true blind spots (Type B).

Artifacts (new, isolated):
- `scripts/run_oss_diagnostics.py` — the read-only instrumentation runner.
- `submissions/oss_diagnostics.json` — full per-sample budget + classification.

Inputs re-used without regeneration:
- `submissions/cfar_bounded_scan_fulltrain.json` — routed cohort (66) + pfa
  collapse-risk flags (51 at risk at pfa=1e-3).

Measurement scope: the 66 CFAR-routed samples, 10 timepoints each. The production
CFAR route runs in **sigma** mode (which does not collapse); the 77% collapse rate
is the experimental **pfa** mode failure. The OSS pass therefore measures the real
sigma-mode pipeline continuity and uses that same run's track-memory output to
decide whether the hypothetical pfa collapses are recoverable.

## 1. Per-stage attenuation budget

Each stage is a pass factor; chaining them gives an effective per-candidate
detection→tracked-node probability. Reinforcement shadow is read as a
recovery-availability signal, not a discard stage.

| stage | factor | cohort mean (66) | at-risk median (51) | min (at-risk) |
|---|---|---|---|---|
| input signal | SNR proxy (survivor norm / background) | 7.07 | 3.25 | 1.80 |
| CFAR | `cfar_pass` = survivors / candidates | 0.959 | 0.974 | 0.743 |
| sidelobe | `sidelobe_pass` = post / pre | 0.929 | 0.932 | 0.668 |
| linking | `link_pass` = linked nodes / detections | 0.860 | 0.870 | 0.770 |
| **end-to-end** | product of the three | **0.767** | **0.786** | **0.518** |
| reinforcement | beacon fraction | 0.0002 | 0.000 | 0.000 |
| reinforcement | latent-recovery candidates | — | 446 | 26 |

Reading the chain:
- **CFAR (sigma) is not the bottleneck.** In production sigma mode it passes ~96%
  of candidates; the collapse is exclusively a pfa-mode threshold artifact.
- **Sidelobe discards ~7%** on average — modest and expected.
- **Linking is the largest single attenuation (~14%)** but still passes ~86% of
  detections into multi-frame tracks; even the worst sample links 77%.
- **End-to-end effective sensitivity ~0.77** — the routed cohort tracks well when
  CFAR is in its non-collapsing (sigma) regime.

## 2. Type A vs Type B classification

For every at-risk sample (collapse at pfa=1e-3), Type A (recoverable) is asserted
when the non-collapsing production run shows usable track memory near the
collapse: a stable beacon-grade track, an active latent-recovery bridge, OR
clearly persistent multi-frame tracks (`link_pass >= 0.5` and
`mean_persistence >= 0.5`).

| classification | count | % of at-risk (51) |
|---|---|---|
| **Type A — recoverable** | **51** | **100%** |
| **Type B — true blind spot** | **0** | **0%** |

Signal breakdown (drivers can overlap):
- Latent-recovery candidates > 0: **51 / 51** (unanimous; min 26, median 446 gaps
  the existing shadow could bridge).
- Persistent multi-frame tracks (`link>=0.5` & `persist>=0.5`): 48 / 51.
- Beacon-grade tracks (≥1): 17 / 51.
- Samples with **no** recovery signal of any kind: **0 / 51**.

The classification is multiply corroborated: the latent-recovery signal and the
persistence signal independently agree on ~48 of 51 samples, and latent recovery
is unanimous. Even the weakest end-to-end sample (`6bba_57b7cc1e`, e2e 0.518)
carries 1293 latent candidates and links 78% of its detections — abundant memory.

Caveat: beacon-grade tracks barely form at 10 timepoints (median beacon_count 0),
so Type A rests on latent-recovery candidates and multi-frame persistence rather
than beacons. Both are strong and unanimous here, but a longer-horizon run would
be needed to characterize beacon formation specifically.

## 3. Aggregate OSS metric vs. raw CFAR-only failure

| metric | value |
|---|---|
| raw CFAR-only collapse rate (pfa=1e-3) | 77.3% (51/66) |
| Type A fraction of at-risk | 100% |
| Type B fraction of at-risk | 0% |
| **effective system-wide blind-spot rate** | **~0%** |
| cohort mean end-to-end sensitivity (sigma prod.) | 0.767 |

**The 77% raw CFAR-only failure rate is almost entirely masked by downstream track
continuity.** The collapse is an isolated-frame threshold artifact; the frames
around each collapse still detect and track normally (link_pass ≥ 0.77 everywhere,
latent candidates ≥ 26 everywhere), so track memory is available to bridge the gap
for every at-risk sample. The genuine system-wide sensitivity gap is effectively
zero: there are no first-appearance/high-background samples in this cohort that
lack any recoverable signal.

## 4. Recommendation

**Type A is dominant (100%) → a correlation / track-continuity layer is
well-justified and targeted. Proceed to build it.**

- The leverage is at the **tracking/reinforcement layer, not the detector
  threshold**. This is consistent with the bounded-CFAR result
  (`docs/CFAR_BOUNDED_REFORMULATION.md`, NO-GO): fixing the CFAR threshold form
  alone avoided collapse but recovered no quality, because the surviving
  detections were mislocated. Here we show the opposite lever is promising —
  every collapse case sits inside a sample with strong, exploitable track memory.
- A correlation layer that propagates track state across frames (using the latent
  candidates already surfaced by shadow mode) directly addresses the recoverable
  Type A failure mode and has abundant signal to work with on all 51 samples.
- No case is Type B, so no effort should be spent trying to manufacture signal
  where none exists; the blind-spot risk that would have doomed a correlation
  layer is absent in this cohort.

### Guardrail honored

This was a read-only pass over existing data and existing production primitives.
No detection/linking logic was added or changed; no production defaults, `run.py`,
or the protected V13 submission track were touched. Full suite remains at 53
passed.
