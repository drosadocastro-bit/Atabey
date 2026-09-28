# V27C proposal review packet

Date: 2026-09-27

Status: **READY FOR DESIGN REVIEW — NOT AN EXECUTABLE FREEZE**.

Builder: Codex. Human reviewer and execution authority: not yet recorded for a
V27C implementation payload. This packet is builder verification, not independent
scientific review.

## Prepared artifacts

- [Preregistration](V27C_OFFICIAL_GRAPH_EVALUATION_PREREGISTRATION.md): evaluation
  question, fixed matrix, matching and metric semantics, ledgers, failure policy
  and authorization boundary.
- [Machine contract](tests/fixtures/v27c_official_graph_evaluation.json): concrete
  graph, GT, evaluator, runtime, parent-source and historical-anchor identities.
- [Proposal validation](v27c_contract_validation_20260927.json): read-only input
  and design checks, explicitly separate from cohort evaluation.

## Design choices to review

The primary diagnostic endpoint is adjusted edge Jaccard from the pinned host.
All five recursive arms and all three saved graph stages are mandatory. Eight
arm contrasts and three within-arm stage contrasts preserve individual sample
effects and host aggregation. There is no winner-selection threshold.

Every evaluation uses fresh prediction and GT host graphs. Metrics and ledgers
come from the same matched state. The current correspondence adapter exposes
matched edges but not the host's `pred_valid` flag; a separate bounded instrument
must expose that flag while preserving the parent-frozen adapters. Otherwise an
unmatched edge outside sparse annotation coverage could be misreported as an
official false positive.

The four-way edge partition distinguishes official TP, official FP, edges not
evaluated by sparse GT, and edges filtered by the host. Pruning comparisons
separate physical deletion from changes in matching and evaluability on surviving
edges. These ledgers explain the metric accounting without claiming independent
biological causality.

Historical H/P3 and S1/P3 metric anchors must reproduce archived V26A results
with exact integer/null agreement and absolute tolerance 1e-12 for historical
finite floats. Both new passes require exact scientific digests. Current GEFF
bytes are pinned for V27C; the old archive does not by itself prove their
historical byte identity. Any anchor disagreement stops execution for a separate
diagnosis rather than silently changing the contract.

## Readiness and remaining work

The proposal names 240 distinct saved graphs and their 480 physical copies,
32 parent pass summaries, 16 local GEFF trees with 336 files, and the unchanged
103 parent source identities. Both installed host packages report the required
VCS commits; the contract also records their 103 Python source files and the
146-package runtime reference. The protocol fixes the 7 um evaluation radius
separately from the historical 9 um tracking gates.

Only file/graph integrity, metadata, source inspection and existing archived
metric extraction were performed. No new cohort correspondence or metric was
computed. No V27C runner or evaluation instrument has been implemented or tested.
The validation record states exactly which structural checks completed.

Next, implement the instrument and frozen runner, validate synthetic cases and
failure paths, and prepare the implementation review and exact candidate payload.
Human review and approval of that payload precede freezing and cohort execution,
as specified in the preregistration. The null fields in this proposal cannot
authorize execution; V27B approval remains scoped to V27B.

V26A remains NO_GO and V24.8's independent-data block remains intact. A valid
V27C result, favorable or adverse, will describe these opened samples only.
