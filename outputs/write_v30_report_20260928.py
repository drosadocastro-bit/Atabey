"""Summarize completed, verified V30 output; no new matching, replay or scoring."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v30_execution_20260928'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    audit = read(OUT / 'independent_verification.json')
    assert audit['status'] == 'COMPLETE_EVIDENCE_VERIFIED'
    assert not (OUT / 'failure.json').exists() and not (OUT / 'independent_verification_failure.json').exists()
    result = read(OUT / 'result.json')
    proposal = read(ROOT / 'v30_diagnostic_proposal_20260928.json')
    rows = result['rows']
    by_id = {r['sample_id']: r for r in rows}
    totals = {arm: dict(sum((Counter(r['coordinate_counts'][arm]) for r in rows), Counter())) for arm in ('baseline', 'tta')}
    stages = {arm: {stage: {k: sum(r['stages'][arm][stage][k] for r in rows) for k in ('nodes', 'edges')} for stage in ('RAW', 'P2', 'P3')} for arm in ('baseline', 'tta')}
    losses = [by_id[sid] for sid in proposal['focus_loss_ids']]
    loss_stats = {'count': len(losses), 'edge_jaccard_worse': sum(r['official_metrics']['delta']['edge_jaccard'] < 0 for r in losses),
                  'node_adjustment_improved': sum(r['official_metrics']['node_adjustment_residual']['delta'] > 0 for r in losses),
                  'pruning_disabled': sum(not r['pruning_enabled'] for r in losses),
                  'node_recall_improved': sum(r['official_metrics']['delta']['node_recall'] > 0 for r in losses),
                  'node_recall_unchanged': sum(r['official_metrics']['delta']['node_recall'] == 0 for r in losses),
                  'node_recall_worse': sum(r['official_metrics']['delta']['node_recall'] < 0 for r in losses)}
    assert (loss_stats['count'], loss_stats['edge_jaccard_worse'], loss_stats['node_adjustment_improved'], loss_stats['pruning_disabled']) == (25, 25, 24, 19)
    views = {}
    for name in ('EXACT_ONLY', 'EXACT_PLUS_NEAR'):
        history, outgoing = Counter(), Counter()
        edges = {stage: dict(sum((Counter({k: v for k, v in r['views'][name]['edges'][stage].items() if k != 'max_absolute_confidence_difference'}) for r in rows), Counter())) for stage in ('RAW', 'P2', 'P3')}
        for r in rows:
            for h in r['views'][name]['history_cross_tab']:
                history[h['recursive_history']] += h['count']
                outgoing[h['outgoing']] += h['count']
        views[name] = {'history': dict(history), 'outgoing': dict(outgoing), 'edges': edges}
    derived = {'status': 'DESCRIPTIVE_READOUT_FROM_VERIFIED_OUTPUT',
               'source_result_sha256': hashlib.sha256((OUT / 'result.json').read_bytes()).hexdigest(),
               'source_verification_sha256': hashlib.sha256((OUT / 'independent_verification.json').read_bytes()).hexdigest(),
               'coordinate_counts': totals, 'stage_totals': stages, 'strong_loss_context': loss_stats, 'views': views,
               'new_scoring_performed': False, 'causal_attribution': False}
    with (OUT / 'descriptive_readout.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(derived, f, sort_keys=True, indent=2); f.write('\n')
    text = '''# V30 results: valid descriptive diagnostic

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
'''
    for label in ('EXACT', 'NEAR_ISOLATED', 'NO_NEAR_COUNTERPART', 'NEAR_AMBIGUOUS', 'DUPLICATE_AMBIGUOUS'):
        text += f"| {label} | {totals['baseline'].get(label, 0):,} | {totals['tta'].get(label, 0):,} |\n"
    text += '''
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
'''
    for field in ('common', 'baseline_only', 'tta_only', 'confidence_only_changes', 'baseline_unmapped_endpoint', 'tta_unmapped_endpoint'):
        text += f"| {field} | {views['EXACT_ONLY']['edges']['RAW'][field]:,} | {views['EXACT_PLUS_NEAR']['edges']['RAW'][field]:,} |\n"
    text += '''
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
'''
    for arm, s in stages.items():
        text += f"| {arm} | {s['RAW']['nodes']:,} | {s['P2']['nodes']:,} | {s['P3']['nodes']:,} | {s['RAW']['edges']:,} | {s['P3']['edges']:,} |\n"
    text += '''
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
'''
    for name, group in result['groups'].items():
        text += f"| {name} | {group['count']} | {group['coordinate_denominators']['baseline']:,} | {group['coordinate_denominators']['tta']:,} | {group['coordinate_counts']['baseline'].get('EXACT', 0):,} |\n"
    text += '''
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
'''
    with (ROOT / 'V30_RESULTS.md').open('x', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('Wrote V30_RESULTS.md and descriptive_readout.json from verified completed output.')


if __name__ == '__main__':
    main()
