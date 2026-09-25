# V26A lessons learned: operation order is part of the intervention

Date: 2026-09-24

V26A remains a completed NO-GO. This note records a methodological lesson from
the subsequent [gate-order audit](../V26A_GATE_ORDER_AUDIT_RESULTS.md); it does
not replace the historical preregistration, measurements or decision.

## Evidence

V26A was described as changing only forward ranking, with candidate gates held
fixed. Code inspection and archived-data replay showed a second distinction:
the baseline selects its global motion-nearest target before applying the two
9 um gates, while V26A filters all targets first and then ranks by physical step.
Keeping the threshold values does not keep that decision procedure constant.

On 99,167 frozen-history source decisions, 229 had a rejected first choice and
a feasible alternative; local V26A accepted an alternative for 200. Eight of
the 108 historical forward-bucket recoveries overlap exposed sources. This
intersection does not identify a causal fraction of recursive recoveries or
of the +791 unmatched-edge ledger delta.

The audit reproduced 48 archived graph signatures and 86,778 baseline links.
Two complete executions produced byte-identical evidence. This establishes
the discrepancy without erasing the successful replay, failed interest gate,
or remaining uncertainty in the original work.

## Lessons to carry into V27

1. Specify the executed decision procedure, including operation order. A list
   of unchanged parameters is not an adequate intervention definition.
2. Establish an exact historical reference, then compare explicit controls.
   Do not silently normalize the baseline to match the intended description.
3. Separate order and ranking with a complete two-by-two design. Two simultaneous
   changes cannot be attributed to one factor from an endpoint delta alone.
4. Treat tie policy and numerical behavior as explicit parts of the algorithm.
   Determinism does not imply equivalence between two deterministic choices.
5. Hold histories fixed to measure local decision effects. A changed link can
   otherwise change later predictions, feasible targets and pruning eligibility.
6. Separate local decisions, recursively propagated graph changes and official
   rematching. An archived recovery overlap is not a new official TP or proof
   of biological identity.
7. Make success mean an interpretable measurement, including a null result.
   Do not select a new production tracker from already opened evidence.
8. Preserve failures and supersede claims additively. Keep Builder, Reviewer
   and human Authority distinct; a completed audit does not approve a new run.

## Concrete response

[V27's proposed preregistration](../V27_ASSOCIATION_CAUSAL_DECOMPOSITION_PREREGISTRATION.md)
turns these lessons into named arms, paired contrasts, exact replay checks and
explicit limits. Its current status is a proposal, not a frozen or executed
experiment. The first phase addresses local algorithmic effects on the same
opened cohort. Recursive propagation needs a separate prospective phase contract;
promotion still requires genuinely independent evidence.
