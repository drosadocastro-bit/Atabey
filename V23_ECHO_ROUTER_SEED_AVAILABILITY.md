# V23 Echo Router Seed Availability

Decision: **READ-ONLY PREREQUISITE AUDIT**.

Router seeds were generated only from the V19 graph: broken endpoints at t-1 and parents at t with at most one outgoing continuation. GT coordinates were used only after seed generation to score coverage.

| Event | Broken seeds / matching | Under-resolved seeds / matching | Router seed |
|---|---:|---:|---|
| 44b6_706092f0 t49 | 136 / 0 | 539 / 0 | False |
| 44b6_74d0c52e t58 | 96 / 1 | 210 / 1 | True |
| 44b6_aaf8b0ea t61 | 174 / 0 | 297 / 1 | True |
| 44b6_c50204e0 t28 | 224 / 4 | 561 / 1 | True |
| 44b6_c50204e0 t65 | 304 / 2 | 676 / 1 | True |
| 6bba_3abfe10a t81 | 160 / 0 | 509 / 0 | False |
| 6bba_57b7cc1e t12 | 387 / 2 | 731 / 2 | True |
| 6bba_57b7cc1e t23 | 374 / 3 | 724 / 0 | True |
| 6bba_57b7cc1e t77 | 374 / 0 | 716 / 0 | False |
| 6bba_fc5f39dc t24 | 35 / 0 | 92 / 2 | True |
| 6bba_fc5f39dc t54 | 62 / 2 | 179 / 1 | True |

Seed coverage: **8/11**. Zero perturbation: **True**.
