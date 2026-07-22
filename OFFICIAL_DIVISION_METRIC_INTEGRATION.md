# Official Patched Division Metric Integration

Date: 2026-07-22
Status: implemented and bounded-validation complete

## Provenance

Atabey now calls the competition host's patched `score_divisions` implementation directly.
No division-matching rules are reimplemented locally.

- Host repository: `royerlab/kaggle-cell-tracking-competition`
- Host commit: `075fc5f5a52d11077f9dc2b074644618f26939e2`
- Exploit-fix commit: `aa65e90aeb8a774ebb1b549e547787b87ac8a01c`
- `tracksdata` commit: `39dccf3a243e44274759468cb31b2ad9e7fc1d09`
- Match radius: `7 um`

The integration converts Atabey's in-memory detections and lineage edges to
`tracksdata.InMemoryGraph`, preserving timepoint and physical `(z, y, x)` coordinates,
then calls the untouched host scorer. The optional dependency commits are pinned in
`pyproject.toml`; they are evaluation-only and do not enter submission inference.

## Executed parity tests

The host's complete patched division suite ran under Python 3.12, the interpreter range
supported by `tracksdata`:

```text
39 passed
```

This includes the weak-component exploit regression, distinct predicted daughter branches,
cross-GT-component forks, shared/merged branches, unsupported sparse-region forks, duplicate
fork pairing, and mixed TP/FN/FP accounting.

Atabey's adapter tests independently confirm:

- a genuine directed parent-to-two-daughter fork is a TP;
- an unsupported fork in sparse space is ignored rather than automatically counted FP;
- a fork with a shared direct child is rejected as FP plus FN.

## Corrected bounded evidence

The fixed Phase 1 four plus Phase 2 ten evaluable cases were rebuilt and evaluated in exact
GT division windows. Full numeric evidence is in `OFFICIAL_DIVISION_RECALIBRATION.md` and its
two CSV files.

- V19: `TP=4`, `FP=6`, `FN=10`; evaluable precision `0.40`.
- V20: `TP=0`, `FP=0`, `FN=14`.
- V19 raw forks: `27,779`; official evaluable FP forks: `6`.
- Track B accepted forks: `8,507`.
- Track B official classification: `3 TP`, `2 FP`, `8,502` sparse-unsupported/ignored.

The six V19 FPs occur in two of 13 samples: two in `6bba_207c6aaf` and four in
`6bba_ebdf3b34`. The fixed-window FP distribution is therefore mean `0.462`, median `0`,
with 11/13 samples at zero. This is a bounded battery statistic, not a 199-sample estimate.

All three historically recovered Track B TPs remain genuine official TPs:

- `6bba_05db0fb1:t24:cf76`
- `6bba_b329af44:t82:cf38`
- `6bba_ebdf3b34:t84:cf39`

`6bba_32db13fc` contributes a fourth V19 official TP that was not one of the original three.

## Reinterpretation

The old evaluator's raw FP totals are invalid and must not be used. Sparse-unsupported forks
are not official false positives, but they are also not verified true negatives or biologically
valid divisions. They remain unknown outside annotated local evidence.

The three recovered-TP observations survive. The ownership and Hungarian diagnostics remain
real measurements on their fixed candidates, but any precision or population-level claim based
on the old FP denominator is withdrawn.

V20's topology and EdgeRecall findings are separate from this metric correction. For division
recovery, however, V20 is fully suppressive in this battery: it removes all four official V19 TPs
and leaves all 14 registered divisions as FN.

Joint voting and any new division mechanism remain blocked pending review of this corrected
evidence.
