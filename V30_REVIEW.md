# V30 preparation review

**Status: proposed methodology; implementation pending.**

V30 asks where the saved V28-control and V29A-TTA outputs differ, so that a later
optimization can target a documented failure mode. It does not change V29A's
NO_GO decision or establish that V28 can achieve a particular higher score.

## Review package

- [Diagnostic contract](V30_DIAGNOSTIC_CONTRACT.md): definitions, scope, validity,
  reporting rules, explicit unmeasured mechanisms and required synthetic checks.
- [Machine proposal](v30_diagnostic_proposal_20260928.json): exact cohort, input
  hashes, source/runtime pins, focus memberships and proposed two-hour CPU budget.
- [Preparation audit](outputs/v30_preparation_20260928/input_audit.json): verified
  existing evidence identities. It is not a diagnostic execution result.
- [Preparation procedure](outputs/prepare_v30_diagnostic_20260928.py): inventory
  and lineage checks only; its output directory is exclusive and not reusable.

## Proposed analysis

| Layer | What V30 would report | What it would not establish |
| --- | --- | --- |
| Coordinates | Exact anchors, isolated nearby pairs, unresolved/duplicate coordinates | Biological identity or actual cell disappearance |
| Linking | Changed endpoints and confidence, with predecessor/chain context | Ranking, tie or history as an isolated cause |
| Pruning | Actual RAW → P2 → P3 removals under each frozen route | Benefit of a new pruning policy |
| Existing metrics | Published edge, node-adjustment and division changes alongside structural changes | New GT scores or independent validation |

All 199 samples remain in the report. Detailed focus is the union of 25 previously
opened losses greater than 0.020 and the four protected samples: **28 distinct
samples**, because one protected sample also belongs to the loss group.
The original five strata and both pruning-route groups retain explicit coverage.

The worst published loss, `44b6_40c45f5a`, has `apply_pruning: false` in the saved
[TTA record](outputs/v29a_execution_20260928/downloaded/v29a_run/records/44b6_40c45f5a.json).
Executed pruning therefore cannot explain that sample's regression. The proposed
analysis keeps coordinate changes, association changes and the existing metric's
node-count adjustment visible rather than assuming a single mechanism.

The 2.0-micron secondary correspondence radius is a proposed descriptive choice.
It is not tuned to these coordinates, an official matching radius, or an identity
guarantee. Exact-only results remain primary; ambiguous cases stay unresolved.

## Preparation verification

The identity-only audit verified:

- 199 paired samples, 398 coordinate files and 398 inference records against
  the frozen inference manifest and each record's coordinate hash.
- 81 source-bundle members, with 76 local scientific source files matching their
  normalized bundled bytes.
- All 76 V28 release artifacts and all 479 V29A release artifacts.
- Parent result/summary/package lineage, existing graph-signature references,
  route/shape/scale metadata and the pinned local runtime package versions.

No new graph has been reconstructed, coordinate correspondence measured or
official evaluator run during this preparation. Runtime availability and file
identity do not prove future replay parity. GT files and live Kaggle selections
were not queried in this preparation; no changes were made to them.

## Next step

Review these definitions, then implement the additive diagnostic runner and its
synthetic checks. Review the exact implementation before approving a freeze and
one diagnostic execution. The current proposal deliberately contains no approved
runner or execution receipt. A later intervention, GPU run, submission or
publication would have its own explicit scope and authority.
