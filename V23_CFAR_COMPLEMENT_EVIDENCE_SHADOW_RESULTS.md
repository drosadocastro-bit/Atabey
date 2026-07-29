# V23 CFAR Complement Evidence Shadow

Decision: **DESCRIPTIVE ONLY; decoder-logit attachment pending**.

CFAR generated the fixed candidate set. Raw detector-native evidence was evaluated only as an annotation/ranking signal. No candidates were removed, no new candidates were added, and no graph was mutated.

Population: `218,024` CFAR actions, `11` events, `15` official TP actions, `138` official FP actions.

## Event-balanced AUC

| Feature | Pooled | 44b6 | 6bba |
|---|---:|---:|---:|
| `mean_detection_confidence` | 0.3189 | 0.2442 | 0.3488 |
| `mean_daughter_contrast` | 0.5690 | 0.6009 | 0.5563 |
| `mean_daughter_anisotropy` | 0.6293 | 0.7164 | 0.5944 |
| `daughter_mass_balance` | 0.6260 | 0.7763 | 0.5658 |

## Boundary

This is a complement test over the existing CFAR action set, not a U-Net detector replacement test. The current local artifacts do not contain decoder logits for the CFAR peak IDs, so the next implementation must export those logits at the unchanged CFAR coordinates before claiming encoder-decoder complement evidence.

CFAR remains active and quarantined as the detector control.
