# V23 Range-Gated Echo Shadow Results

Decision: **NO_GO_ROUTER_TOO_BROAD**.

The fixed `floor=0.35, k=0.80` echo profile was admitted only inside 14 um windows generated from V19 broken endpoints and under-resolved parents. GT was used only after routing to score registered fork geometry. No candidates or graphs were mutated.

| Event | Cohort | Primary geometry | Gated geometry | New parent + daughter echoes | ROI fraction parent / daughter |
|---|---|---|---|---:|---:|
| 44b6_706092f0 t49 | failure | False | False | 396 + 568 | 0.481 / 0.744 |
| 44b6_74d0c52e t58 | failure | False | True | 623 + 771 | 0.302 / 0.409 |
| 44b6_aaf8b0ea t61 | failure | False | True | 727 + 741 | 0.304 / 0.428 |
| 44b6_c50204e0 t28 | control | True | True | 366 + 397 | 0.554 / 0.670 |
| 44b6_c50204e0 t65 | control | True | True | 510 + 588 | 0.730 / 0.853 |
| 6bba_3abfe10a t81 | failure | False | False | 269 + 399 | 0.541 / 0.685 |
| 6bba_57b7cc1e t12 | control | True | True | 1541 + 1683 | 0.898 / 0.972 |
| 6bba_57b7cc1e t23 | failure | False | True | 1503 + 1781 | 0.910 / 0.977 |
| 6bba_57b7cc1e t77 | failure | False | False | 1884 + 2082 | 0.849 / 0.954 |
| 6bba_fc5f39dc t24 | failure | False | True | 105 + 138 | 0.167 / 0.294 |
| 6bba_fc5f39dc t54 | control | True | True | 213 + 198 | 0.269 / 0.434 |

Failure recovery: **4/7**.
Added echoes per event-frame: median **578.0**, p90 **1771.2**, max **2082**.
Echo-pool retention: median **0.936**, p90 **0.997**.
Estimated ROI volume: median **0.612**, p90 **0.950**.

Guardrail: this is availability evidence only. It does not authorize candidate emission, edge creation, or graph mutation.
