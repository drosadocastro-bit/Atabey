# V24.3 Full-199 Score Validation Preregistration

Status: **authorized; implementation ready for two frozen shards**.

The authoritative full-27 artifact passed every preregistered gate and authorized
one bounded next step: full-199 score validation of the frozen V24.3 arm. This
stage does not authorize submission or production graph mutation.

## Population

The runner requires exactly 199 sample IDs with paired `.zarr` and `.geff`
inputs. It partitions sorted IDs deterministically by stride into two shards:

- shard 0: `sample_ids[0::2]` (100 samples)
- shard 1: `sample_ids[1::2]` (99 samples)

The split is operational only. Both shards use the same checkpoint, predictor,
thresholds, graph builders, V24.2 transform, V24.3 transform, and evaluator.
Each shard requires deterministic replay and emits resumable per-sample JSON.

Two shards are used because the observed 27-sample runtime projects beyond a
single Kaggle session for 199 samples. A shard may report only
`FULL_199_SCORE_VALIDATION_SHARD_COMPLETE`; the population result exists only
after strict merge validation reports `FULL_199_SCORE_VALIDATION_COMPLETE`.

## Evidence Boundary

The population contains:

- 172 samples used to fit the frozen checkpoint
- 27 held-out development samples not used for fitting or selection

The merged report must show these strata separately. Scores on the 172 training
samples are population context, not independent generalization evidence. The
held-out 27 remains the only preregistered independent generalization cohort.

## Frozen Guards

Execution must fail when any of these conditions is not met:

1. The full-27 authorization report hash and fields match the frozen contract.
2. The inherited runner and V24.2/V24.3/telemetry source hashes match.
3. Exactly 199 paired sample IDs are present.
4. The held-out 27 is an exact subset, leaving 172 checkpoint-training samples.
5. Shard count is exactly two and shard indexes are 0 and 1.
6. Each shard completes deterministic replay.
7. Merge inputs have disjoint IDs, identical provenance, and the same complete
   population-ID hash.

## Boundaries

- No training or threshold tuning.
- No hybridization or assignment changes.
- No production graph mutation.
- No submission generation or authorization.
- No independent-generalization claim from the pooled 199-sample score.
