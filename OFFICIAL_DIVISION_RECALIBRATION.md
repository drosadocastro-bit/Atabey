# Official Patched Division Recalibration

This audit calls the host repository's patched `score_divisions` directly after converting
Atabey graphs to `tracksdata.InMemoryGraph`. GT evaluation is restricted to the fixed
Phase 1/2 division windows (grandparent, divider, children, grandchildren). Track A/B
graphs and candidate decisions are not mutated.

## Aggregate fixed-window counts

- V19 official TP/FP/FN: **4/6/10**; precision `0.400000`.
- V20 official TP/FP/FN: **0/0/14**; precision `n/a`.
- V19 raw forks in the bounded graphs: **27779**; official evaluable FP forks: **6**.
- Track B accepted forks: **8507** = official TP **3**, official FP **2**, sparse-unsupported/ignored **8502**.

## Three formerly recovered TPs

Official TP confirmation: **3/3**.

| Case | GT parent | Track B parent | Accepted | Official GT recovered | Parent is official TP fork |
|---|---:|---|---:|---:|---:|
| P1-05DB | 25000381 | `6bba_05db0fb1:t24:cf76` | True | True | True |
| P1-B329 | 83001755 | `6bba_b329af44:t82:cf38` | True | True | True |
| P1-EBDF-LATE | 85001151 | `6bba_ebdf3b34:t84:cf39` | True | True | True |

## Fixed case breakdown

| Case | Phase | V19 recovered | V20 recovered |
|---|---:|---:|---:|
| P2-12DF | phase2 | False | False |
| P2-2A2E | phase2 | False | False |
| P2-587A | phase2 | False | False |
| P2-D754 | phase2 | False | False |
| P1-05DB | phase1 | True | False |
| P2-207C | phase2 | False | False |
| P2-32DB | phase2 | True | False |
| P2-4FFD | phase2 | False | False |
| P2-55B7 | phase2 | False | False |
| P2-705E | phase2 | False | False |
| P1-B329 | phase1 | True | False |
| P1-EBDF-EARLY | phase1 | False | False |
| P1-EBDF-LATE | phase1 | True | False |
| P2-F8FF | phase2 | False | False |

## Interpretation guardrail

Counts here are corrected official-metric evidence for the pre-registered windows, not a
199-sample population estimate. Joint voting and new division mechanisms remain blocked
until this report is reviewed.
