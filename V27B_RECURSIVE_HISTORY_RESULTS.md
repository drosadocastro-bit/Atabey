# V27B recursive history and pruning response: results

Status: **VALID_RECURSIVE_MECHANISM_RESULT — 16/16 samples completed**.

Danny reviewed and approved the exact V27B candidate for freezing and execution.
The approved run completed all 32 sample passes with exit code 0. Both passes
matched exactly for every sample. No scientific implementation, contract or
parameter was changed during execution, and no retry was performed.

The result establishes history-dependent changes in association identities and
algorithmic confidence, followed by different responses to unchanged pruning.
It does not establish improved tracking accuracy or official score. V26A remains
**NO_GO**; the original V27A attempt remains **INVALID_EXECUTION**.

## Cohort and comparison boundary

The same 16 previously opened samples contain **99,167 source decisions across
1,584 frame transitions**. F reproduces the V27A.1 frozen-history decisions.
R supplies each arm with predecessors from its own accepted previous-transition
edges. All detections, ordering, physical units, 9-micron gates, reverse ownership,
assignment and confidence definitions remain fixed as specified in the
[contract](V27B_RECURSIVE_HISTORY_PREREGISTRATION.md).

H is the historical motion/cKDTree reference. M0/M1 rank by motion error;
S0/S1 rank by physical step. The 0 arms select before gating and the 1 arms
prefilter before selecting. Controlled arms use original target indices for
exact forward ties. Only R graphs receive post-sequence V24.2 and V24.3 pruning.
F remains a local reference, with no alternative F graph assembled or pruned.

## Own history changes identities and confidence

Each row compares R with F for the **same arm**, before pruning.

| Arm | F accepted links | R accepted links | Net change | Changed accepted outcomes | Gain / loss / switch | Same-target confidence changes |
|---|---:|---:|---:|---:|---|---:|
| H | 86,778 | 86,778 | 0 | 0 | 0 / 0 / 0 | 0 |
| M0 | 86,763 | 86,768 | +5 | 23 | 11 / 6 / 6 | 179 |
| M1 | 86,965 | 86,965 | 0 | 28 | 10 / 10 / 8 | 287 |
| S0 | 87,450 | 87,464 | +14 | 56 | 35 / 21 / 0 | 1,523 |
| S1 | 87,484 | 87,489 | +5 | 56 | 29 / 24 / 3 | 1,507 |

An accepted outcome is the accepted target identity or abstention. A switch
changes one source outcome while removing one edge identity and adding another.
Rows can concern overlapping sources; their counts are not independent evidence.
Confidence-only changes are counted separately when the accepted target stays
the same. Confidence here is the algorithm's prediction-error-derived value,
not a calibrated biological probability.

M1 illustrates why a zero net count is insufficient: its 28 changed outcomes
include ten gains, ten losses and eight target replacements, despite identical
accepted-link totals. S0 never changes its pre-gate selected target, as required
by its history-independent physical-step ranking, yet 56 accepted outcomes
change through the history-dependent prediction gate. H reproduces F exactly.

Predecessor identity changes number 326, 510, 2,527 and 2,504 for M0, M1, S0 and
S1 respectively. Their predicted-position changes number 292, 425, 2,303 and
2,280. These are distinct recorded quantities: different predecessor IDs need
not imply different coordinates. Per-sample first-divergence witnesses remain
in the machine result and raw comparison streams.

## Paired policy effects under frozen and recursive history

| Contrast, before → after | F changed accepted outcomes | F net links | R changed accepted outcomes | R net links | R gains / losses / switches |
|---|---:|---:|---:|---:|---|
| Forward tie policy, H → M0 | 204 | -15 | 227 | -10 | 59 / 69 / 99 |
| Order with motion ranking, M0 → M1 | 202 | +202 | 211 | +197 | 203 / 6 / 2 |
| Order with step ranking, S0 → S1 | 34 | +34 | 39 | +25 | 32 / 7 / 0 |
| Ranking, select first, M0 → S0 | 1,608 | +687 | 1,651 | +696 | 786 / 90 / 775 |
| Ranking, filter first, M1 → S1 | 1,386 | +519 | 1,430 | +524 | 587 / 63 / 780 |

The F comparisons hold baseline history fixed. The R comparisons measure total
dynamic policy effects, including histories induced by the policy itself.
In particular, later R_H/R_M0 differences are not required to be current exact
ties when those arms have different histories. Tie validity is checked within
each common-history probe instead.

Prefiltering produces only accepted-link gains in the two F order contrasts.
Under recursive history, the motion-order contrast also has six losses and two
switches; the step-order contrast has seven losses. This is an observed
downstream history effect, not a changed gate implementation.

The aggregate binary acceptance interaction changes from
`I_F = 34 - 202 = -168` to `I_R = 25 - 197 = -172`.
The history difference is **-4**, with per-source differences -1 for 12 sources,
+1 for eight, and zero for 99,147. The R interaction itself is -1 for 207 sources,
+1 for 35 and zero for 98,925; no +/-2 values occurred. A small aggregate change
does not erase target replacements or confidence changes. These accounting
identities do not provide biological causal attribution or independent-trial
statistical inference.

## Unchanged pruning responds to different graphs

| Arm | RAW edges | P2 edges | P3 edges | P2 → P3 removed edges |
|---|---:|---:|---:|---:|
| H | 86,778 | 86,778 | 85,106 | 1,672 |
| M0 | 86,768 | 86,768 | 85,096 | 1,672 |
| M1 | 86,965 | 86,965 | 85,338 | 1,627 |
| S0 | 87,464 | 87,464 | 85,983 | 1,481 |
| S1 | 87,489 | 87,489 | 86,013 | 1,476 |

P2 removes isolated nodes and leaves edge counts unchanged. P3 removes bounded
short fragments. Every saved stage was checked as a subset of its predecessor,
with retained node attributes, edge confidence and relation unchanged.

| Paired contrast | RAW added / removed edges | RAW net | P3 added / removed edges | P3 net |
|---|---|---:|---|---:|
| H → M0 | 158 / 168 | -10 | 167 / 177 | -10 |
| M0 → M1 | 205 / 8 | +197 | 247 / 5 | +242 |
| S0 → S1 | 32 / 7 | +25 | 37 / 7 | +30 |
| M0 → S0 | 1,561 / 865 | +696 | 1,839 / 952 | +887 |
| M1 → S1 | 1,367 / 843 | +524 | 1,603 / 928 | +675 |

These are differences **between arms at the named stage**, not edges created by
pruning. Each individual graph only loses nodes/edges through pruning. The
between-arm net motion-order difference grows from +197 to +242, and the
step-order difference from +25 to +30, because survival differs across input
graphs. Complete raw-union edge and endpoint survival ledgers preserve this
distinction, including shared raw edges with different final survival.

## Execution integrity and preserved evidence

- All 16 reproduced F streams match their pinned V27A.1 compressed hashes and
  complete count dictionaries, including the 99,167-source reference census.
- R_H and its pruning stages reproduce **48 historical signatures**. R_S1
  matches the unchanged recursive V26A executable and its **16 archived P3
  signatures**. The run performs no new evaluation of those graphs against GT.
- All **16 pairs of scientific passes** agree exactly. There are **240 unique
  graph stages** and **480 physical graph copies** across the two passes.
- Each pass contains 7,920 common-history probes: five history owners across
  1,584 transitions. Preserved tie-mediated parent-criterion dispositions number
  20, 20, 20, 21 and 21 for H, M0, M1, S0 and S1 respectively. These overlapping
  probe occurrences are not 102 independent cases. No other blocking failure
  was admitted and no validity failure remains.
- Post-run verification checked all **103 frozen source identities**, **59
  frozen input artifacts**, runtime and passing 133-test evidence. The saved
  freeze copy is byte-identical to the approved manifest.
- A separate read-only artifact check verified **627 inventory entries** by
  size/hash, parsed the **240 first-pass graph stages**, checked raw detection
  identity, adjacency/uniqueness, accepted-edge counts and pruning subset and
  retained-attribute invariants. Aggregates were independently resummed from
  sample summaries. This is builder verification, not independent scientific
  review or fresh validation data.

The run contains **628 files including the inventory**, totaling
**1,463,368,202 bytes**. Scientific-pass runtime sums to approximately **153.6
minutes**. Maximum Python-tracked allocation was **82,545,068 bytes**; this
telemetry is not peak process RSS and is excluded from scientific replay hashes.

Raw directory: `outputs/v27b_frozen_20260924/`.

[Machine-readable results and artifact inventory](v27b_recursive_history_results.json)
include all per-sample results, divergence witnesses, telemetry and post-run
verification records. The raw streams retain the full contexts and original
criterion dispositions. Earlier contracts and implementation-review documents
remain preserved as historical records; this report records completed execution.

## Approval and provenance

Approved manifest:
[v27b_freeze_approved_20260924.json](v27b_freeze_approved_20260924.json)

Manifest SHA-256:
`6f7e35cb652f9d95f4de47f7c13bcde49bdfe04ed6a2b7504c5edb6e8fda7847`

Payload SHA-256:
`e41ae805c2c49f3044423d5cf24c561716293cde56b48f2bfb408fa4ab256b74`

Machine-result SHA-256:
`27a6c91a4f583e6dd7ef0732048c67945c08b42cba6f6c8118621d86ef86f9be`

Executed command, recorded for provenance (the directory now exists):

```powershell
.\.venv\Scripts\python.exe scripts/run_v27b_recursive_history.py run `
  --freeze v27b_freeze_approved_20260924.json `
  --approved-freeze-sha256 6f7e35cb652f9d95f4de47f7c13bcde49bdfe04ed6a2b7504c5edb6e8fda7847 `
  --output-dir outputs/v27b_frozen_20260924
```

## Interpretation boundary

V27B confirms that recursive history can change target identities and confidence
even when link counts remain equal, and that identical pruning code can alter
the observed between-policy differences. It provides a completed mechanism
decomposition on the opened cohort. No arm is selected by these counts.

Official rematching and scoring require their own contract, with stage-specific
graph and evaluator identities. There was no new model inference, training,
tuning, production promotion or submission. This result does not release the
independent-data block or change V26A's NO_GO decision.
