# V26A gate-order descriptive audit

Date: 2026-09-24

Status: **COMPLETE; IMPLEMENTATION/DESCRIPTION DISCREPANCY CONFIRMED**.
The frozen V26A **NO-GO remains unchanged**.

## Finding

The V26A preregistration describes the baseline as ranking only targets that
satisfy both 9 um gates. The implemented baseline instead queries one globally
nearest motion-predicted target and then applies those gates. If that target
fails, it does not try another. V26A filters the targets first, then selects by
physical-step distance. Threshold values are unchanged, but operation order is
different. Consequently the experiment does not isolate ranking preference
from the handling of feasible alternatives after a failed first choice.

The read-only census found this difference in the real archived cohort:

| Baseline-history observation | Count |
| --- | ---: |
| Source decisions before the final frame | 99,167 |
| Sources with at least one feasible next-frame target | 94,661 |
| Original target fails a gate while another feasible target exists | **229** |
| Those sources where frame-local V26A accepts an alternative | **200** |
| Those sources still rejected by reverse mutuality | 29 |
| All differing baseline/V26A frame-local accepted-target decisions | 1,653 |
| Reproduced baseline relink edges | 86,778 |
| Frame-local V26A accepted edges, without propagating changed history | 87,484 |

All 229 original choices pass the prediction-error gate but fail the physical
step gate. They occur in 15 of 16 samples. The exposure rate is 0.231% of all
source decisions; 200 of the 1,653 local decision changes (12.10%) occur at those
exposed sources. These are local counts, not final V26A graph transitions.

## Intersection with archived losses and recoveries

The census independently reproduces the full 1,069-loss denominator and its
436 forward-ranking, 268 reverse-mutuality, 243 generation, 23 pruning and 99
adjustment-only classifications using the archived evidence and existing exact
replay subtype function.

Nine archived lost GT-edge identities have an exposed mapped source:

- eight in the 436 forward-ranking loss bucket;
- one in the 99 adjustment-only bucket.

For all nine, frame-local V26A selects a mapped target under the frozen V25
history, and the historical V26A ledger records a recovery. Thus **8 of the 108
historical forward-bucket recoveries overlap this operation-order exposure**.
This is an intersection, not a causal estimate. No new official matching was
performed, and neither these counts nor their complement isolate ranking-only
effects. Changed recursive history can affect other sources and later pruning.

In particular, this audit does not apportion the historical +791 unmatched-edge
delta, 107 displaced credited edges, or final score change between mechanisms.

## Concrete archived example

In `6bba_23af9eeb`, source `unet:6bba_23af9eeb:n00002141` at t=28:

| Choice | Prediction error (um) | Physical step (um) | Outcome |
| --- | ---: | ---: | --- |
| Global motion nearest: `n00002201` | 7.621926 | 10.900831 | Baseline rejects; step exceeds 9 |
| Only feasible alternative: `n00002210` | 8.285907 | 3.633610 | Local V26A accepts; reverse mutual |

There is only one feasible target and no minimum-distance tie. This is a direct
example of the baseline abstaining despite a feasible alternative. The mapped
GT edge `[29000214, 30000221]` is in the archived V26A recovery ledger.

## Per-sample census

"Recovered overlap" counts archived GT-edge identities; all other counts refer
to source decisions. "Local changes" includes every accepted-target difference,
not only gate-order exposure.

| Sample | Sources | Exposed | Alternative accepted | Local changes | Recovered overlap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 6bba_05b6850b | 7,636 | 20 | 18 | 98 | 0 |
| 6bba_23af9eeb | 5,050 | 11 | 10 | 128 | 1 |
| 6bba_2540cd90 | 3,680 | 0 | 0 | 37 | 0 |
| 6bba_2646afc7 | 6,290 | 14 | 7 | 86 | 0 |
| 6bba_372c8cb8 | 7,872 | 9 | 8 | 131 | 0 |
| 6bba_3c5691b6 | 8,156 | 20 | 17 | 202 | 3 |
| 6bba_5b28472a | 6,596 | 11 | 10 | 83 | 0 |
| 6bba_5f89039d | 4,815 | 3 | 3 | 54 | 1 |
| 6bba_718b21f9 | 4,180 | 2 | 2 | 31 | 0 |
| 6bba_76db78c1 | 6,523 | 5 | 5 | 109 | 0 |
| 6bba_96833384 | 6,057 | 16 | 13 | 124 | 1 |
| 6bba_b204cac7 | 6,538 | 10 | 9 | 68 | 1 |
| 6bba_d0fc38b5 | 7,453 | 15 | 13 | 195 | 0 |
| 6bba_d5eae175 | 4,382 | 4 | 4 | 32 | 0 |
| 6bba_ed9377fd | 4,678 | 3 | 2 | 65 | 0 |
| 6bba_fc516dc6 | 9,261 | 86 | 79 | 210 | 2 |
| **Total** | **99,167** | **229** | **200** | **1,653** | **9** |

There are also 592 exact motion-minimum ties and 384 feasible step-minimum ties
across the full census. These flags may overlap each other and the exposure
events. They are not additional disjoint causes or counts of changed links.
Baseline choices use SciPy cKDTree; V26A step ties use original target order.

## Integrity and reproducibility

- Both ZIPs match their frozen SHA-256/size identities; exact membership of all
  16 sample records and archive entry counts was checked.
- All existing V26A contract source hashes passed before reconstruction.
- All **48** frozen relink/V24.2/V24.3 signatures were reproduced, and each
  V24.3 signature matched the baseline in the historical V26A result archive.
- Every frame's analytical accepted-target decisions matched both existing
  linker implementations on the same baseline histories.
- The census reconstructed exactly all 86,778 baseline edge identities.
- Input graph signatures remained unchanged. Original ZIPs, source contracts,
  historical results and production modules were not edited.
- Runtime: Python 3.13.14, NumPy 2.4.6, SciPy 1.18.0. Exact baseline agreement
  is established by the archived signatures, rather than assumed from version
  names. This does not establish cross-version tie invariance.
- Two complete audit executions produced byte-identical JSON (238,564 bytes),
  SHA-256 `fc33a35293834bba4f710c52fbc967f52b17be15cd350b5bcafaad2847f1261f`.
  All 15 canonical source hashes were rechecked after execution.
- 29 targeted tests passed, including 10 new audit tests covering order exposure,
  reverse rejection, ordinary ranking changes, absent feasible alternatives,
  inclusive boundaries, ties, empty frames, recovery intersection without input
  mutation, inconsistent graph rejection and unverified archive rejection.

The machine result contains all 229 exposure events, all nine loss overlaps,
per-sample counts, graph signatures, archive identities and canonical source
hashes: [v26a_gate_order_audit_results.json](v26a_gate_order_audit_results.json).
Method and command: [audit protocol](V26A_GATE_ORDER_AUDIT_PROTOCOL.md).

## Consequence

Preserve V26A's measured outcomes and NO-GO. Read its intervention as physical-step
selection with pre-filtering of feasible candidates, rather than a clean
ranking-only comparison against the executed baseline. Any future causal
experiment must distinguish operation order, ranking, tie behavior and recursive
history explicitly in a separate frozen contract. This audit authorizes no such
experiment, tuning, submission or promotion and adds no independent validation.
