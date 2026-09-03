# V26A Forward Motion-Prediction Ranking Ablation Preregistration

Date: 2026-09-03

Status: **PREREGISTERED; NOT EXECUTED**.

V25 found that 436 of 704 selection losses were attributable to the forward
motion-prediction ranking decision under exact pinned SciPy `cKDTree` replay.
V26A asks whether replacing that one ranking decision recovers a meaningful
fraction of those associations without unbounded collateral associations.

V25 identified mechanism attribution. V26 tests intervention sensitivity. It
does not authorize production tuning.

## Single Intervention

For each source, enumerate the same targets that satisfy both frozen 9 micron
gates:

- motion-prediction error at most 9 microns; and
- physical source-to-target step distance at most 9 microns.

Frozen V24.3 ranks those feasible targets by motion-prediction error. V26A ranks
them by physical step distance, with original target order as the deterministic
tie-break. No blend, threshold, weight, fallback, or parameter sweep is allowed.

The following remain frozen:

- E016 detections and physical coordinates;
- both candidate-generation gates and their inclusive boundary;
- reverse raw-nearest mutuality from pinned SciPy `cKDTree`;
- greedy source/target uniqueness;
- prediction-error-derived edge confidence;
- V24.2 and V24.3 pruning;
- V19 routing and comparison evidence;
- official node/edge matching and metric logic.

The ablation is recursively applied, so a changed edge may change later motion
history. That downstream propagation is an observed intervention effect, not a
candidate-generation rule change. Recovery in the original forward-loss bucket
must therefore be reported separately from changes outside that bucket.

## Frozen Evidence

The cohort is exactly the 16 opened V24.3 regressions used by V25. V26A consumes
the validated V25 archive rather than rerunning E016 inference. Archived physical
coordinates must reproduce all 16 relink, V24.2, and V24.3 graph hashes before
the intervention runs. Ground truth is used only through the pinned official
evaluator.

Two container hashes are accepted: the retained browser/download bundle and the
Kaggle kernel-native ZIP. Both contain the same 27 paths. Decompressed comparison
of all 16 sample records found identical scientific fields; only the operational
`inference_runtime_seconds` field differs. The kernel run record and CUDA
telemetry files may also differ. No unpinned container is accepted.

These labels are opened and retrospective. Results are descriptive intervention
sensitivity evidence, not independent generalization evidence.

## Required Outputs

For every sample and in aggregate, record:

- recovered V19-credited edges absent from frozen V24.3;
- displaced V24.3-credited edges;
- newly credited edges;
- newly introduced and removed incorrect prediction edges;
- net credited-association and net incorrect-edge deltas;
- recovery in the original forward-ranking and reverse-mutuality strata;
- official metric deltas;
- changed prediction edges outside the original loss bucket;
- deterministic graph replay;
- relinking latency and peak Python-traced memory.

Mixed-mechanism sample behavior must remain visible. Aggregate improvement may
not erase catastrophic per-sample effects.

## Interest Gate

V26A is **interesting for further research**, not promotable, only if all fixed
conditions hold:

1. At least 44 of the 436 forward-ranking losses are recovered.
2. Net credited-association delta is positive.
3. Net incorrect-edge delta is nonpositive.
4. Newly incorrect edges are at most 0.25 per recovered forward-ranking loss.
5. No sample loses more than 0.10 adjusted edge Jaccard.
6. Every intervention replay is deterministic.

Failure of any condition is a NO-GO for this intervention. Passing authorizes
only a separately preregistered follow-up on genuinely independent evidence.

## Prohibitions

V26A authorizes no training, tuning, threshold search, score optimization,
selector, V19/V24 routing, production graph mutation, submission generation, or
deployment. V26B, V26C, and pruning changes remain out of scope.