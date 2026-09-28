# V30 results: valid descriptive diagnostic

**COMPLETE_EVIDENCE_VERIFIED.** The single approved CPU execution completed all
199 saved sample pairs in **25 min 6 s**, within the two-hour limit. All **398
final graph/export parities** passed. Independent output accounting verified
1,194 serialized stage signatures and 1,194 stage/view edge partitions. No new
inference or official GT scoring was performed. V29A remains **NO_GO**.

## What the strong losses have in common

All **25** previously opened losses exceeding 0.020 had worse official edge
Jaccard. The arithmetic node-count adjustment residual improved in **24/25**;
**19/25** had pruning disabled. Node recall improved in six, was unchanged in
three, and worsened in sixteen. These are copied V29A metrics joined to the
diagnostic, not fresh evaluations.

The residual is the arithmetic difference between adjusted and unadjusted edge
Jaccard. It depends on both quantities; a less-negative residual is not by itself
proof of better node-count calibration or an isolated causal penalty effect.

The observed losses therefore cannot generally be explained by executed pruning
or a worse node-count adjustment. The edge metric can change through detection
localization, GT correspondence and temporal association together. V30 does not
separate these causes or prove that changing the linker would recover the loss.

## Coordinate coverage and uncertainty

| RAW coordinate category | V28 control | V29A TTA |
| --- | ---: | ---: |
| EXACT | 2,091,027 | 2,091,027 |
| NEAR_ISOLATED | 1,761,493 | 1,761,493 |
| NO_NEAR_COUNTERPART | 1,646,526 | 1,460,104 |
| NEAR_AMBIGUOUS | 1,452 | 949 |
| DUPLICATE_AMBIGUOUS | 0 | 0 |

The 2,091,027 exact pairs cover **38.02%** of control and **39.35%** of TTA RAW
nodes. Including the 1,761,493 isolated nearby pairs raises geometric coverage to
**70.04% / 72.50%**. Nearby correspondence is supplementary and is not cell identity.
NO_NEAR_COUNTERPART does not establish a disappeared or newly appearing cell.

Among exact-mapped sources, **71.85%** of recursive histories are unresolved;
the expanded geometric view still leaves **51.89%** unresolved. This limits
mechanistic attribution. Low geometric ambiguity does not imply biological certainty.

## Associations and confidence are different observations

| RAW edge comparison | Exact-only | Exact plus nearby |
| --- | ---: | ---: |
| common | 837,354 | 2,496,936 |
| baseline_only | 25,631 | 111,297 |
| tta_only | 28,817 | 126,470 |
| confidence_only_changes | 371,945 | 1,688,556 |
| baseline_unmapped_endpoint | 3,767,160 | 2,021,912 |
| tta_unmapped_endpoint | 3,649,165 | 1,891,930 |

In the exact-only view, 1,544 mapped sources changed from one mapped successor to
another. Another 16,802 had only a control outgoing link and 18,540 only a TTA
outgoing link. A further 1,050,409 outgoing comparisons were unresolved because
an endpoint was unmapped. Edge differences are not counts of wrong associations.

The 371,945 confidence-only changes on common exact-anchored RAW edges must not
be confused with changed endpoints. Neither these counts nor different recursive
histories isolate ranking, tie behavior, candidate order or history as causes.

## Actual pruning under the fixed routes

Pruning was enabled for 90 samples and disabled for 109. P2 removes isolated
nodes; P3 also removes edges belonging to short fragments. Totals below describe
the executed branches, not a new pruning intervention or stage-specific score.

| Arm | RAW nodes | After P2 | After P3 | RAW edges | Final edges |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 5,500,498 | 5,462,732 | 5,422,524 | 4,630,145 | 4,610,041 |
| tta | 5,313,573 | 5,282,877 | 5,249,057 | 4,515,336 | 4,498,426 |

## Two concrete cases

The worst loss, **44b6_40c45f5a**, had pruning disabled. Score fell
**0.106430206**; edge Jaccard fell **0.111644816**, while the node-adjustment
residual improved **0.005214610**. There were 15,741 exact pairs, 251 control-only
and 250 TTA-only RAW edges within that exact comparison, alongside 2,775
confidence-only changes. Most RAW edges had at least one unmapped endpoint, so
these counts cannot explain the entire metric difference.

The protected regression, **6bba_76db78c1**, lost **0.045537786** despite slightly
better node recall and a better node-adjustment residual. Both arms removed
286 nodes / 143 edges at P3, but the identities differed: among exact anchors,
57 control survivors were removed in TTA and 57 TTA survivors were removed in
control. Equal removal totals did not establish equal treatment of detections.

## Coverage of the declared groups

| Group | Samples | Control RAW nodes | TTA RAW nodes | Exact pairs |
| --- | ---: | ---: | ---: | ---: |
| checkpoint_training_172 | 172 | 4,841,142 | 4,681,048 | 1,850,222 |
| family_44b6 | 71 | 2,989,762 | 2,891,936 | 1,162,736 |
| family_6bba | 128 | 2,510,736 | 2,421,637 | 928,291 |
| focus | 28 | 883,544 | 855,020 | 345,304 |
| held_out_27 | 27 | 659,356 | 632,525 | 240,805 |
| historical_regressions_16 | 16 | 99,976 | 93,359 | 40,044 |
| protected | 4 | 21,047 | 20,143 | 8,691 |
| pruning_false | 109 | 4,491,663 | 4,350,392 | 1,702,198 |
| pruning_true | 90 | 1,008,835 | 963,181 | 388,829 |
| strong_losses | 25 | 869,065 | 841,361 | 338,515 |

Groups overlap. The 172 training and 27 checkpoint-held-out samples were already
opened; neither is new independent validation. The 28 focus samples are the
outcome-selected union of the 25 strong losses and all four protected IDs.

## Recommendation and limits

V30 leaves room for a future optimization hypothesis but does not demonstrate a
new improvement or V28's ceiling. The next useful step is a **separate V31
association-trace contract**: expose forward/reverse candidates, eligibility,
exact ties and predecessor state around changed links, distinguishing changed
candidate populations from changed history before proposing a policy change.
Unmapped comparisons must remain unresolved. Any causal intervention must freeze
operation order, ranking, ties and history separately, following the V27 lesson.

Prioritize this question over further node-count/pruning tuning as a general
remedy for these losses. This is a research recommendation, not proof that a
linker modification will improve quality. No V31 work is executed or authorized
by this result. No TTA fallback, sample-specific selector or promotion follows.

The prior aggregate gain, failed quality gates and zero division true positives
remain unchanged. This run did not access Kaggle or verify current selections;
the historical V28 public score remains a prior result, not a new observation.

## Evidence

- [Approved freeze](v30_freeze_approved_20260928.json) and
  [execution log](V30_EXECUTION.md).
- [Terminal receipt](outputs/v30_execution_20260928/finished.json),
  [complete machine result](outputs/v30_execution_20260928/result.json), and
  [all-sample report and focus links](outputs/v30_execution_20260928/REPORT.md).
- [Independent verification](outputs/v30_execution_20260928/independent_verification.json)
  and [derived readout](outputs/v30_execution_20260928/descriptive_readout.json).
- [Worst-loss summary](outputs/v30_execution_20260928/rows/44b6_40c45f5a.json)
  and [protected-loss summary](outputs/v30_execution_20260928/rows/6bba_76db78c1.json).

The independent check hashes inputs and saved outputs and recomputes output
accounting/signatures. It does not rerun matching, linking or GT evaluation and
does not confer causal or biological validity. No commit or push was performed.
