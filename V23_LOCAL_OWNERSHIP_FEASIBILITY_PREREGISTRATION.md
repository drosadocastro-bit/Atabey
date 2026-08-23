# V23 Local Ownership Feasibility Shadow Preregistration

Status: frozen bounded shadow; no production integration

## Question

Can a local ownership constraint realize the desired fork in the four frozen identity/ownership cases without stranding a competing parent, while leaving already-complete forks and detector-unavailable cases untouched?

This is an oracle-labeled feasibility question. It does not test whether Atabey can select the biological pair without GT.

## Frozen Population

The source is `v23_single_child_ownership_failures.json`:

- three complete registered forks are protected no-op controls;
- one detector-only loss remains quarantined;
- four identity/ownership cases enter the shadow;
- a target lacking two distinct daughter detections remains unavailable in the denominator and cannot be converted into a scoring failure.

No sample, event, or route may be added after outcomes are opened.

## Counterfactual

For each target, the frozen V19 CFAR/bipartite graph is built unchanged. Sparse GT is then used to identify the nearest registered focal parent and nearest registered detections for both daughters.

If the pair is distinct, a copied graph is projected to the oracle fork by removing conflicting local ownership and wrong next-frame edges from the focal parent, then adding the two desired edges. The source graph is never changed.

Competing parents are only parents that currently own one of the reserved daughters. A local LSAP diagnostic compares how many competitors can receive a plausible continuation before and after the desired daughters are reserved. The continuation gate remains the existing 9 um diagnostic gate.

## Metrics

- eligible and unavailable events by family;
- competing parents matched before and after reservation;
- assignment-cost increase;
- target GT division score under the patched official metric before and after copied-graph projection;
- total official TP, FP, and FN deltas;
- source zero perturbation.

## Decision

`GO_TO_SEMANTIC_SCORER_RESEARCH_ONLY` requires:

1. all three complete forks remain protected controls;
2. at least two target cases are eligible;
3. every eligible case changes its target official score from 0 to 1;
4. no eligible case reduces the number of matched competing parents;
5. no eligible case reduces total official TP or increases official FP.

Any clean subset short of those requirements is `HOLD`; no clean recovery is `NO_GO`.

A GO authorizes only research on a GT-blind semantic scorer placed before the constraint layer. It does not authorize graph mutation, LSAP integration, routing changes, threshold tuning, or a full 199-sample run.
