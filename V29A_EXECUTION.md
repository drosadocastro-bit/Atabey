# V29A approved research execution

Status: **COMPLETE AND VERIFIED; promotion decision NO_GO**.
Initial timing/reproducibility gate passed. Dispatched
September 28, 2026, 11:46:49 UTC.
This document records execution status and will be updated from the preserved
run evidence. No quality result or submission decision is available yet.

Danny approved freezing and executing the reviewed research package in this
chat. `v29a_research_freeze_approved_20260928.json` preserves the candidate
payload unchanged, its digest, the approval statement and authority record.

- Candidate payload SHA-256:
  `c4edda67ad121bd34c7e4bba6e29f432de039401d3a20fe94846412d0890d25f`
- Package manifest SHA-256:
  `7d93749e50dfe95fa1643dceb39e870f9111850ce994c14c30ca1496ddd4dc67`
- Approved dispatch notebook SHA-256:
  `353d03aa426e51f5c7314d16075fe7741e16fc80dc9c6a9f17027f9e6ed1d448`
- Kaggle research kernel: `drakus74/atabey-v29a-tta-research`,
  ID 136251327, version 1.
- Server session timeout: 21,600 seconds. The notebook separately limits its
  inference child to the remaining approved time after setup.

All 19 candidate artifacts passed their raw-byte identity checks immediately
before dispatch. The dispatch notebook differs from the reviewed template only
in the approval receipt. The pulled remote source matches that dispatch source;
the actual image matches the frozen V28-tested image, with T4 and no internet.
Remaining quota before dispatch was 44.789679 device-hours. The selected entries
were still V28 56631581 and V19 54622713. The authenticated competition timeline
still named September 29, 2026 as the final deadline.

Execution receipts, quota, competition pages, remote source verification and
incremental status/log snapshots are in `outputs/v29a_execution_20260928`.
Only completed, timing-approved and hash-verified inference may enter the
already approved local scoring phase, capped at 10,800 seconds.

This approval covers research only. No competition submission, selection change,
retry or publication is authorized by this execution record. V28 stays frozen.

## Progress and continuing execution

The live log reached `completed: 8` after all seven historical controls, both
TTA repeats, four visible exports, CSV validation and the initial runtime gate.
The approved runner only enters that full-cohort loop after those checks pass.
This is execution progress, not evidence of improved official quality.
The exact projection values remain pending download and independent verification.

The authenticated live-log connections ended prematurely four times; the raw
events and transport errors are preserved. These were local read-only monitoring
failures. No GPU execution was restarted and no scientific output was altered.

A local background supervisor started at 12:07:26 UTC (process 5784). It observes
the existing job, verifies the remote source again at completion, downloads once,
verifies output hashes and receipt lineage, and conditionally invokes the frozen
local evaluator with its 10,800-second outer timeout. The evaluator performs the
full timing, coverage, coordinate, source, dependency and GT checks before
returning a quality decision. Remote failure or `NO_GO_RUNTIME` skips scoring;
no second research dispatch is permitted. Completion and any failures will be
written under `outputs/v29a_execution_20260928` as `supervisor_finished.json`
or `supervisor_failure.json`, with separate evaluation logs and results.

The continuing supervisor and CPU phase depend on this Windows computer staying
awake and connected. The remote Kaggle execution has its own server timeout.
There is no automatic competition submission or selection change at completion.

## User-requested pause before travel

Danny asked to stop the timer before shutting down the computer and will notify
this chat when Kaggle finishes. The heartbeat was paused and the identified
local supervisor process 5784 was stopped intentionally. Its absence is not an
execution failure. The latest saved remote status was RUNNING at 15:22:01 UTC.
No Kaggle cancellation or scientific retry was requested or performed, and local
evaluation had not started. The remote job retains its six-hour server limit.

On Danny's return, inspect the existing version 1, collect its output and verify
the frozen contract before conditionally resuming the approved CPU phase. Do
not relaunch GPU inference. See `outputs/v29a_execution_20260928/user_pause_20260928.json`.

## Resume after remote completion

Danny notified this chat that the notebook finished. At approximately 19:13 UTC,
the authenticated API reported COMPLETE. The completed log records 199 cases,
`INFERENCE_COMPLETE`, and 17,350.063760169003 seconds including setup (4 h 49 min
10 s). The remote notebook source and actual software image still match the
approved dispatch, and all 19 candidate artifact hashes remain unchanged.

V28 56631581 (0.728) and V19 54622713 (0.515) remain selected. No submission or
selection change was made. The GPU quota query reported 18,130.139 seconds used
of 162,000, with none reserved; this is account quota telemetry, not an inferred
device-hours multiplier.

The initial SDK output enumeration hit HTTP 429 before downloading any file.
A larger-page retrieval was rejected with HTTP 400. Both transport failures are
preserved, and retrieval continues with known-supported 100-item pages paced
three seconds apart. Scientific inference has not been retried. Local official
evaluation starts only once, after the completed files and receipt pass checks.
The heartbeat remains paused; the resumed collection process is active in this
chat. These remote completion facts do not yet establish quality improvement.

## Final verified outcome

Local paired official evaluation completed all 199 samples at 19:44:07 UTC in
1,003.818 seconds, with successful process exit. The final independent evidence
audit completed at 19:44:34 UTC. Every fresh baseline reproduced its historical
official metrics; both timing projections, the official repeat, source/runtime,
GT identities and all frozen decision gates were verified.

The local aggregate score increased from 0.721055749 to 0.735927590
(+0.014871840), with 134 improved and 65 regressed samples. Six quality gates
passed, but the maximum individual-loss gate and the four-protected-case gate
failed. The worst loss was -0.106430206, and protected case `6bba_76db78c1`
lost 0.045537786. The frozen result is therefore **NO_GO**, not an invalid run.

See `V29A_RESULTS.md` for all gates, subgroup results and evidence links.
V28 0.728 and V19 0.515 remain selected; all 76 frozen V28 artifacts are intact.
No submission, selection change, scientific retry, commit or push was performed.
The heartbeat remains paused. The local evaluation and retrieval processes have
finished; no new supervisor is needed.
