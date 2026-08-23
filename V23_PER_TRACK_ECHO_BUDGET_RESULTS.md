# V23 Per-Track Echo Proposal Budget Results

Decision: **HOLD**.

Low-confidence echoes were assigned with candidate ownership 1, explicit abstention, and per-track budgets K=1/K=2. GT was used only after assignment to measure registered fork geometry. No graph or candidate set was mutated.

| Budget | Failure recovery | Controls available | Selected/frame median | p90 | max | Ownership unique |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 4/7 | 4/4 | 292.0 | 860.7 | 964 | True |
| 2 | 4/7 | 4/4 | 414.0 | 1314.1 | 1582 | True |

## Event Breakdown

| Event | Cohort | Primary | K=1 available / selected | K=2 available / selected |
|---|---|---|---:|---:|
| 44b6_706092f0 t49 | failure | False | False / 559 | False / 734 |
| 44b6_74d0c52e t58 | failure | False | True / 389 | True / 785 |
| 44b6_aaf8b0ea t61 | failure | False | True / 580 | True / 1015 |
| 44b6_c50204e0 t28 | control | True | True / 570 | True / 691 |
| 44b6_c50204e0 t65 | control | True | True / 799 | True / 1015 |
| 6bba_3abfe10a t81 | failure | False | False / 428 | False / 553 |
| 6bba_57b7cc1e t12 | control | True | True / 1272 | True / 2066 |
| 6bba_57b7cc1e t23 | failure | False | True / 1336 | True / 2099 |
| 6bba_57b7cc1e t77 | failure | False | False / 1310 | False / 2285 |
| 6bba_fc5f39dc t24 | failure | False | True / 121 | True / 183 |
| 6bba_fc5f39dc t54 | control | True | True / 226 | True / 302 |

Guardrail: this is a proposal-availability shadow only. It does not authorize candidate emission, edge creation, graph mutation, or full-cohort execution.
