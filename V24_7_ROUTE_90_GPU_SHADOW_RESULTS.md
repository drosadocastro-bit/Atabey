# V24.7 Route-90 Commitment plus ILP GPU Shadow Results

Date: 2026-08-30

Status: **COMPLETE; NO-GO FOR PROMOTION**.

This is retrospective opened-label evidence. It does not authorize threshold
tuning, a V19/V24 selector, production graph mutation, submission, or deployment.

## Integrity

- archive: `v24_7_route_90_shadow_outputs.zip`
- archive SHA-256:
  `cbc1583536d444f6c5dc7bb7cee76cfc34b556eb4b146c15db51c07c1ac6df7d`
- runner commit:
  `b5fc79582c9ce713587fa94aa8cf73fd0aa68e40`
- frozen checkpoint SHA-256:
  `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`
- frozen predictor SHA-256:
  `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`
- 90 expected and 90 unique sample records; no missing or unexpected IDs
- full sequences; U-Net batch size 4
- deterministic replay passed on `6bba_05b6850b`
- all 90 source graphs remained unmutated
- ZIP CRC check passed

The run completed in 2,702.68 seconds (45.04 minutes). Per-sample total runtime
summed to 2,664.50 seconds; median was 27.80 seconds and p90 was 36.94 seconds.

## Root Trigger

The ROOT-inspired commitment audit produced 631 changed-assignment windows:

| Stratum | Samples | Changed windows | Persistent | Persistent rate |
|---|---:|---:|---:|---:|
| Regression-16 | 16 | 99 | 9 | 9.09% |
| Route-control-74 | 74 | 532 | 75 | 14.10% |
| Route-90 | 90 | 631 | 84 | 13.31% |

Persistent effects were not enriched in the retrospective regression stratum.

## Contained Primary

The fixed primary used the preregistered 2.0 um per-change penalty and 0.5 um
minimum improvement gate.

- 619 windows solved optimally and 12 exceeded the variable budget; there were no
  solver errors, timeouts, or infeasible results.
- 55 windows received `shadow_alternative`; all 55 were ownership rewrites.
- 46 of those accepted alternatives were inapplicable to the pruned V24.3 graph.
- 9 accepted ownership rewrites were scoreable: 2 in regression samples and 7 in
  controls.
- all 9 scoreable rewrites were exactly neutral on adjusted-edge and raw-edge
  Jaccard.
- all 8 persistent primary ownership proposals were inapplicable after pruning;
  no persistent primary rewrite was scoreable.

The contained primary therefore produced no retrospective metric improvement and
does not support promotion.

## Zero-Penalty Diagnostic

The diagnostic accepted 296 ownership rewrites. Only 42 were scoreable against
the pruned V24.3 graph:

| Stratum | Scoreable rewrites | Improved | Neutral | Regressed | Mean adjusted delta |
|---|---:|---:|---:|---:|---:|
| Regression-16 | 7 | 2 | 5 | 0 | +0.00069179 |
| Route-control-74 | 35 | 1 | 33 | 1 | +0.00004401 |
| Route-90 | 42 | 3 | 38 | 1 | +0.00015198 |

All four nonzero events were reconverging rather than persistent:

- `6bba_705ec2c9` control: -0.00116312 adjusted-edge delta
- `6bba_718b21f9` regression: +0.00242127 for each of two distinct rewrites
- `6bba_fbc898dc` control: +0.00270356

The zero-penalty rewrite rate was modestly higher among persistent windows
(46/84, 54.76%) than reconverging windows (250/547, 45.70%). That did not survive
the scoring boundary: only 5 persistent rewrites were scoreable and all 5 were
neutral, while every nonzero result came from reconverging windows.

## Compatibility Boundary

Across the primary and zero-penalty arms, 612 proposal evaluations were explicitly
inapplicable after V24.3 pruning:

| Reason | Count |
|---|---:|
| Added endpoint absent | 434 |
| Removed edge absent | 86 |
| Added edge already present | 73 |
| Multiple continuation parents | 18 |
| Multiple continuation children | 1 |

These proposals remain mechanism telemetry from the relink graph. They were not
altered, scored, used to restore pruned nodes, or included in efficacy deltas.
The high attrition shows that running the trigger and ILP before pruning is poorly
aligned with the V24.3 scoring graph.

## Decision

The preregistered combined hypothesis is unsupported on route-90:

1. Persistent commitment effects did not identify the nonzero official-metric
   rewrites; all nonzero diagnostic outcomes were reconverging.
2. The contained primary had no positive scoreable rewrite.
3. Most ownership alternatives were incompatible with the pruned V24.3 graph.
4. The zero-penalty diagnostic included a control regression and cannot justify
   lowering the containment penalty.

Keep V24.7 shadow-only and keep the V24.3 baseline unchanged. Do not build a
selector from this opened-label cohort. A future independent experiment would
need to run commitment and ILP on the post-pruning graph, with a separately frozen
contract, rather than adapting this result retrospectively.