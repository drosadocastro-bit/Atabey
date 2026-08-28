# V24.6 Bounded ILP Shadow: Local Two-Sample Probe

## Status

Completed locally against cached frozen E016 coordinates. The optimizer is
shadow-only: it does not mutate a graph, select a production arm, alter a
submission, or authorize a threshold.

## Hypothesis

A joint three-frame assignment can expose a lower-kinematic-cost alternative
around a commitment-sensitive edge, while an explicit baseline-change penalty
contains intervention and defaults to abstention.

This tests optimization stability, not biological identity. A lower objective
does not establish that an alternative lineage is correct.

## Primary Contract

- trigger: persistent commitment edge when present
- negative-control trigger: minimum-margin evaluated edge otherwise
- window: source frame, intermediate frame, and one future frame
- maximum link distance: `9.0 um`
- baseline edge-change penalty: `2.0 um` per symmetric-difference edge
- minimum objective improvement: `0.5 um`
- maximum binary variables: 512
- solver time limit: 5 seconds
- ownership: at most one selected path per intermediate and future detection
- source assignment: exactly one path or explicit unmatched path per local source
- solver: `scipy.optimize.milp`

The zero-penalty run is a post-primary mechanism diagnostic. It is not an
eligible arm and must not be interpreted as a tuned setting.

## Primary Result

| Sample | Trigger | Sources | Intermediate | Future | Variables | Result | Gain |
|---|---|---:|---:|---:|---:|---|---:|
| `6bba_2646afc7` | persistent frame-9 tie | 3 | 4 | 3 | 17 | keep baseline | `0.0 um` |
| `6bba_3c5691b6` | minimum-margin control | 2 | 1 | 1 | 6 | keep baseline | `0.0 um` |

Both solves were optimal and far below the variable budget. Both input graph
signatures were unchanged.

The preregistered primary hypothesis is therefore null at the decision level:
the containment ILP recommends no intervention on either local window.

## Mechanism Diagnostic

With the baseline-change penalty set to zero, the held-out control remains
identical to baseline. The catastrophic sample exposes one alternative:

- baseline objective: `37.6024875421 um`
- alternative objective: `30.7063261741 um`
- unpenalized improvement: `6.8961613680 um`
- removed edge:
  `n00000654 -> n00000723`
- added edges:
  `n00000654 -> n00000722`,
  `n00000657 -> n00000723`, and
  `n00000723 -> n00000784`

The alternative has four edge changes under symmetric difference. The primary
containment charge is therefore `8.0 um`, larger than the unpenalized kinematic
gain by `1.1038386320 um`. This explains the primary abstention: the candidate
exists, but its local evidence is not strong enough to pay for its intervention
footprint under the fixed conservative contract.

## Interpretation

The probe supports the mechanism half of the hypothesis only on the
commitment-sensitive catastrophic sample: joint optimization can reveal an
alternative hidden by local motion-mutual decisions. It also shows that the
containment term behaves as intended by refusing that four-edge rewrite.

It does not show score recovery, because no graph was changed or officially
scored. It does not justify lowering the penalty near its implied crossover;
doing so from an opened-label sample would be threshold tuning. The held-out
precision-tradeoff sample supplies no corresponding ILP disagreement in this
window.

The defensible next step is a fixed-cohort shadow audit using this unchanged
primary contract, reporting disagreement rate, intervention size, solver
failures, and official counterfactual score only as retrospective evidence.

## Reproduction

```powershell
python scripts/run_v24_6_bounded_ilp_shadow.py
```

Machine-readable evidence is in
`outputs/v24_6_bounded_ilp_shadow_local_2/summary.json`.