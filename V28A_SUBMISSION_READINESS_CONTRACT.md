# V28A: frozen V24.3 submission readiness

Status: **PROPOSED — preparation and read-only audit authorized; no execution freeze**.

Prepared on 2026-09-28 UTC after Danny accepted the deadline-focused V28 plan.
Builder: Codex. Reviewer and submission authority: Danny; exact-payload approval
has not been recorded. This is a new delivery contract, not an amendment to the
completed V24/V27 scientific decisions.

## Objective and deadline

Prepare one reproducible, offline Kaggle candidate implementing the already
evaluated V24.3 policy. Preserve the accepted V19 submission as the operational
backup. Success means a complete, valid notebook submission accepted by Kaggle
and explicitly selected for final judging; a local CSV, successful visible-test
run or public score alone does not establish all three conditions.

The competition closes **2026-09-29 23:59 UTC / 19:59 America/La_Paz**.
The [official overview](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview)
was checked on 2026-09-28: notebook submission, internet disabled, CPU/GPU runtime
at most 12 hours, output `submission.csv`, and every test dataset represented.
Recheck these requirements and the account's remaining quota before dispatch.

## Candidate and interpretation

Candidate: `e016_atabey_relink_v24_3_short_fragment_shadow`, promoted to a delivery
candidate only through this separate review. Its historical 199-sample result
is descriptive: 172 samples trained the checkpoint and 27 were held out from
training but subsequently opened during development. These are not fresh V28
validation data. The four catastrophic population regressions remain visible:

| Sample | Historical adjusted-edge delta vs V19 |
|---|---:|
| `6bba_2646afc7` | -0.217286 |
| `6bba_2540cd90` | -0.185074 |
| `6bba_76db78c1` | -0.136909 |
| `6bba_d5eae175` | -0.106688 |

Review must acknowledge these cases and all 16 regressions. No sample-ID fallback,
learned selector, route-specific new threshold, division injection, extra pruning,
retraining, ensemble or V27 M1/S1 association change is in scope. V26A remains
NO_GO; V24.8's independent-evidence block remains. No expected hidden score is set.

## Exact algorithm to preserve

1. Discover all test `.zarr` samples dynamically, in sorted order. Do not use the
   199 training IDs or the visible test IDs as a whitelist. Process every frame;
   `max_frames=None`, with no sample/frame cap or error-skipping path.
2. Use the clean E016 checkpoint SHA-256
   `02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03`.
   The historical runtime `config.json` raw hash is
   `e9b4e396c58081bca08adf8275bd0bd1c2d3fd6eb091a1912a5116cb6de7b50a`.
   The local Windows config has different raw line endings; it must not silently
   replace the runtime artifact. The downloaded runtime config matches exactly.
3. Use the public predictor from `pilkwang/biohub-tracking-support-pack-50ep-v1`,
   SHA-256 `c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9`.
   Pin its imported code and dependency closure before freeze, not merely this
   top-level file. Preserve the complete historical `PredictConfig` recorded in
   the machine contract, including `use_ilp=False` and `det_tta=False`.
4. Preserve window size 2, downsample `[1,4,4]`, 32 output channels, layers
   `[32,64,128]`, detection threshold 0.97, pool size 5 microns and the historical
   batch argument 4. The predictor actually processes one two-frame window at a
   time; its batch argument is not evidence of four-window batching.
5. Preserve predictor normalization from image quantiles and original-resolution
   coordinate conversion. Verify dimensions, finite quantiles, time coverage and
   scale compatibility. The linker uses `(1.625,0.40625,0.40625)` microns per voxel;
   fail on incompatible input metadata instead of silently changing physical units.
6. Discard native model edges for the delivered graph. Keep the predictor call
   unchanged initially, including its native-edge computation. Use the existing
   `relink_predictor_detections()` and `motion_mutual` at 9 microns. Preserve source
   and candidate order, exact ties, gating order, reverse mutuality, confidence
   and recursive predecessor history. Do not substitute the V27 variants.
7. Apply `prune_interior_isolated_detections()` followed by
   `prune_interior_short_fragments()` **only when** the sample ID starts with
   `6bba_` and the frozen V19 detector route is `components`. All other samples
   retain the unpruned E016 relink graph. This is the actual evaluated V24.3
   implementation, not a new route chosen from labels.
8. Determine that route using frozen image-only foreground profiling. A minimal
   route-only adapter may avoid building the unused V19 graph only after proving
   equivalence to the reference route: adaptive `components` cannot enter the
   CFAR branch. Preserve thresholds, normalization and the five frame anchors.
   The 199 retained route records may be used as implementation references, never
   for changing policy. Record any mismatch and stop equivalence approval.

The pixel pipeline remains bounded to temporal windows; retain at most one
sample's graph and CSV buffer at a time. Do not load a full image movie or retain
all test graphs. Reuse existing graph, pruning and writer code; add a thin runner.

## Offline packaging and output contract

Package an explicit source manifest, exact checkpoint/config, complete predictor
source closure and required offline dependencies. Pin Kaggle dataset versions,
file hashes and the tested runtime/GPU. No runtime clone, download or online pip
installation. An offline package import must succeed even though the predictor
imports training/evaluation helpers. Do not assume those dependencies are absent
merely because V28 does not score or train.

The execution path reads test images/metadata, weights and packaged code only.
No `.geff` labels, stored training graphs, scientific output archives or train-ID
lookup may supply test predictions. Do not modify the historical baseline kernel.

Reuse `graph_to_submission_rows()` per sample with a cumulative row offset and
stream to a temporary CSV. Verify the final file before atomic publication as
`/kaggle/working/submission.csv`. Required checks:

- Exact header `id,dataset,row_type,node_id,t,z,y,x,source_id,target_id`.
- Consecutive global row IDs; complete and exact discovered dataset coverage.
- Per-dataset unique exported node IDs and valid, same-dataset edge endpoints.
- Finite integer voxel coordinates/time within each source array's dimensions;
  preserve the existing Python `round` convention and node-ID remapping.
- Correct `-1` placeholders; no duplicate edges, backward/non-adjacent edges or
  missing endpoints. Preserve intended graph topology after serialization.
- Compare CSV round-trip structure with the intended export. Separately record
  any coordinate rounding; pre-export metric equality cannot prove post-export
  metric equality if coordinates change.
- An empty graph cannot silently omit a required dataset. Treat missing input
  metadata, failed samples, empty required outputs and malformed rows as errors.
  Preserve partial files/logs under failure names; never publish partial success.

## Evidence required before execution approval

V28A currently supplies an audit and proposed contract. The following must be
completed by the implementation stage, then reviewed against an exact manifest:

1. Focused tests for route gating, unchanged relinking/pruning, serialization,
   missing dependencies, empty/invalid inputs, full discovery and fail-closed
   output handling. Include explicit synthetic fixtures and real saved-graph
   parity witnesses; synthetic tests alone do not establish inference parity.
2. No-label replay of the original three smoke samples
   `44b6_5f15d135`, `44b6_74d0c52e`, `6bba_3c5691b6`, plus the four catastrophic
   cases above, with comparison to saved V24.3 graph signatures. Use opened
   evidence only for implementation parity; no new scoring or parameter choice.
   Repeat one full inference sample for determinism. A GPU/runtime discrepancy
   is investigated explicitly; do not widen tolerances silently.
3. Route-only parity against all 199 retained route records if that optimization
   is used. These checks need source images, not labels or a new full scientific
   evaluation. Missing local images may be checked in the packaging smoke job.
4. A clean Kaggle offline smoke over every visible test sample, with actual
   runtime, CPU/GPU identity, RSS/GPU memory, disk usage and output validation.
   Quantify initialization, profiling, inference, linking, pruning and CSV costs.
5. A workload-aware projection including every stage. Proposed operational gate:
   conservative projection at most 10 hours, leaving 2 hours inside the official
   12-hour limit. Show the workload assumption and at least a 2x measured-work
   scenario; visible-test success alone does not prove hidden-test feasibility.
   Actual hidden runtime remains unverified until Kaggle processes the submission.
6. Manifest containing all input package versions/hashes, code, settings, tests,
   parity and runtime evidence, notebook metadata, and the exact output filename.
   Danny reviews the four regression cases, remaining limitations and payload.

Implementation work and local invariant checks can prepare this package. Any
remote GPU validation job needs a specific reviewed scope and resource budget;
the final competition submission requires Danny's explicit exact-package approval.
This proposed document itself authorizes neither remote execution nor submission.

## Delivery and fallback policy

Use one V24.3 candidate and the existing completed V19 as backup. The audit found
V19 submission reference `54622713`, public score `0.515`, submitted 2026-07-12.
Its final-selection flag and submitted notebook version are not exposed by the
queried API and still require verification. Latest baseline source equality does
not by itself bind that source to the submitted version. Preserve the accepted
submission; do not recreate it unless necessary and specifically reviewed.

Do not compare V24.3's local 0.721056 with V19's public 0.515 as a predicted gain.
If V24.3 fails any delivery gate, keep V19 as the submission-level backup; no
per-sample substitution. If only one candidate passes, select only that candidate.
If both are accepted and Kaggle permits two final selections, recommend retaining
both for Danny's final decision. Verify the allowed count and selection receipt;
do not rely on automatic selection. No leaderboard-driven parameter search.

Operational targets (not promises of completion): package/review during September
28, first approved submission by September 28 23:59 UTC, and no new experimental
policy thereafter. September 29 05:59 UTC is the planned last fresh-run start
(18 hours before close); later work prioritizes completion and accepted backup.
Aim to verify final selection by September 29 17:59 UTC (6 hours before close).
Queued/slow jobs do not move the official deadline. Each failed packaging attempt
gets a separate retained record and a newly identified corrected package.

## Review record

- Plan acceptance: Danny, "me parece bien amor"; scope is V28A preparation/audit.
- Builder: Codex.
- Exact implementation manifest: not yet available.
- Independent review / execution authority / final-selection receipt: pending.
- See [readiness audit](V28A_SUBMISSION_READINESS_AUDIT.md) and
  [machine contract](tests/fixtures/v28a_submission_readiness.json).
