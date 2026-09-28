# V28 offline GPU validation: passed

Completed 2026-09-28 UTC. Builder: Codex. Danny approved freezing and executing
the reviewed validation-only package with a 7,200-second cap. This report is
builder verification of that execution, not independent review or submission
approval. No competition submission, final-selection change, commit or Git push
was performed in this step.

The [Kaggle validation notebook](https://www.kaggle.com/code/drakus74/atabey-v28-validation)
completed as **version 1**, kernel ID **136190696**. Its cell sources match the
approved dispatch. All 24 checked frozen artifacts still match their raw bytes;
the unrelated V25 notebook remains unchanged.

## Results

| Check | Observed result |
|---|---|
| Offline installation and model load | Passed on Python 3.12.13, Torch 2.10.0+cu128, CUDA 12.8, Tesla T4 |
| Image-only pruning decisions | 199/199 match the frozen route references |
| Fresh inference and final graph signatures | 7/7 exact historical matches |
| Repeated inference | First sample's final graph signature matches exactly |
| Visible test coverage | All 4 discovered samples, 100 frames each |
| CSV | 311,183 rows, 15,911,178 bytes; downloaded file revalidated locally |
| Coordinate rounding | 0 rounded nodes across the 11 recorded parity/test graphs |
| Setup plus validation wall time | 533.013 seconds / 8 min 53 sec |
| Initialization | 48.174 seconds |
| Conservative runtime projection | 18,090.061 seconds / 5 h 1 min 30 sec; passes 10-hour gate |
| GPU quota delta | 552.567 seconds / 9 min 13 sec |
| Remaining quota at check | 44.8465 hours / approximately 44 h 51 min |
| Peak process RSS | 1.80 GiB |
| Maximum recorded Torch GPU allocation / reservation | 429.58 MiB / 532 MiB |

Fresh parity covered the original three samples `44b6_5f15d135`,
`44b6_74d0c52e`, `6bba_3c5691b6`, and all four historical catastrophic cases:
`6bba_2646afc7`, `6bba_2540cd90`, `6bba_76db78c1`, `6bba_d5eae175`.
The local verifier also compared their identities and expected signatures to
the references inside the frozen source bundle, rather than trusting only the
remote success flags. Route, inference and repeat files agree with the summary.

CSV validation checks the exact header, global IDs, dataset coverage, node IDs,
coordinate bounds, placeholders, edge endpoints, adjacent times, duplicate edges
and the intended exported-row digests. The downloaded CSV hash is:

`f9ed84aa3c55de186c7b750861d3e869d028107540e16d5e8ca1e77e01106924`

The artifact is named `validation_submission.csv`. It has not been submitted.

## Interpretation and remaining limits

This establishes offline delivery and implementation parity for the measured
cases. It does not establish new tracking quality or independent generalization.
No ground-truth scoring, parameter selection or retraining occurred. Exact
reproduction of the four catastrophic cases preserves their historical failures;
it does not repair them. All 16 historical regressions remain disclosed in the
[readiness contract](V28A_SUBMISSION_READINESS_CONTRACT.md).

The time projection uses the worst measured complete per-voxel-frame cost across
11 cases, twice the observed 199-sample voxel-frame workload, scaled CSV checking,
initialization and a 600-second reserve. It assumes hidden workload is no larger
than those 199 samples. Hidden shapes, density, filesystem behavior and hardware
can differ; hidden runtime is still unverified. The projection was recomputed
locally and equals the saved remote result exactly.

Telemetry records Linux architecture/platform, GPU device 0 identity, package
versions, memory and stage times. The exact CPU model and total allocated GPU
device count were not captured. Requested shape was `NvidiaTeslaT4`; the quota
delta above is the observed account change, not a claim about device count.
These telemetry gaps remain explicit for submission review.

The executed Kaggle image was:

`gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`

## Evidence and exact identities

- [Approved validation freeze](v28_validation_freeze_approved_20260928.json).
- [Machine-readable result and evidence hashes](v28_validation_results_20260928.json).
- Raw downloaded evidence: `outputs/v28_validation_20260928/downloaded/`.
- Local verification receipt: `outputs/v28_validation_20260928/post_run_verification.json`.
- Read-only verifier: `outputs/verify_v28_validation_20260928.py`.
- Raw quota snapshots: `outputs/v28_validation_20260928/quota_before_raw.json`
  and `quota_after_raw.json`.

Frozen package-manifest SHA-256:
`fb7fde61dd8a1499cc68530cd0a0e3bc8293a803acfaf86edd2f4c67b5e097c3`.

Approved validation notebook SHA-256:
`81193365855b7a05073a2d70fd15ef7ea75a82641b0191d2a42856f94cde785b`.

## Proposed next action: one exact submission

The [submission candidate](v28_submission_candidate_20260928.json) is
**PROPOSED_NOT_APPROVED**. Its payload SHA-256 is:

`217541a10e28652eda5ccc79c81683c7f9684ae28449a0559c9d7efb0e35e87d`

The prepared folder is `outputs/v28_submission_review_20260928/`. The submission
notebook is byte-identical to the reviewed template; its receipt remains
`NOT_APPROVED`. Its separate metadata requests the tested image explicitly with
`docker_image_pinning_type=original`, T4 and internet disabled. Dataset versions,
checkpoint, source bundle and scientific policy are unchanged. The explicit
image request is prepared but has not yet been exercised by a submission push;
check the returned image before the competition submission.

Requested authority is one notebook version, verification of its visible output,
then one competition submission of that exact version and `submission.csv`.
Each execution has an 11-hour cap, including setup; a two-GPU charge at both full
caps could consume up to roughly 44 quota hours. The measured visible run is much
shorter, but the upper bound is disclosed against the 44.8465 hours remaining.
Recheck quota and competition rules immediately before dispatch. Preserve V19
submission `54622713` as backup. Final-selection changes remain a separate step;
the backup's exact submitted version and selection flag still need verification.

The readiness contract requires **"Danny's explicit exact-package approval"**
for final submission. After that approval, record a new submission-specific
receipt and dispatch hashes; do not reuse the validation receipt. No automatic
retry, changed policy, leaderboard tuning or new experiment is proposed.
