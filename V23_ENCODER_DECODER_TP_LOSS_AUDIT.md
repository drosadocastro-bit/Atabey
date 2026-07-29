# V23 Encoder-Decoder Official-TP Loss Audit

## Scope

This is a paired, read-only comparison of the existing 46-event control and
frozen encoder-decoder availability exports. It investigates why the learned
detector produced fewer official TP actions than the control in some cases.
No graph or route was changed.

## Summary

- Control: `64` official TP actions, `39/46` events available.
- Encoder-decoder: `55` official TP actions, `40/46` events available.
- Availability transitions: `37` stable available, `4` stable unavailable,
  `3` control-unavailable to encoder-decoder-available, `2` control-available
  to encoder-decoder-unavailable.
- The two `1->0` transitions are both CFAR-routed cases.

The learned detector improves overall availability by one event but does not
preserve official TP action identity. Its lower action volume is therefore a
real candidate-set reduction, not a clean replacement.

## Case-level TP changes

| Case | Route | Control TP | U-Net TP | Availability | Interpretation |
|---|---|---:|---:|---|---|
| `44b6_5f15d135:t36` | local maxima | 4 | 6 | 1->1 | learned detector adds recognized actions |
| `44b6_74d0c52e:t58` | CFAR | 2 | 0 | 1->0 | availability regression |
| `44b6_c50204e:t28` | CFAR | 0 | 1 | 0->1 | learned detector recovers an unavailable event |
| `6bba_2819ca14:t61` | components | 1 | 2 | 1->1 | learned detector adds one action |
| `6bba_57b7cc1e:t12` | CFAR | 6 | 4 | 1->1 | identity/action loss despite availability |
| `6bba_57b7cc1e:t23` | CFAR | 1 | 0 | 1->0 | availability regression |
| `6bba_57b7cc1e:t77` | CFAR | 2 | 1 | 1->1 | identity/action loss |
| `6bba_6321a359:t8` | components | 2 | 1 | 1->1 | identity/action loss |
| `6bba_7d3058ae:t32` | components | 4 | 2 | 1->1 | identity/action loss |
| `6bba_cdcfe533:t86` | components | 0 | 1 | 0->1 | learned detector recovers an unavailable event |
| `6bba_d2b9fc0c:t72` | components | 2 | 1 | 1->1 | identity/action loss |
| `6bba_d2b9fc0c:t78` | components | 4 | 2 | 1->1 | identity/action loss |
| `6bba_debd7bfa:t26` | components | 6 | 2 | 1->1 | identity/action loss |
| `6bba_ef7b4f7e:t89` | components | 1 | 2 | 1->1 | learned detector adds one action |
| `6bba_fc5f39dc:t54` | CFAR | 0 | 1 | 0->1 | learned detector recovers an unavailable event |

## What determines the losses?

The losses separate into two mechanisms:

1. **Formation/availability loss:** two CFAR cases lose all recognized
   actions. For `44b6_74d0c52e:t58`, the learned detector produces more parent
   peaks but zero registered geometric actions, versus two in the control.
   For `6bba_57b7cc1e:t23`, it produces fewer parent/anchored peaks and zero
   registered actions, versus one in the control.
2. **Candidate identity/count change:** in the remaining available cases, the
   learned detector changes the peak population and action pool. It can reduce
   or add recognized official actions without a simple monotonic relationship
   to total action count.

The evidence does not support describing the encoder-decoder as a uniformly
cleaner detector. It is a lower-volume detector with a different recall
profile. In particular, the CFAR route contains both the strongest regressions
and recoveries, so route replacement is not justified.

## Decision

**Keep CFAR active and quarantined as the route control/fallback.** Do not
remove it or let the encoder-decoder replace it globally.

The encoder-decoder remains useful for detector-native feature extraction and
possibly a future gated shadow, but the next diagnostic should focus on the two
CFAR availability regressions and compare pre-threshold heatmap evidence at
those exact frames. No threshold tuning or production routing change is
authorized by this audit.
