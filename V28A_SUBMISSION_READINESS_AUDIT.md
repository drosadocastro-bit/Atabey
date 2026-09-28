# V28A delivery readiness audit

Date: 2026-09-28 UTC. Builder: Codex.

Decision: **AUDIT_COMPLETE_IMPLEMENTATION_NOT_READY_FOR_EXECUTION**.

V24.3 is a concrete candidate for offline submission packaging. The accepted V19
backup exists. This audit does not freeze an implementation, run inference, submit
to Kaggle or select final entries. The next work is the thin offline test runner,
its notebook/package and the parity/runtime checks in the
[proposed contract](V28A_SUBMISSION_READINESS_CONTRACT.md).

## Verified account and backup state

An authenticated read-only Kaggle query returned eight submissions (page size
200). All eight were `SubmissionStatus.COMPLETE`. The most recent returned row:

| Field | Observation |
|---|---|
| Submission reference | `54622713` |
| Submitted | 2026-07-12 21:43:29 UTC |
| Description | V19 watershed refinement, profile-based routing, 6bba-only CFAR+sidelobe cap 900 |
| Public score | `0.515` |
| Private score | Not exposed |
| Final-selection flag | Not exposed by this API |

The latest source downloaded from
[`drakus74/atabey-adaptive-baseline`](https://www.kaggle.com/code/drakus74/atabey-adaptive-baseline)
matches local `kaggle_kernel/run.py` byte for byte. Its raw SHA-256 is
`a105ab6f15efcd393a08f41816b82ab8673ae0b72b986c0687b6c7e6643187ac`.
Remote metadata shows internet disabled, GPU disabled and the competition input;
the latest kernel status was COMPLETE. The output listing includes a CSV.

These observations establish an existing accepted backup and current baseline
source equality separately. They do not identify the notebook version attached
to submission `54622713`, prove final selection, or measure hidden execution time.
Keep that accepted submission intact; verify its version/selection in Kaggle
before final delivery. GPU availability, remaining quota and final-selection
limit were not obtained by the queried interfaces.

## Verified V24.3 identities

The full-199 archive and embedded summary match the hashes recorded in
`v24_3_full_199_score_validation_report.json`. The archive contains 199 unique
sample records. Thirteen inspected core source files, including graph conversion,
linker, both pruning functions, route profiling, writer and reference runners,
match evaluation commit `2af9cbf3f192171e669db223967f8ba8eedb6d81` after canonical
newline normalization. This is a scoped source check, not the final transitive
runtime manifest.

| Artifact | Verification |
|---|---|
| Local clean E016 weights | Match historical `02e1d657...fd03` |
| Weights downloaded from `drakus74/v22-e016-clean-checkpoint` | Same exact bytes/hash |
| Downloaded runtime config | Matches historical `e9b4e396...b50a` |
| Downloaded public predictor | Matches historical `c44e771b...34b9` |

The local checkpoint config has CRLF line endings and raw hash
`329706a54464bbab2eb48f11a301ec64ee57b598164454402c57d510c6110640`.
Its JSON value and LF-normalized bytes agree with the historical runtime config.
Both originals were preserved; the exact downloaded runtime bytes are available
for packaging. This is a packaging distinction, not a model change.

## Actual algorithm and delivery gaps

The V24.3 notebook evaluates train images against `.geff` ground truth and uses
online clone/install operations. It cannot serve directly as the offline
competition submission. The current submission kernel is V19, not V24.3.

The V24.3 implementation applies P2 then P3 only when
`sample_id.startswith('6bba_') and detector == 'components'`. Ninety of the 199
retained records satisfy that predicate. The other routes retain unpruned E016
relink graphs. Applying pruning globally would change the evaluated method.

The detector route originates in frozen foreground profiling. A route-only
adapter can potentially omit construction of the unused V19 graph: the reference
CFAR predicate cannot select adaptive `components`. This is a proposed execution
optimization that still needs route parity, not an already validated new runner.

The downloaded predictor processes two-frame windows with `load_image=False`;
it retains coordinates/edges, not a full image movie. The configured batch
argument 4 is not evidence of batched windows: the inspected loop encodes one
window at a time. It also computes native edges that the V24.3 arm discards.
Keep that call unchanged for the first package.

The support dataset lists offline wheels, including Python-3.12-specific binary
wheels. File presence does not prove compatibility with the next Kaggle runtime.
The predictor imports training/evaluation helpers and `tracksdata`; a complete
import/dependency audit and clean offline smoke remain necessary. No packages
were installed during this audit, and no predictor code was executed.

`graph_to_submission_rows()` already maps internal IDs and emits the official
columns with integer rounding. The new runner must call it one sample at a time,
validate complete output and publish atomically. Current generic serialization
alone does not check every required invariant, input bound or dataset's presence.

## Runtime evidence and its limits

The saved V24.3 `runtime_seconds` values across 199 samples sum to:

- **3,976.199 seconds / 1.1045 hours** for predictor inference plus relinking.
- Median sample: **17.732 seconds**; maximum: **41.034 seconds**.
- V19 reference construction separately totals **4.6547 hours** in the same
  retained records; this is motivation to examine route-only execution.

Inspection of the recording code shows that the V24.3 time excludes route
profiling, both pruning stages, serialization and environment startup. It
includes the public predictor's native-edge computation. These are historical
component timings on the evaluated workload, not a complete submission runtime,
not the duration of the entire multi-arm evaluation and not a hidden-test bound.
This audit did not run a new GPU benchmark.

The contract therefore proposes a measured offline run and a workload-aware
10-hour conservative projection, including a 2x measured-work scenario, inside
Kaggle's 12-hour limit. Hidden sample count/shapes, hardware and queue time must
remain explicit uncertainties; the visible placeholder set alone is insufficient.

## Readiness disposition

| Item | State |
|---|---|
| Completed V19 submission | Verified |
| Exact V24.3 model/predictor available | Verified |
| Scoped historical core-source parity | 13/13 verified |
| Historical archive/summary integrity | Verified |
| V24.3 offline test-only runner | To implement |
| Source/dependency closure and dataset-version pins | Pending |
| Actual GPU/quota, offline imports and runtime | Pending |
| Graph/inference/route/CSV parity | Specified, not executed |
| Exact-package review and execution freeze | Pending |
| Final submission selection | Not verified |

Existing V24/V27 outcomes are unchanged. The four catastrophic V24.3 cases and
all 16 population regressions are retained in the review boundary. V27's 16-case
results select no replacement policy. There are zero untouched labeled samples
for a fresh independent experiment in the recorded cohort inventory.

The proposed next step is implementation of this one frozen-method delivery
path. Resolve the package and parity checks before presenting an execution
manifest; do not substitute a new model or policy to make packaging pass.

## Evidence and scope

- [Machine audit](v28a_submission_readiness_20260928.json), SHA-256
  `afff793d4484c107660d888987c881c1d6011a7b5a8ff4748c02d9a7aef31aac`.
- [Proposed machine contract](tests/fixtures/v28a_submission_readiness.json),
  SHA-256 `91838a2a0d0cd798c31c9b39278f0e6936352b303c6265476dd2b95fab1d7787`.
- Read-only derivation: `outputs/build_v28a_readiness_20260928.py`.
- Original API/download evidence: `outputs/v28a_readiness_20260928/`.
- Official requirements checked at the
  [competition overview](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview).

This stage made read-only Kaggle queries/downloads and created local proposal
artifacts. It did not edit scientific source, rerun experiments, upload datasets,
start remote jobs, submit, select entries, commit or push. V27 frozen artifacts
and the pre-existing V25 notebook modification remain outside this change.
