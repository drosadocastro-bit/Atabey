# V23 Candidate-Axis Topology Audit Results

Decision: **HOLD_CANDIDATE_AXIS_TOPOLOGY**.

This fixed six-event audit tests a raw-image one-lobe to two-lobe transition along each proposed daughter axis. Unknown alternatives remain unknown. No model was fitted and no graph was changed.

| Event | Role | Family | Pairs | Topology rank | Percentile | Static rank | Delta |
|---|---|---|---:|---:|---:|---:|---:|
| 44b6_7a302da0 t90 | repairable | 44b6 | 55 | 23 | 60.0% | 39 | +16 |
| 44b6_9be80b04 t77 | protected_complete | 44b6 | 66 | 4 | 95.5% | 3 | -1 |
| 44b6_c50204e0 t28 | protected_complete | 44b6 | 55 | 31 | 45.5% | 55 | +24 |
| 6bba_05db0fb1 t24 | protected_complete | 6bba | 21 | 6 | 76.2% | 6 | +0 |
| 6bba_207c6aaf t41 | repairable | 6bba | 36 | 27 | 27.8% | 22 | -5 |
| 6bba_474be664 t63 | repairable | 6bba | 66 | 25 | 63.6% | 57 | +32 |

Pooled median percentile: 61.8%. Top-10 capture: 2/6. Rank improved/flat/regressed versus static endpoint support: 3/1/2.

This differs from the rejected Hough precursor: Hough tested parent-frame bimodality alone, while this feature is candidate-conditioned and measures the temporal transition from one centered lobe to two endpoint lobes.

Guardrail: even a GO would authorize only an independent sample-blocked validation of this raw feature source, not a scorer, assignment integration, graph mutation, or full-cohort run.
