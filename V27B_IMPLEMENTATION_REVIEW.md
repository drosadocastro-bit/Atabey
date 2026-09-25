# V27B implementation review

Date: 2026-09-24

Status: **IMPLEMENTED; VALIDATED; CANDIDATE READY FOR HUMAN REVIEW**.

Danny authorized implementation of the reviewed
[V27B contract](V27B_RECURSIVE_HISTORY_PREREGISTRATION.md). Its protocol and machine
specification remain byte/content-pinned in their proposed form as historical
review inputs. This additive report records the implementation. No V27B cohort
execution or approved freeze has been created.

## Implemented behavior

The new [shadow orchestrator](src/atabey/tracking/recursive_history_audit.py)
calls the unchanged V27A.1 observer for each arm's own history. All five probe
decisions are retained, but only the named active arm supplies accepted edges to
its next transition. Predecessor state is replaced after complete assignment;
unaccepted or expired history cannot persist. Each sample and replay starts with
five empty, independent histories.

The [runner](scripts/run_v27b_recursive_history.py) first reproduces the complete
frozen-history frame stream through the unchanged V27A.1 replay function. It
requires the compressed stream hash and full count dictionary to match the
reviewed reference before beginning recursive observation. F decisions are never
assembled into alternative graphs.

For R, the orchestrator retains all detections and uses unchanged assignment,
confidence and relation semantics. It records predecessor and prediction changes,
target outcomes, confidence-only changes, first divergences, F/R paired contrasts,
interaction distributions and history-sensitivity accounting. Primary source
counts are separate from the five common-context probe counts.

Exact-tie validation is confined to common-history probes. Direct R_H/R_M0
comparisons may differ without a current tie after prior history divergence.
Identical full input contexts must reproduce identical parent observation
digests. H must reproduce the historical graph and decisions; S1 must reproduce
the unchanged recursive V26A executable, including edge confidences.

Only after recursive linking finishes does the orchestrator call the unchanged
V24.2 and V24.3 pruning functions. It retains RAW/P2/P3 graphs, removals, stage
contrasts and endpoint/edge survival for the complete union of each paired raw
edge set. Shared raw edges that survive in only one final graph remain visible.
Pruning is checked for input mutation, created identities, missing endpoints and
changes to retained attributes. It never supplies history to linking.

Each sample receives two fresh pass directories. A pass writes 15 graph-stage
files, its reproduced F stream, recursive context/probe/comparison stream,
pruning stream and summary. Thus the cohort has 240 scientific graph stages in
each pass (480 physical graph copies across the two deterministic replays).
The runner compares scientific inventories, graph signatures, ledgers and counts
exactly. Timing and Python memory telemetry are stored separately.

## Failure preservation and execution boundary

The runner requires an explicit approved manifest hash, FROZEN status, review by
a named reviewer distinct from the builder, and human authorization covering
the exact V27B payload and scope. It rejects the unchanged proposal and a
READY_FOR_HUMAN_REVIEW candidate. V27A.1 authorization cannot satisfy this scope.
The exact reviewed V27B contract hash is enforced rather than accepting arbitrary
edited configuration fields.

Before and after an approved execution, source, runtime, test-report and input
identities are checked. Archive membership, all reference anchors and the full
cohort are mandatory. Outputs cannot overwrite or resume an existing directory.
The runner retains failure status, active sample/pass context, partial artifacts
and an inventory on failure. Recursive inputs are written before observer calls;
pruning inputs are written before transformations, preserving evidence even if
the operation raises or mutates its input. There is no automatic retry.

## Validation completed

- **38 V27B tests** cover recursive/frozen divergence, arm and pass isolation,
  empty-frame reset, original target ordering, initial-history equality,
  confidence-only changes, and complete deterministic synthetic passes.
- A synthetic 17-target exact tie gives H and M0 different first choices. The
  following transition has distinct non-tied decisions under their own histories
  while every common-history validity probe passes.
- Tests cover shared raw-edge survival divergence after pruning, mutation and
  attribute-corruption rejection, missing/extra F frames, failed anchor evidence,
  and persistence before observation failures.
- Freeze tests use explicitly named synthetic reviewer/authority/runtime records
  in temporary repositories. They validate missing authorization, wrong scope,
  builder self-review, omitted/tampered sources, contract changes, runtime/test
  evidence drift, input-byte changes and overwrite rejection. These records are
  not real execution approvals.
- The combined V27B, V27A.1, V27A, V26, V25 and pruning battery passed
  **133 tests**, with zero failures, errors or skips. It includes the known opened
  exact-tie gate witness as a regression, not independent evidence.
- All **97 parent source identities**, the **50 V27A.1 raw artifacts**, the
  reviewed V27B protocol/contract and linked inputs remain unchanged. The new
  candidate was checked again from a separate imported invocation.

Test report: `outputs/v27b_validation_20260924.xml`

SHA-256:
`987fd245d968641cbf257b29ab0dc6c72f8e86b525535b0c4bc8730f7d978c99`

These are builder implementation checks, not an independent scientific review.
The full recursive cohort behavior and resource requirements remain unmeasured.
Adding implementation files expands the workspace source inventory; preservation
means the parent's recorded files match, not that its old whole-workspace
preflight accepts the expanded tree.

## Candidate for review

[v27b_freeze_candidate_20260924.json](v27b_freeze_candidate_20260924.json)

- Status: `READY_FOR_HUMAN_REVIEW`
- Scope: `V27B_RECURSIVE_HISTORY_AND_PRUNING_RESPONSE`
- Pinned sources: **103**
- Distinct input artifact paths: **59**, including all 50 prior raw files
- Runtime: CPython 3.13.14; **146** distinct package/version pairs recorded
- Human review and execution authorization: **null**

Candidate SHA-256:
`bb997b00e4fe0880882ef8b4b08a6f2faf01db1741cacd98db99d70d21201446`

Payload SHA-256:
`e41ae805c2c49f3044423d5cf24c561716293cde56b48f2bfb408fa4ab256b74`

The next execution requires a separate approved manifest naming this exact
payload, with the human review and authorization records. Preserve this candidate.
The approved run must use a new output directory:

```powershell
.\.venv\Scripts\python.exe scripts/run_v27b_recursive_history.py run `
  --freeze <approved-v27b-manifest.json> `
  --approved-freeze-sha256 <approved-manifest-sha256> `
  --output-dir <new-v27b-output-directory>
```

No new official rematching or scoring, model inference, tuning, production
promotion or submission is included. V26A remains NO_GO, original V27A remains
INVALID_EXECUTION, and V27B remains unexecuted on the cohort.
