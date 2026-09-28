# V27C: official evaluation of frozen V27B graphs

Status: **VALID_RETROSPECTIVE_EVALUATION_RESULT — 16/16 samples, 480 evaluations**.

Danny approved the exact V27C candidate for freezing and execution. The unchanged
runner completed two full passes over all five arms and RAW/P2/P3 stages with
exit code 0. Per-cell and full-pass scientific digests agree exactly. Historical
H/P3 and S1/P3 metric anchors passed, and final source/input/runtime checks passed.
No retry or scientific change was made during execution.

This is retrospective evaluation of the same 16 opened samples, not independent
validation or a leaderboard submission. It quantifies official credit and
evaluable errors under the pinned host; sparse labels do not establish exhaustive
biological truth. V26A remains **NO_GO** and V24.8's independent-data block remains.

## Adjusted edge Jaccard across all saved graph stages

These are the official host's cohort summaries, with its denominator weighting.
They are not means of sample deltas. H is the historical reference; M0/M1 use
motion ranking, S0/S1 physical-step ranking. The 0 arms select before gating;
the 1 arms filter first. All arms have their own recursive history.

| Arm | RAW | P2 | P3 |
|---|---:|---:|---:|
| H | 0.70936980 | 0.75682333 | 0.77931465 |
| M0 | 0.70976047 | 0.75756853 | 0.77917748 |
| M1 | 0.71047145 | 0.75841161 | 0.78003746 |
| S0 | 0.71737964 | 0.76155162 | 0.78258067 |
| S1 | 0.71740136 | 0.76156639 | 0.78258659 |

Every arm/stage has division TP=0, FP=0, FN=4 in the cohort. Thus the aggregate
division Jaccard is zero and the combined score equals adjusted edge Jaccard.
Fourteen samples have an undefined individual division Jaccard because their
division denominator is zero; those nulls are preserved. No primary metric or
sample was omitted.

## Final-stage credit and error totals

| Arm, P3 | Official edge TP | Official edge FP | Edge FN | Adjusted J delta vs H |
|---|---:|---:|---:|---:|
| H | 9,937 | 1,308 | 1,403 | 0 |
| M0 | 9,943 | 1,318 | 1,397 | -0.00013717 |
| M1 | 9,956 | 1,319 | 1,384 | +0.00072281 |
| S0 | 10,008 | 1,337 | 1,332 | +0.00326602 |
| S1 | 10,009 | 1,338 | 1,331 | +0.00327194 |

Higher cohort adjusted Jaccard coexists with more official FP and individual
sample losses. These observations do not select a winner or reopen V26A's
historical decision. The original V26A gate is not recalculated here.

No input edge was filtered by the host in any evaluated cell. At P3, the counts
outside sparse-GT evaluability are 73,861 / 73,835 / 74,063 / 74,638 / 74,666 for
H/M0/M1/S0/S1 respectively. They are preserved separately from official FP;
neither an unmatched label nor its absence establishes biological correctness.

## Order and ranking comparisons after P3

Each row compares the named policies with their induced recursive histories.
Gains/losses are sets of GT edge identities, not counts of prediction edges
added/removed. Newly penalized/relieved FP includes changed evaluability on
surviving prediction edges as well as physical additions/deletions.

| Before -> after | Gained / lost GT credits | Newly penalized / relieved FP | Adjusted J delta | Sample delta min / max |
|---|---:|---:|---:|---:|
| H -> M0 | 29 / 23 | 34 / 24 | -0.00013717 | -0.00774328 / +0.00996456 |
| M0 -> M1 | 13 / 0 | 1 / 0 | +0.00085998 | -0.00087216 / +0.00341769 |
| S0 -> S1 | 1 / 0 | 1 / 0 | +0.00000591 | -0.00080639 / +0.00137881 |
| M0 -> S0 | 168 / 103 | 149 / 130 | +0.00340319 | -0.01869032 / +0.01841772 |
| M1 -> S1 | 156 / 103 | 148 / 129 | +0.00254912 | -0.02090546 / +0.01845280 |

The motion-order comparison makes V27B's count limitation concrete: its **+242
P3 prediction edges** correspond to **13 new GT credits and one additional
official FP**. Of 247 added prediction edges, 233 are outside sparse-GT
evaluability; the five removed prediction edges are also outside it. Their
absence from the official FP count does not prove correctness, and their nodes
can still affect the adjustment.

For this M0 -> M1 contrast, eight samples have positive adjusted-J deltas, five
negative and three zero. The minimum is -0.00087216 on `6bba_2646afc7`; the maximum
is +0.00341769 on `6bba_ed9377fd`. No GT credits are lost, but extra FP and node
counts still permit per-sample metric losses. The RAW comparison has 11 gained
credits, zero lost, two additional FP and adjusted-J delta +0.00071098.

Step-order sensitivity is smaller on this cohort: S0 -> S1 has only one gained
GT credit and one additional FP after P3, despite a net 30 extra prediction
edges. Its adjusted-J delta is positive in one sample, negative in seven and
zero in eight. Aggregate arithmetic must not erase that distribution.

For the baseline contrasts, H -> M1 gains 42 and loses 23 GT credits; 35 edges
become FP and 24 cease to be FP. Ten samples improve and six decline. H -> S1
gains 179 and loses 107 GT credits, with 163 newly penalized and 133 relieved FP:
net **+72 TP and +30 FP**. Nine samples improve and seven decline; its adjusted-J
range is -0.01070395 (`6bba_2646afc7`) to +0.01841232 (`6bba_718b21f9`).

The descriptive adjusted-J interaction `(S1-S0)-(M1-M0)` is -0.00068927 in RAW,
-0.00082830 in P2 and -0.00085407 in P3. These nonlinear metric differences are
not additive biological causal effects or independent statistical trials.

## Pruning changes official matching as well as node counts

For H, RAW -> P2 removes **3,726 isolated nodes and zero edges**, yet gains **358
GT credits** and reduces net official FP by 301. The ledger records 418 surviving
edges with changed mapped endpoints and 412 with changed categories. Adjusted
Jaccard increases by 0.04745353 while mean node recall decreases by 0.00169934.

H's P2 -> P3 removes **1,672 prediction edges and 3,344 nodes**. Fresh matching
gains 153 GT credits and loses 33, for net +120 TP; net FP decreases by 169.
Adjusted Jaccard increases by 0.02249132, while mean node recall decreases by
0.00413251. Both pruning transitions have positive adjusted-J deltas in all 16
samples, but this does not erase their node-recall losses or the 33 lost GT
credits in the second transition.

No pruning stage creates prediction edges. These credit changes arise in an
evaluation where surviving graphs are matched afresh, and the adjusted metric
also responds to predicted node counts. V27C documents their joint effect; it
does not isolate independent causal contributions from deletion, rematching
and the node adjustment. Historical correspondence membership cannot replace
fresh stage-specific evaluation.

## Integrity and recorded artifacts

- 240 distinct input graphs evaluated twice, with all 480 evaluations complete.
- Exact scientific agreement for metrics, node correspondence, edge categories,
  all paired/pruning ledgers, sample summaries and cohort summaries.
- 32 historical per-sample metric anchors and two historical cohort summaries
  checked in each pass; no integer/null mismatch or out-of-tolerance float.
- Initial and final verification of 112 canonical sources, 854 input files,
  the two pinned host packages and their source files, the runtime and the
  passing 193-test evidence.
- No changed contract, implementation, parameter, matching threshold or input;
  no scientific retry, inference, training, relinking or pruning execution.

A separate read-only artifact verification passed after execution: all 1,767
inventory entries matched size/hash, all 881 corresponding pass files were
byte-identical, and all 240 unique cell records and 624 unique paired/pruning
ledgers were parsed and reconciled. Input graph attributes, credit sets,
prediction-edge unions, category transitions and pruning subset invariants were
checked; metric totals and contrast counts were independently resummed from
saved sample records. This remains builder verification, not independent
scientific review. The verifier performed no new matching or scoring.

The frozen run directory contains **1,768 files, 302,249,558 bytes**, including
its inventory. The inventory excludes only itself. Evaluation-call wall times
sum to **1,244.67 seconds (20.74 minutes)** across 480 calls. Maximum recorded
Python-traced allocation is **136,746,058 bytes**. These are evaluation-call
measurements after graph loading, not total workflow duration or process RSS.

Raw directory: `outputs/v27c_frozen_20260927/`.

The runner's `RESULTS.md` contains all cohort and contrast tables. Full precision,
individual sample records, null reasons, denominators and original warnings
remain in the machine evidence and compressed cell/ledger files.

[Machine-readable result and full inventory](v27c_official_graph_evaluation_results.json).
The record includes the runner result, approved freeze identity, telemetry,
execution logs and post-run verification. Full raw files remain local and are
required for artifact-level reproduction.

Machine-result SHA-256:
`35afa4ba8b3f5ebf9d0357491fa7e4c5924cc09433976845afbc9e61645447b8`

## Approval and provenance

Approved manifest: [V27C approved freeze](v27c_freeze_approved_20260927.json).

Approved manifest SHA-256:
`56d5dc360fafb7e9ff210e9ba9d231369a9b1d888f8219e7d7b83d4e50706c94`

Reviewed payload SHA-256:
`0b11827689b07034f3db3afa7142dbc60d8be9ead6cbfcf1e57af634c5e83af9`

The candidate remains preserved separately. The approved record identifies
Codex as builder, Danny as reviewer and authority, and records Danny's explicit
approval. Earlier proposal and implementation-review documents remain historical
records of their respective stages.

Executed command (the output directory now exists and must not be reused):

```powershell
.\.venv\Scripts\python.exe scripts/run_v27c_official_graph_evaluation.py run `
  --freeze v27c_freeze_approved_20260927.json `
  --approved-freeze-sha256 56d5dc360fafb7e9ff210e9ba9d231369a9b1d888f8219e7d7b83d4e50706c94 `
  --output-dir outputs/v27c_frozen_20260927
```

V27C completes the planned diagnostic evaluation. Any follow-up requires its
own question, data-eligibility boundary and reviewed contract. These results
authorize neither automatic arm selection nor production promotion/submission.
