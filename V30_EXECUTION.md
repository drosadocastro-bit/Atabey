# V30 approved execution

Status: **COMPLETE_EVIDENCE_VERIFIED**. One CPU saved-coordinate diagnostic was launched on
2026-09-28 after Danny reviewed the implementation and approved freezing and
execution. This file is an execution log, separate from the immutable proposal
and implementation review.

Approval text: "esto esta bien estructurado  baby , aprobado para congelar y ejecutar"

- [Approval receipt](v30_freeze_approved_20260928.json), SHA-256
  `5159c0ba8bfa58100e5426cec3f19b781a0faaafb417da21bc7707b35b896137`.
- [Implementation candidate](v30_implementation_candidate_20260928.json), SHA-256
  `3b902b1d9547c1c2403fd4f7cb25442598c70cc500d2a6af5a66cf1ff93f8cf0`.
- [Execution record](outputs/v30_execution_20260928/execution.json).
- [Input preflight](outputs/v30_execution_20260928/preflight.json).
- [Console log](outputs/v30_launch_20260928/console.log).

Scope: one diagnostic of the saved 199 sample pairs, using the frozen route and
graph functions. The two-hour wall limit includes preflight and closure. No new
inference, GT scoring, competition submission, selection change, retry, commit or
push is authorized. V29A remains NO_GO; V28's frozen result is unchanged.

The single run completed all 199 pairs in **1,505.58 seconds (25 min 6 s)**.
All 398 final graph/export parities passed. The terminal result/report hashes
validated and neither a worker failure nor a terminal failure receipt exists.

The independent read-only audit verified all 1,194 serialized stage signatures,
1,194 stage/view edge partitions, node/frame/removal accounting, reciprocal
correspondence records and the copied official metrics. It also rechecked the
input inventory, runtime versions and all 76 V28 / 479 V29A release artifacts.
It did not reconstruct graphs, rerun matching, or perform new GT evaluation.

- [Terminal receipt](outputs/v30_execution_20260928/finished.json).
- [Independent verification](outputs/v30_execution_20260928/independent_verification.json).
- [Interpretation and limits](V30_RESULTS.md).
- [All-sample report](outputs/v30_execution_20260928/REPORT.md).

Result SHA-256: `51524270fad715d9103621e8ddd0e155ac39d7031f27c99e9b5f4f54c577275a`.
No scientific retry, new inference, scoring, submission, commit or push occurred.
The historical proposal/review status texts remain unchanged; this execution log
and the approved receipt record the subsequent authorization and completion.
