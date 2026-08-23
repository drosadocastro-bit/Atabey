# V23 CFAR Formation Shadow Preregistration

## Objective

Test a CFAR-native candidate-formation shadow that addresses three bounded failure mechanisms without changing the production detector, link graph, or official evaluator.

## Frozen Control

- CFAR detector and bipartite linker remain unchanged.
- Existing 14 um action-formation radius remains the candidate-control radius.
- Official 7 um matching is applied only after an action has been formed.
- No candidate, edge, or graph mutation is permitted in the shadow.

## Shadow Observations

For each registered development division, record separately:

1. Parent availability within 7 um and within 14 um.
2. Each daughter availability within 7 um and within 14 um.
3. Whether two distinct daughter IDs can form a pair around the candidate parent.
4. Whether a formed 14 um action subsequently matches the official 7 um fork.

The same detection must not satisfy both daughter roles in a distinct-pair result.

## Evaluation

Report by sample family and route:

- parent loss;
- daughter loss;
- distinct-pair formation loss;
- formed action rejected by official matching;
- official-positive action available.

The shadow is successful only if it recovers a previously unavailable official-positive action while preserving the frozen control's candidate identity, graph, and zero-perturbation status.

## Guardrails

The 14 um formation radius is not itself evidence that a division is real. Wider role availability is diagnostic only. Any future production proposal must be tested against the fixed adversarial battery and official metric, with normal tracking continuation measured separately.
