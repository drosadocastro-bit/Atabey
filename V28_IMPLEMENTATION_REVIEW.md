# V28 implementation review: offline V24.3 delivery

Status: **IMPLEMENTED_LOCAL_CHECKS_PASS — READY_FOR_BOUNDED_GPU_VALIDATION_REVIEW**.

This implements the [V28A proposal](V28A_SUBMISSION_READINESS_CONTRACT.md).
Danny authorized implementation and reported **45 GPU hours available**. That is
user-reported capacity, not a fresh account-quota measurement. No Kaggle GPU job,
dataset upload, competition submission or final selection was performed here.
Builder: Codex; human review and execution freeze remain pending.

## What is implemented

- `src/atabey/submission/v28.py`: dynamic sample discovery, metadata checks,
  frozen image-only pruning eligibility, existing relinking and P2/P3 transforms,
  per-sample CSV export and independent streaming CSV validation.
- `scripts/run_v28_submission.py`: exact-package/scope receipt checks, pinned
  inputs, GPU predictor loading, exclusive run directories, complete test traversal,
  stage telemetry, retained failures and publication only after full validation.
- `scripts/build_v28_notebooks.py`: deterministic embedded source bundle, pinned
  support/checkpoint dataset references, offline dependency installation and
  distinct validation/submission notebooks. It does not upload or execute them.
- `scripts/audit_v28_local_parity.py`: no-GPU parity against retained V24/V27
  evidence; no new official scoring or label access.

The existing linker, route profiling, pruning functions, writer, predictor and
model weights are unchanged. The added adapter invokes existing implementations.
Pruning eligibility is exactly `6bba_` plus adaptive `components`; the reference
CFAR branch cannot override `components`. No V27 intervention, fallback selector,
threshold change, retraining or division repair is introduced.

The delivered graph uses E016 detections and motion-mutual linking. The public
predictor's native edge computation remains intact and its edges are discarded.
Pixel reads retain the historical two-frame window. Graphs and CSV buffers are
processed one sample at a time. Metadata incompatibility, empty required graphs,
missing samples, invalid endpoints, invalid coordinates, duplicate edges and
partial inference failures prevent publication of the final submission file.

## Completed validation

| Check | Result |
|---|---|
| Focused implementation and related regression battery | **83 passed** |
| Image-only pruning eligibility vs retained full-199 records | **199/199 exact** |
| Reconstructed graphs vs saved V27B H/P3 full node/edge attributes | **16/16 exact** |
| Same reconstructed graphs vs historical V24.3 signatures | **16/16 exact** |
| Streaming CSV validation of those real graphs | **16/16 passed; zero rounded nodes** |
| Local predictor imports and CPU checkpoint loading | **Passed; no inference** |
| Static offline dependency closure, Python 3.12/Linux | **62 wheels; no missing requirements or version conflicts** |
| Generated notebooks | Compile, embedded identities match current source, no saved execution, refuse unapproved execution |
| Pinned dataset references | Accepted by the installed Kaggle CLI validator |

The real-graph check starts from saved predictor coordinates, then reruns the
existing association and pruning steps. It establishes graph-construction/export
parity, not new image inference parity. The original three smoke cases and four
catastrophic cases remain required in the GPU validation notebook. The local
199-route/16-graph audit took 125.55 seconds and used no GPU.

Tests cover malformed/changed CSVs, missing/duplicate endpoints, wrong sample
coverage, coordinate bounds and rounding, route gating, failed second-sample
inference, missing/mutated dependencies and wrong-package/scope approvals. Fake
predictors and receipts are explicitly synthetic unit-test fixtures. The actual
CLI has no fake-predictor option.

Original evidence is under `outputs/v28_implementation_20260928/`: the initial
66-pass XML, final 83-pass XML, local parity records/CSVs, import/model check and
offline dependency audit. An initial local packaging attempt used the wrong
Kaggle dataset-reference spelling (`/versions/N`); the CLI rejected it. Its files
remain in `package_r1`. Correct `/N` references were checked before preparing the
current `package_r3`. No remote attempt was made, and scientific behavior did not
change during these packaging revisions.

## Concrete artifacts for review

Validation notebook: [V28 validation](notebooks/V28_validation_offline_kaggle.ipynb).

Submission notebook: [V28 submission](notebooks/V28_submission_offline_kaggle.ipynb).

Current dispatch folders:

- `outputs/v28_implementation_20260928/package_r3/dispatch_validation/`
- `outputs/v28_implementation_20260928/package_r3/dispatch_submission/`

Source bundle: **454,893 bytes**, 75 pinned package files plus its manifest.
The package also verifies 75 support-code/wheel files before import/install.
The clean checkpoint and historical runtime config are checked separately.

Package-manifest SHA-256:
`fb7fde61dd8a1499cc68530cd0a0e3bc8293a803acfaf86edd2f4c67b5e097c3`

Unapproved validation-notebook SHA-256:
`640e8edabb9baabfe71ee9237e00b04af81a43114cace6ebfad031b99641cb30`

Unapproved submission-notebook SHA-256:
`0bcdfd5e6b63364a728ccc8d05c1efdffa25004e8d864a97497a09b5b420f2e2`

Datasets are fixed to support-pack version **10** and clean-checkpoint version
**1**. The older support-pack `tracksdata` wheel is excluded from installation;
the bundle supplies a wheel built from historical commit
`39dccf3a243e44274759468cb31b2ad9e7fc1d09`. All installed wheel bytes are pinned.
Torch and pandas are inherited from the Kaggle image and recorded in telemetry;
their actual versions, GPU identity and inference parity still require the real
offline validation. The current code deliberately refuses Python other than 3.12
because the supplied binary wheels target that ABI.

## Proposed bounded GPU validation

Authorize **validation only** against this reviewed package, with a **2-hour
wall-clock cap**, including notebook setup. At dispatch, use Kaggle's outer
7200-second job timeout as well as the notebook's remaining-time child-process
timeout. One GPU is intended; verify the actual accelerator/quota charge. A
two-GPU allocation could charge up to roughly four GPU hours for that wall cap.
The reported 45-hour balance does not authorize consuming the whole balance.

The job checks the 199 pruning decisions, runs fresh image inference on the
seven fixed parity cases, repeats the first case, processes all visible test
samples and validates the exported CSV. It records setup/profile/inference/link/
prune/export timings, GPU allocation, process peak RSS, output bytes and runtime
package versions. It does not open ground-truth graphs or compute new scores.

It then evaluates a conservative 10-hour projection gate under the explicit
assumption that hidden voxel-frame workload is no larger than the observed
199-sample workload, with 2x measured work and startup/I/O reserve. Hidden shape,
density, filesystem and hardware uncertainty remain; this projection is not a
guarantee of hidden runtime. A mismatch, environment error or gate failure is
retained and blocks progress rather than changing thresholds or tolerances.

Successful validation writes **`validation_submission.csv`**, never the final
Kaggle output name. It cannot count as an authorized competition submission.
After successful validation, review its exact runtime and parity evidence before
authorizing the separate submission receipt. Submission-mode packaging allows
11 hours including setup, retaining margin inside the official 12-hour limit.

Both notebooks currently contain `NOT_APPROVED` receipts and stop before package
extraction. Freezing creates a separate receipt with Danny's actual approval and
the reviewed package identity; preserve the unapproved templates and record the
resulting executable notebook/metadata hashes. Do not invent approval text or
reuse a validation receipt for submission.

The existing accepted V19 submission `54622713` remains the backup. Final-selection
flags, actual GPU quota and the submitted V19 notebook version still need account
verification. V27 artifacts and the unrelated V25 notebook are unchanged. No
commit or push was performed in this implementation step.
