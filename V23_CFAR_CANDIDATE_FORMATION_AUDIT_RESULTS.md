# V23 CFAR Candidate-Formation Audit

Decision: **READ-ONLY DIAGNOSTIC; NO CFAR GATE CHANGE**.

Population: `46` registered development cases. Candidate formation was evaluated from the frozen availability/detector artifacts; no detector rerun or graph mutation occurred.

## Loss Classification

| Formation outcome | Cases | Percent |
|---|---:|---:|
| official_tp_available | 40 | 87.0% |
| pair_formation_loss | 2 | 4.3% |
| formed_but_official_match_loss | 2 | 4.3% |
| parent_detection_loss | 1 | 2.2% |
| daughter_detection_loss | 1 | 2.2% |

## Route and Family

| Route / family | Cases | Formation outcomes | Median action count | Median mean frame density |
|---|---:|---|---:|---:|
| cfar_sidelobe/44b6 | 5 | pair_formation_loss=2, official_tp_available=2, parent_detection_loss=1 | 14033 | 516.0 |
| cfar_sidelobe/6bba | 6 | official_tp_available=5, daughter_detection_loss=1 | 21329 | 764.5 |
| components/6bba | 34 | official_tp_available=32, formed_but_official_match_loss=2 | 598 | 110.8 |
| local_maxima/44b6 | 1 | official_tp_available=1 | 11317 | 433.5 |

## Interpretation Guardrail

This audit separates missing role detections from pair/triplet formation and later official matching. Distances and density are descriptive covariates, not threshold-tuning evidence. Any follow-up gate change must be a bounded shadow experiment with CFAR retained as the control.
