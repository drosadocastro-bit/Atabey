# V23 Session Closure: Detector-Native Evidence

Status: **CLOSED -- NO-GO for the bounded pair-field image ranker**.

V23 tested whether detector-native and parent-centered image evidence could add reliable division-ranking signal beyond the explicit geometry already available in Atabey. The final preregistered experiment completed all three sample-blocked folds for all three frozen seeds. It did not pass the absolute-quality, generalization, or independent-image-evidence gates.

This is a useful negative result. It closes the current V23 learned pair-field path without changing CFAR, assignment, lineage graphs, or submission behavior.

## Final Experiment

The locked dataset contained:

- 29 patched-official-positive events;
- 2,264 candidate actions;
- 54 reusable parent fields;
- two cell families, kept visible in validation;
- three sample-blocked outer folds;
- three frozen seeds: `314159`, `271828`, and `161803`.

The fitted model was the preregistered 20,145-parameter five-channel 3D CNN. Its output was evaluated only as a within-event retrieval score. It was never treated as a calibrated division probability.

The downloaded Kaggle archive was complete: it contained the compact report and summary, 18 checkpoints, and 18 fold-result shards. Its local SHA-256 was:

```text
efeeef09c8a8db83933065c5939059a64b9a30c6576782c06f90d45738c8f2eb
```

The archive and model checkpoints remain local research artifacts and are intentionally excluded from Git.

## Preregistered Decision

Final decision: **`NO_GO_PAIR_FIELD_RANKER`**.

| Seed | Main Recall@10 | Main MRR | Main pairwise accuracy | Seed passes |
|---:|---:|---:|---:|---|
| 314159 | 0.206897 | 0.107656 | 0.420088 | No |
| 271828 | 0.344828 | 0.113220 | 0.452231 | No |
| 161803 | 0.241379 | 0.157510 | 0.518386 | No |

No seed passed. Every seed was below the catastrophic Recall@10 floor of 0.65, and none approached the preregistered pooled target of 0.80. The result is not borderline and does not justify threshold or architecture tuning on the same 29 events.

## Control Reality Check

For the median seed (`161803`):

| Ranking source | Recall@10 | Events recovered | MRR | Pairwise accuracy |
|---|---:|---:|---:|---:|
| Main image model | 0.241379 | 7/29 | 0.157510 | 0.518386 |
| Nearest distance | 0.862069 | 25/29 | 0.524786 | 0.866853 |
| Geometry only | 0.896552 | 26/29 | 0.598950 | 0.885955 |
| Mask only | 0.724138 | 21/29 | 0.298317 | 0.735623 |
| Image shuffled | 0.310345 | 9/29 | 0.126810 | 0.512436 |
| Static image | 0.241379 | 7/29 | 0.145022 | 0.482363 |

The central finding is stronger than a simple model-quality failure:

- explicit geometry recovered 26 of 29 events in the top 10;
- the image model recovered only 7 of 29 for the median seed;
- shuffled image fields recovered more events than correctly paired image fields;
- replacing `t+1` with `t` did not reduce Recall@10;
- mask-only input substantially outperformed the full image model, but still trailed explicit geometry.

The experiment therefore found no repeatable evidence that this local two-frame image representation adds independent ranking information. Image channels appear to interfere with a useful candidate-pair representation under the present sample size, architecture, and objective.

This must not be generalized into a claim that microscopy images contain no biological signal. It only falsifies the tested V23 mechanism under its locked development contract.

## Generalization Failure

The median-seed main model remained weak across every reporting slice:

| Slice | Events | Recall@10 | MRR | Pairwise accuracy |
|---|---:|---:|---:|---:|
| Fold 1 | 9 | 0.222222 | 0.118431 | 0.487871 |
| Fold 2 | 12 | 0.333333 | 0.179652 | 0.543363 |
| Fold 3 | 8 | 0.125000 | 0.168260 | 0.515250 |
| `44b6` | 9 | 0.111111 | 0.063740 | 0.440580 |
| `6bba` | 20 | 0.300000 | 0.199700 | 0.553400 |

The fold-1 shuffle coverage of 7/9 events also missed its 80% control requirement because of singleton `44b6` strata. That issue is documented but is not decision-determining: the model already failed multiple stronger absolute and comparative gates.

## What V23 Established

V23 produced several durable findings:

1. CFAR remains valuable as a detector and should not be removed on the basis of the encoder-decoder analogy.
2. Decoder evidence can be extracted at CFAR coordinates, but the tested decoder channels did not supply a reliable replacement or complement for CFAR.
3. Several division failures arise before semantic ranking, through candidate identity, parent/daughter availability, distinct-daughter retention, or ownership contention.
4. Range-gated echo and related radar-inspired shadows were useful diagnostics, but did not earn production integration.
5. Pair-field representation was available and computationally feasible, yet the learned image ranker failed against simpler geometry controls.
6. Negative controls prevented a misleading promotion: raw neural scores alone would not have revealed that shuffled and static imagery performed similarly.

## Three Remaining Geometry Misses

The strongest surviving baseline, geometry-only ranking, missed these official-positive events at Recall@10:

| Event | Fold | Best TP rank | Candidate actions |
|---|---:|---:|---:|
| `6bba_207c6aaf:t41:gt42000280` | 1 | 11 | 57 |
| `6bba_474be664:t63:gt64000351` | 2 | 11 | 66 |
| `6bba_ebdf3b34:t13:gt14000412` | 2 | 37 | 111 |

These are retained as a future diagnostic set. They do not authorize tuning on three cases. A future version may perform a preregistered, read-only overlap audit to determine whether they are formation, identity, or ownership failures.

## Closed

- The V23 bounded pair-field image ranker is closed as `NO_GO_PAIR_FIELD_RANKER`.
- Architecture search, seed search, threshold tuning, and feature tuning on the same 29 events are closed.
- V23 local assignment is not authorized because the ranker did not clear its prerequisite gate.
- A full-199 pair-field run is not authorized.
- Graph mutation, CFAR replacement, and submission integration remain disabled.
- The downloaded checkpoints are evidence artifacts, not promotable models.

## Preserved

- The existing production graph and CFAR routing are unchanged.
- Official-metric integration and zero-perturbation findings remain valid.
- The geometry-only control is preserved as bounded evidence, not as a new production decision rule.
- The three geometry misses are preserved for a separately preregistered future investigation.

## Next Version Boundary

Any continuation should begin under a new version and a new contract. The most defensible first question is whether the three geometry misses share an upstream candidate-formation, coordinate-identity, or ownership mechanism. Only after that read-only diagnosis should Atabey consider a geometry scorer with a local ownership constraint as a safety layer.

V23 itself is complete.
