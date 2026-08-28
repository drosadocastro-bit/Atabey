# V24.5 Commitment Shadow: Local Two-Sample Smoke

## Status

Completed locally in shadow mode. This experiment does not change a production
graph, select between V19 and V24, alter a submission, or authorize a new gate.

## Question

Does removing one accepted predecessor from motion history cause a later
motion-mutual assignment change that persists over a bounded two-frame replay?

This is a counterfactual stability test. A persistent change is not evidence
that the original association was incorrect.

## Frozen Inputs

- checkpoint SHA-256:
  `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`
- predictor SHA-256:
  `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`
- detector threshold: `0.97`
- pooling kernel: `5.0 um`
- linker: motion-mutual, `9.0 um`
- device: CPU (`torch 2.9.1+cpu`)
- timepoints: first 12 only
- counterfactual horizon: 2 frames
- counterfactual cap: 64 ambiguity-ranked accepted edges per sample

Coordinates were generated once under the frozen predictor contract and cached
as `.npy` files. No older peak table was substituted.

## Samples

| Sample | Selection reason | Coordinates | Eligible | Tested | Persistent |
|---|---|---:|---:|---:|---:|
| `6bba_2646afc7` | largest full-199 association-loss regression | 835 | 648 | 64 | 1 |
| `6bba_3c5691b6` | only held-out regression; precision tradeoff | 747 | 534 | 64 | 0 |

CPU inference took 17.49 seconds and 15.62 seconds respectively. Shadow replay
took 1.23 seconds and 1.09 seconds.

## Persistent Case

The only commitment-sensitive probe was:

- source: `unet:6bba_2646afc7:n00000654`
- target: `unet:6bba_2646afc7:n00000723`
- source frame: 9
- edge distance: `3.6336 um`
- prediction error: `3.6336 um`
- forward margin: `0.0 um`
- reverse margin: `0.3468 um`
- changed assignments: 1
- reconverged by the bounded horizon: no

The zero forward margin identifies an exact distance tie. This is a plausible
local ambiguity signal, but the smoke does not establish which tied assignment
is more accurate.

Four other probes changed one assignment and then reconverged: one in
`6bba_2646afc7` and three in `6bba_3c5691b6`.

## Interpretation

The result does not support one shared persistent lock-in mechanism across both
representative regressions. It does identify one auditable tied assignment in
the catastrophic case. Because only 12 timepoints and the 64 most ambiguous
accepted edges were tested, absence of another persistent case is not evidence
of absence over the full sequence.

No threshold should be tuned from these two opened-label samples. A defensible
next experiment would inspect the tied edge geometrically, then preregister a
tie-handling shadow rule before applying it to a broader fixed cohort.

## Reproduction

```powershell
python scripts/run_v24_5_commitment_shadow.py `
  --train-dir train `
  --support-repo D:\Atabey-artifacts\e016_secondary_seed\support_repo `
  --weights v22_e016_clean_checkpoint\edge_predictor_best.pth `
  --sample-ids 6bba_2646afc7 6bba_3c5691b6 `
  --max-timepoints 12 `
  --unet-batch-size 1 `
  --device cpu `
  --horizon-frames 2 `
  --max-counterfactual-edges 64
```

Machine-readable results are in
`outputs/v24_5_commitment_shadow_local_2/summary.json`.