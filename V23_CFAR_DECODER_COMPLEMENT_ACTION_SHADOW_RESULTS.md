# V23 CFAR Decoder Complement Action Shadow

Decision: **DESCRIPTIVE COMPLEMENT EVIDENCE ONLY**.

Population: `311,688` fixed CFAR actions across `11` events; geometry-matched TP proxy actions: `30`.

| Feature | Event R@1 | Event R@5 | Event R@50 | MRR |
|---|---:|---:|---:|---:|
| `mean_decoder_logit` | 0.0000 | 0.0000 | 0.0000 | 0.0001 |
| `minimum_daughter_decoder_logit` | 0.0000 | 0.0000 | 0.0000 | 0.0002 |
| `daughter_decoder_logit_balance` | 0.0000 | 0.0000 | 0.0000 | 0.0003 |
| `mean_embedding_norm` | 0.0000 | 0.0000 | 0.0000 | 0.0002 |
| `minimum_daughter_embedding_norm` | 0.0000 | 0.0000 | 0.0000 | 0.0001 |
| `mean_embedding_mean` | 0.0000 | 0.0000 | 0.0000 | 0.0002 |
| `mean_detection_confidence` | 0.0000 | 0.0000 | 0.0000 | 0.0042 |

Unknown and unsupported actions were not used as negatives. The TP label is a registered 7 um geometric match proxy, not a replacement for the patched official metric.
CFAR generated every candidate; decoder evidence only annotated/ranked the fixed action set. No candidate was removed and no graph was mutated.
