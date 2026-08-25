# V23 CFAR Decoder Role-Level Evidence Audit

Decision: **READ-ONLY DIAGNOSTIC; NO RANKING OR INTEGRATION**.

Population: `311,688` fixed CFAR actions, `11` events, `30` registered 7 um geometric TP-proxy actions.

Positive-role nodes are participants in a registered geometric TP-proxy action. Controls are other nodes appearing in actions from the same event and role. This is not an official-metric evaluation and does not treat unsupported actions as negatives.

## Pooled Role Comparison

| Role | Feature | Positive median | Control median | AUC (positive higher) | n+ | n- |
|---|---|---:|---:|---:|---:|---:|
| parent | decoder_logit | 2.2925 | 1.7535 | 0.5901 | 11 | 6191 |
| parent | confidence | 0.1242 | 0.1121 | 0.6323 | 11 | 6191 |
| parent | embedding_norm | 2.4616 | 2.4360 | 0.5227 | 11 | 6191 |
| parent | embedding_mean | -0.0995 | -0.0819 | 0.3545 | 11 | 6191 |
| parent | embedding_std | 0.4236 | 0.4176 | 0.5187 | 11 | 6191 |
| daughter_1 | decoder_logit | 2.6538 | 1.5580 | 0.6022 | 12 | 5938 |
| daughter_1 | confidence | 0.1596 | 0.1137 | 0.7268 | 12 | 5938 |
| daughter_1 | embedding_norm | 2.4594 | 2.3313 | 0.4955 | 12 | 5938 |
| daughter_1 | embedding_mean | -0.0911 | -0.0782 | 0.4513 | 12 | 5938 |
| daughter_1 | embedding_std | 0.4254 | 0.4014 | 0.4925 | 12 | 5938 |
| daughter_2 | decoder_logit | 2.1858 | 1.5570 | 0.5835 | 9 | 5935 |
| daughter_2 | confidence | 0.1394 | 0.1125 | 0.7542 | 9 | 5935 |
| daughter_2 | embedding_norm | 2.2773 | 2.3235 | 0.4174 | 9 | 5935 |
| daughter_2 | embedding_mean | -0.0874 | -0.0781 | 0.4694 | 9 | 5935 |
| daughter_2 | embedding_std | 0.3930 | 0.4006 | 0.4149 | 9 | 5935 |

## Interpretation Guardrail

Pooled separation is descriptive only and may be dominated by a small number of events. A useful decoder signal would require consistent role-level separation across events, with no graph mutation. Failure at this stage closes the decoder as a ranking source rather than motivating threshold tuning.
