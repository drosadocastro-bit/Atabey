# V22 Continuation-Reference Availability Audit Results

Decision: **GO TO FOLD-SAFE CONTINUATION TABLE BUILD**

This audit measures the availability and concentration of weak V19 continuation
references. It does not train a continuation model, label biological truth, run
assignment, or mutate a graph.

## Integrity

- Samples completed: **27/27**.
- Unique references: **182,996**.
- Duplicate reference IDs: **0**.
- References marked as ground truth: **0**.
- Shard hash failures: **0**.
- Source graph mutations: **0**.
- Semantic scoring or assignment: **disabled**.
- Full 199-sample scope: **not authorized**.

All preregistered decision gates passed.

## Funnel

| Stage | Count |
|---|---:|
| V19 graph edges | 432,718 |
| Consecutive continuation edges with exclusive central ownership | 317,102 |
| Exclusive three-frame chains inside 14 um | 214,845 |
| Strict route-neutral motion-mutual chains | 207,993 |
| Excluded near registered divisions | 24,997 |
| Eligible references | 182,996 |

Only 6,852 otherwise eligible three-frame chains failed the independently
recomputed strict motion-mutual test. The division exclusion removed 24,997
chains after mutual-nearest validation, preventing division-adjacent dynamics
from teaching the continuation head.

## Fold Breakdown

| Fold | Samples | References | Share | With alternatives | Alternative rate |
|---:|---:|---:|---:|---:|---:|
| 1 | 9 | 49,111 | 26.8% | 43,575 | 88.7% |
| 2 | 9 | 77,434 | 42.3% | 71,687 | 92.6% |
| 3 | 9 | 56,451 | 30.8% | 48,877 | 86.6% |

Every sample in every fold contributes references. Fold 2 remains the largest,
but it no longer contains 71.7% of the population as it did in the division
action table. Fold blocking alone is still insufficient; training must equalize
sample and frame contributions inside each training fold.

## Family Breakdown

| Family | Samples | References | Share | With alternatives | Alternative rate |
|---|---:|---:|---:|---:|---:|
| `44b6` | 5 | 66,510 | 36.3% | 65,801 | 98.9% |
| `6bba` | 22 | 116,486 | 63.7% | 98,338 | 84.4% |

`44b6` is only 5/27 samples but contributes more than one third of all
references and has almost universal local alternatives. Family must remain an
explicit evaluation stratum and cannot be allowed to receive raw-count weight.

## Route Breakdown

| Route | Samples | References | Share | With alternatives | Alternative rate |
|---|---:|---:|---:|---:|---:|
| `cfar_sidelobe/bipartite` | 7 | 83,872 | 45.8% | 82,942 | 98.9% |
| `components/greedy` | 19 | 82,247 | 44.9% | 64,400 | 78.3% |
| `local_maxima/motion_mutual` | 1 | 16,877 | 9.2% | 16,797 | 99.5% |

CFAR and components provide comparable total reference counts through very
different sample counts and alternative densities. The local-maxima route has
ample rows but only one contributing sample, `44b6_5f15d135`, in fold 3.
Quantity does not provide route-level generalization evidence.

### Fold x route

| Fold | Route | Samples | References | Alternative rate |
|---:|---|---:|---:|---:|
| 1 | CFAR/bipartite | 3 | 24,201 | 98.2% |
| 1 | components/greedy | 6 | 24,910 | 79.5% |
| 2 | CFAR/bipartite | 3 | 55,422 | 99.3% |
| 2 | components/greedy | 6 | 22,012 | 75.7% |
| 3 | CFAR/bipartite | 1 | 4,249 | 97.7% |
| 3 | components/greedy | 7 | 35,325 | 79.1% |
| 3 | local-maxima/motion-mutual | 1 | 16,877 | 99.5% |

When fold 3 is held out, the two training folds contain no local-maxima sample.
That held-out result is therefore a route-transfer test. A route-specific model
or route-specific calibration is prohibited by this evidence.

More precisely, folds 1 and 2 contain no held-out local-maxima observation, so
the route is untested in 2 of 3 held-out rounds. The only round that evaluates
local-maxima holds out fold 3, where the route was absent from training; that
measurement is zero-shot-only. Every metric touching this route must be shown
separately with the caveat **unproven generalization**, even when a pooled
route-neutral metric is also reported.

### Full-cohort route prevalence

A read-only census using the exact frozen five-timepoint route selector found:

| Route | Samples | Full-cohort share |
|---|---:|---:|
| `components/greedy` | 108 | 54.3% |
| `cfar_sidelobe/bipartite` | 66 | 33.2% |
| `local_maxima/motion_mutual` | 25 | 12.6% |

Local-maxima is not a negligible route: it covers 25/199 training samples. It is
also family-skewed, covering 17/71 `44b6` samples (23.9%) but only 8/128 `6bba`
samples (6.25%). A dedicated remedy is therefore worth future study, but the
current one-sample development evidence is insufficient to build or validate
one now.

## Concentration

- Largest sample: `44b6_706092f0`, 27,567 references (**15.1%**).
- Top three samples: **33.1%** of references.
- Effective sample size from raw reference counts: **15.1 of 27**.
- Largest parent frame: 649 references (**0.355%**).
- Top three parent frames: **0.850%**.

The preregistered limits were 20% for one sample and 45% for the top three; both
pass. Temporal concentration is low, but sample concentration is still material.
Raw reference weighting would reduce the effective population from 27 samples
to approximately 15.

## Alternative Availability

- References with at least one local target alternative: **164,139/182,996
  (89.7%)**.
- References with at least one competing source: **164,005/182,996 (89.6%)**.

This is sufficient for pairwise continuation compatibility construction in every
fold. Alternatives remain weak competitors, not biological negatives.

## Decision And Next Contract

The audit is a **GO** for constructing the continuation feature/pair table only.
The next implementation must preserve these constraints:

1. use the existing sample-blocked folds;
2. train one pooled, route-neutral geometric continuation head;
3. weight equally by sample, then parent frame, then pair/reference;
4. keep family and route as reporting strata, not shortcuts to confidence;
5. represent missing or low-margin evidence as abstention;
6. report the fold-3 local-maxima sample as unseen-route transfer;
7. never call weak V19 references ground truth;
8. keep scoring, assignment, graph mutation, and the full 199 scope closed.

The continuation table must project reference and alternative actions into a
feature schema compatible with U-Net continuation actions. Detector-specific
confidence, volume, or appearance fields cannot be relied upon unless an
independent domain-compatibility audit validates them.