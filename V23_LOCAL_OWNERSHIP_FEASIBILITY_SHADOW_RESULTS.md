# V23 Local Ownership Feasibility Shadow Results

Decision: **GO_TO_SEMANTIC_SCORER_RESEARCH_ONLY**.

This is an oracle-labeled feasibility test, not a selector. GT identifies the desired fork only after the frozen V19 graph is built. Assignment is evaluated solely as a local ownership safety constraint.

Protected complete forks: 3/3. Detector-only quarantines: 1. Mixed missing-detection targets remain explicit.

| Event | Family | Eligible | Competitors | Safe | Target official 0->1 | TP delta | FP delta | Shadow edits |
|---|---|---|---:|---|---|---:|---:|---|
| 44b6_74d0c52e t58 | 44b6 | False | None | None | NA | NA | NA | none |
| 44b6_7a302da0 t90 | 44b6 | True | 0 | True | 0->1 | 1 | 0 | -0/+2 |
| 6bba_207c6aaf t41 | 6bba | True | 1 | True | 0->1 | 1 | 0 | -1/+2 |
| 6bba_474be664 t63 | 6bba | True | 0 | True | 0->1 | 1 | -1 | -1/+1 |

A GO authorizes only development of a GT-blind semantic scorer that proposes the pair before this constraint layer. It does not authorize edge mutation, assignment integration, routing changes, or a full-cohort run.

Guardrail: all edits occurred only on copied graphs for official counterfactual scoring. Source graphs and candidate sets remained unchanged.
