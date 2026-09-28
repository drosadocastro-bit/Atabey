"""Read-only independent accounting of V30 evidence; no graph replay or GT scoring."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v30_execution_20260928'
sys.path.insert(0, str(ROOT / 'scripts'))
from run_v30_diagnostic import artifact, load, save, preflight, validate_receipt, verify_candidate


def need(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    candidate = ROOT / 'v30_implementation_candidate_20260928.json'
    receipt = ROOT / 'v30_freeze_approved_20260928.json'
    audit = {'audited_at_utc': datetime.now(timezone.utc).isoformat(),
             'new_graph_replay_performed': False, 'new_scoring_performed': False}
    try:
        need(not (OUT / 'failure.json').exists() and not (OUT / 'worker_failure.json').exists(), 'Terminal failure exists')
        finished = load(OUT / 'finished.json')
        need(finished['status'] == 'COMPLETE_DESCRIPTIVE_DIAGNOSTIC' and finished['wall_seconds'] < 7200, 'Completion/budget failed')
        for key in ('result', 'report'):
            artifact(OUT, finished[key])
        verify_candidate(ROOT, candidate)
        validate_receipt(load(receipt), candidate, OUT)
        proposal = load(ROOT / 'v30_diagnostic_proposal_20260928.json')
        identities, original = preflight(ROOT, proposal)
        result = load(OUT / 'result.json')
        need(result['status'] == finished['status'], 'Status mismatch')
        for key, path in [('candidate_sha256', candidate), ('receipt_sha256', receipt)]:
            need(hashlib.sha256(path.read_bytes()).hexdigest() == result[key], 'Binding mismatch')
        ids = proposal['sample_order']
        need(result['completed_ids'] == ids and [r['sample_id'] for r in result['rows']] == ids, 'Coverage mismatch')
        need(sorted(p.stem for p in (OUT / 'rows').glob('*.json')) == ids, 'Row file coverage mismatch')
        need(sorted(p.name.removesuffix('.json.gz') for p in (OUT / 'samples').glob('*.json.gz')) == ids, 'Detail file coverage mismatch')
        need(result['existing_official_aggregates'] == original['summaries'] and result['existing_official_strata'] == original['strata'], 'Official aggregates changed')
        need(result['v29a_decision_unchanged'] == original['decision'], 'V29A decision changed')
        originals = {r['sample_id']: r for r in original['rows']}
        checked_stages = checked_views = 0
        group_counts = {key: {arm: Counter() for arm in ('baseline', 'tta')} for key in result['groups']}
        for row in result['rows']:
            sid = row['sample_id']
            need(load(OUT / 'rows' / (sid + '.json')) == row, 'Summary row mismatch')
            with gzip.open(artifact(OUT, row['detail']), 'rt', encoding='utf-8') as stream:
                detail = json.load(stream)
            need(detail['sample_id'] == sid, 'Detail sample mismatch')
            need(detail['existing_official_metrics'] == row['official_metrics'], 'Metric context mismatch')
            for arm in ('baseline', 'tta'):
                need(row['official_metrics'][arm] == originals[sid][arm], 'Original official metrics changed')
            for field, delta in row['official_metrics']['delta'].items():
                a, b = originals[sid]['baseline'][field], originals[sid]['tta'][field]
                need(delta == (None if a is None or b is None else b - a), 'Metric arithmetic mismatch')
            nodes_by_arm, stages_by_arm = {}, {}
            for arm in ('baseline', 'tta'):
                entries = detail['correspondence']['nodes'][arm]
                nodes = {n['node_id']: n for n in entries}
                need(len(nodes) == len(entries), 'Duplicate output node ID')
                nodes_by_arm[arm] = nodes
                counts = Counter(n['label'] for n in entries)
                need(dict(counts) == row['coordinate_counts'][arm], 'Coordinate accounting mismatch')
                for group_name, group in result['groups'].items():
                    if sid in group['sample_ids']:
                        group_counts[group_name][arm].update(counts)
                frame_counts = Counter(n['coordinate_tzyx'][0] for n in entries)
                frame_labels = Counter((n['coordinate_tzyx'][0], n['label']) for n in entries)
                for frame in detail['correspondence']['frames']:
                    observed = frame[arm]
                    need(observed['denominator'] == frame_counts[frame['t']], 'Frame denominator mismatch')
                    need(sum(observed['counts'].values()) == observed['denominator'], 'Frame labels incomplete')
                    for label, count in observed['counts'].items():
                        expected = frame_labels[(frame['t'], label)]
                        need(expected == count, 'Frame category mismatch')
                        need(observed['fractions'][label] == (count / observed['denominator'] if observed['denominator'] else None), 'Frame fraction mismatch')
                remaining = list(nodes)
                edges = [tuple(e) for e in detail['raw_edges'][arm]]
                previous_removed = set()
                stages_by_arm[arm] = {}
                for stage in ('RAW', 'P2', 'P3'):
                    info = detail['stages'][arm][stage]
                    removed = set(info['removed_node_ids'])
                    need(not removed & previous_removed and removed <= set(remaining), 'Invalid node removal')
                    need(all(nodes[k]['first_removal_stage'] == stage for k in removed), 'Removal label mismatch')
                    previous_removed.update(removed)
                    remaining = [k for k in remaining if k not in removed]
                    remaining_set = set(remaining)
                    dropped_edges = [[e[0], e[1]] for e in edges if e[0] not in remaining_set or e[1] not in remaining_set]
                    need(dropped_edges == info['removed_edges'], 'Edge removal accounting mismatch')
                    edges = [e for e in edges if e[0] in remaining_set and e[1] in remaining_set]
                    need(len(remaining) == info['nodes'] and len(edges) == info['edges'], 'Stage size mismatch')
                    representation = (tuple((nid, *nodes[nid]['coordinate_tzyx']) for nid in remaining), tuple(edges))
                    need(hashlib.sha256(repr(representation).encode()).hexdigest() == info['signature'], 'Serialized stage signature mismatch')
                    stages_by_arm[arm][stage] = edges
                    checked_stages += 1
                expected = proposal['samples'][sid]['arms'][arm]['expected_final_signature']
                need(detail['stages'][arm]['P3']['signature'] == expected, 'Final signature mismatch')
                need(all(nodes[k]['first_removal_stage'] == 'SURVIVES' for k in remaining), 'Survivor label mismatch')
            for view, accepted in [('EXACT_ONLY', {'EXACT'}), ('EXACT_PLUS_NEAR', {'EXACT', 'NEAR_ISOLATED'})]:
                pairs = {nid: n['counterpart_id'] for nid, n in nodes_by_arm['baseline'].items() if n['label'] in accepted}
                inverse = {v: k for k, v in pairs.items()}
                need(len(inverse) == len(pairs), 'Mapping not one-to-one')
                for b, t in pairs.items():
                    left, right = nodes_by_arm['baseline'][b], nodes_by_arm['tta'][t]
                    need(right['counterpart_id'] == b and left['label'] == right['label'], 'Mapping is not reciprocal')
                    need(left['coordinate_tzyx'][0] == right['coordinate_tzyx'][0], 'Mapping crosses frames')
                    if left['label'] == 'EXACT':
                        need(left['coordinate_tzyx'] == right['coordinate_tzyx'], 'Exact anchor moved')
                    else:
                        need(left['eligible_neighborhood_degree'] == right['eligible_neighborhood_degree'] == 1, 'Nonisolated near pair')
                        need(0 < left['displacement_um'] <= 2.0, 'Near displacement out of bounds')
                view_data = detail['views'][view]
                need(len(pairs) == view_data['mapped_pairs'], 'View mapping coverage mismatch')
                for stage in ('RAW', 'P2', 'P3'):
                    mapped = []
                    for arm, mapping in [('baseline', {k: k for k in pairs}), ('tta', inverse)]:
                        subset = {(mapping[e[0]], mapping[e[1]]): e for e in stages_by_arm[arm][stage] if e[0] in mapping and e[1] in mapping}
                        mapped.append(subset)
                    common = set(mapped[0]) & set(mapped[1])
                    expected = view_data['edges'][stage]
                    need(expected['common'] == len(common), 'Common edges mismatch')
                    for idx, arm in enumerate(('baseline', 'tta')):
                        only = sorted(set(mapped[idx]) - common)
                        need(expected[arm + '_only'] == len(only), 'Changed association count mismatch')
                        need(expected[arm]['only_endpoint_pairs'] == [list(e) for e in only], 'Changed association rows mismatch')
                        need(expected[arm]['total'] == len(stages_by_arm[arm][stage]), 'Edge denominator mismatch')
                        need(expected[arm]['unmapped_endpoint'] + len(mapped[idx]) == expected[arm]['total'], 'Unmapped edge partition mismatch')
                    relation = [list(k) for k in sorted(common) if mapped[0][k][3] != mapped[1][k][3]]
                    confidence = [[*k, mapped[0][k][2], mapped[1][k][2]] for k in sorted(common) if mapped[0][k][3] == mapped[1][k][3] and mapped[0][k][2] != mapped[1][k][2]]
                    need(expected['relation_changes'] == relation and expected['confidence_only_changes'] == confidence, 'Attribute-only changes mismatch')
                    checked_views += 1
                history = view_data['raw_history']
                need(len(history['rows']) == len(pairs), 'History coverage mismatch')
                cross = Counter((r['outgoing'], r['immediate_history'], r['recursive_history']) for r in history['rows'])
                expected_cross = Counter({(r['outgoing'], r['immediate_history'], r['recursive_history']): r['count'] for r in history['cross_tab']})
                need(cross == expected_cross, 'History cross-tab mismatch')
                pruning = Counter((nodes_by_arm['baseline'][k]['first_removal_stage'], nodes_by_arm['tta'][v]['first_removal_stage']) for k, v in pairs.items())
                need(pruning == Counter({(r['baseline'], r['tta']): r['count'] for r in view_data['pruning']['cross_tab']}), 'Pruning cross-tab mismatch')
        for group_name, arms in group_counts.items():
            for arm, counts in arms.items():
                need(dict(sorted(counts.items())) == result['groups'][group_name]['coordinate_counts'][arm], 'Group counts mismatch')
                need(sum(counts.values()) == result['groups'][group_name]['coordinate_denominators'][arm], 'Group denominator mismatch')
        need(sum(r['final_graph_export_parities'] for r in result['rows']) == 398, 'Incomplete export parity receipts')
        audit.update(status='COMPLETE_EVIDENCE_VERIFIED', paired_samples=199,
                     final_graph_export_parity_receipts=398, serialized_stage_signatures_verified=checked_stages,
                     edge_view_partitions_verified=checked_views, official_metric_copies_unchanged=True,
                     input_identity_audit=identities, finished_sha256=hashlib.sha256((OUT/'finished.json').read_bytes()).hexdigest(),
                     audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     limits=['No second graph reconstruction or export', 'No new GT scoring',
                             'Checks output accounting; does not independently rerun correspondence or causal mechanisms'])
        save(OUT / 'independent_verification.json', audit)
        print(json.dumps({k: audit[k] for k in ('status', 'paired_samples', 'serialized_stage_signatures_verified', 'edge_view_partitions_verified')}))
    except Exception as exc:
        audit.update(status='VERIFICATION_FAILED', error_type=type(exc).__name__, error=str(exc))
        save(OUT / 'independent_verification_failure.json', audit)
        raise


if __name__ == '__main__':
    main()
