# V23 Parallel CFAR vs Encoder-Decoder Shadow Results

Decision: **HOLD; retain CFAR as fallback while the encoder-decoder route is redesigned**.

This is a paired, read-only comparison of existing exports. No detector was retrained, no graph was mutated, and no production route was changed.

## Pooled comparison

| Arm | Available | Availability | Actions | Official TP actions |
|---|---:|---:|---:|---:|
| CFAR control | 39/46 | 0.848 | 268,822 | 64 |
| Encoder-decoder | 40/46 | 0.870 | 211,328 | 55 |
| Availability fallback | 42/46 | 0.913 | 208,175 | 58 |

Fallback used on `6/46` cases (0.130).
Encoder-decoder action volume relative to control: `0.786`.

## Route breakdown

| Route | Cases | Control avail | U-Net avail | Fallback avail | Control actions | U-Net actions |
|---|---:|---:|---:|---:|---:|---:|
| cfar_sidelobe/bipartite | 11 | 7 | 7 | 9 | 218,024 | 159,812 |
| components/greedy | 34 | 31 | 32 | 32 | 44,180 | 40,199 |
| local_maxima/motion_mutual | 1 | 1 | 1 | 1 | 6,618 | 11,317 |

## Interpretation

- The encoder-decoder improves event availability by two cases in the paired set, but loses two control-positive cases and does not yet prove preservation of official TP action identity.
- It reduces candidate volume substantially, which is promising for computational cost and noise exposure.
- The fallback recovers availability when the encoder-decoder is unavailable, but its fallback rate and route distribution must remain visible; it is not a replacement result.
- This comparison does not provide official FP counts per arm; the availability exports contain registered actions and official TP actions, not a complete per-arm FP table.

## Decision

**HOLD.** Keep CFAR quarantined but available as fallback. The encoder-decoder route is promising enough for a CFAR-specific representation audit, not for route removal or production integration.

Graph mutation remained false for every row in both source exports.
