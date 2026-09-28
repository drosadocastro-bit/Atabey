"""V27C evaluation instrumentation; correspondence is not biological identity."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import warnings

from atabey.evaluation.official_division_metric import (
    _ground_truth_to_tracksdata, _official_modules, _prediction_to_tracksdata,
)
from atabey.evaluation.official_tracking_metric import (
    OfficialTrackingResult, summarize_official_tracking,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def validate_graph(graph):
    nodes = {d.node_id: d for d in graph.detections}
    edges = {(e.source_id, e.target_id) for e in graph.edges}
    check(len(nodes) == len(graph.detections), 'Duplicate prediction node')
    check(len(edges) == len(graph.edges), 'Duplicate prediction edge')
    check(all(d.sample_id == graph.sample_id for d in nodes.values()), 'Prediction sample mismatch')
    check(all(type(d.t) is int and all(math.isfinite(v) for v in
              (d.z, d.y, d.x, d.z_um, d.y_um, d.x_um)) for d in nodes.values()),
          'Invalid prediction time/coordinates')
    for edge in graph.edges:
        check(edge.source_id in nodes and edge.target_id in nodes, 'Missing prediction endpoint')
        check(nodes[edge.target_id].t == nodes[edge.source_id].t + 1, 'Nonadjacent prediction edge')
        check(edge.confidence is None or math.isfinite(edge.confidence), 'Nonfinite confidence')


def decode_graph(payload, sample_id, expected_digest):
    check(payload['sample_id'] == sample_id, 'Saved graph sample mismatch')
    check(digest(payload) == expected_digest, 'Saved graph digest mismatch')
    graph = LineageGraph(payload['sample_id'], [Detection(**n) for n in payload['detections']],
                         [LineageEdge(**e) for e in payload['edges']])
    check(digest(asdict(graph)) == expected_digest, 'Graph decoding changed attributes/order')
    validate_graph(graph)
    return graph


class EvaluationFailure(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


def finite(value):
    return float(value) if math.isfinite(float(value)) else None


def evaluate_graph(graph, gt):
    """One fresh host evaluation; metrics and edge ledger share matched state."""
    evidence = {'sample_id': graph.sample_id}
    before = digest(asdict(graph)), digest(asdict(gt))
    caught = []
    try:
        validate_graph(graph)
        check(gt.sample_id == graph.sample_id, 'GT sample mismatch')
        estimate = gt.estimated_number_of_nodes
        check(type(estimate) is int and estimate > 0, 'Invalid estimated node count')
        gt_nodes = {n.node_id: n for n in gt.nodes}
        gt_edges = set(gt.edges)
        check(len(gt_nodes) == len(gt.nodes) and len(gt_edges) == len(gt.edges), 'Duplicate GT identity')
        check(all(s in gt_nodes and t in gt_nodes for s, t in gt_edges), 'Missing GT endpoint')
        check(all(type(n.t) is int and all(math.isfinite(v) for v in n.position_um)
                  for n in gt.nodes), 'Invalid GT coordinates/time')
        pl, td, _ = _official_modules()
        from tracking_cellmot.metrics import evaluate, _evaluate_matched_graph, node_recall, per_sample_metrics

        prediction, pids = _prediction_to_tracksdata(graph, pl, td)
        reference, gids = _ground_truth_to_tracksdata(gt, pl, td)
        reverse_p = {v: k for k, v in pids.items()}
        reverse_g = {v: k for k, v in gids.items()}
        keys = td.DEFAULT_ATTR_KEYS
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            official = evaluate(prediction, reference, scale=None, max_distance=7.0)
            recall = (float(node_recall(prediction, reference)) if
                      prediction.num_edges() and prediction.num_nodes() and reference.num_nodes() else float('nan'))
            derived = per_sample_metrics(official, float(estimate), recall)
            table = (_evaluate_matched_graph(prediction, reference).to_dicts()
                     if prediction.num_edges() else [])
        division_den = official.division_tp + official.division_fp + official.division_fn
        edge_den = official.edge_tp + official.edge_fp + official.edge_fn
        division = official.division_tp / division_den if division_den else None
        adjusted = finite(derived['adj_edge_jaccard'])
        metrics = asdict(OfficialTrackingResult(
            edge_tp=int(official.edge_tp), edge_fp=int(official.edge_fp), edge_fn=int(official.edge_fn),
            edge_jaccard=finite(derived['edge_jaccard']), adjusted_edge_jaccard=adjusted,
            node_recall=finite(derived['node_recall']), predicted_nodes=int(official.num_pred_nodes),
            estimated_total_nodes=estimate, total_node_ratio=finite(derived['total_node_ratio']),
            division_tp=int(official.division_tp), division_fp=int(official.division_fp),
            division_fn=int(official.division_fn), division_jaccard=division,
            score=adjusted + .1 * division if adjusted is not None and division is not None else adjusted))
        evidence.update(metrics=metrics, denominators={'edge': int(edge_den), 'division': int(division_den),
                        'GT_nodes': len(gt.nodes), 'estimated_nodes': estimate}, undefined={})
        for key, value in metrics.items():
            if value is None:
                evidence['undefined'][key] = ('zero_division_denominator' if key == 'division_jaccard'
                                              else 'host_undefined_metric')

        mappings = {d.node_id: None for d in graph.detections}
        if keys.MATCHED_NODE_ID in prediction.node_attr_keys():
            for row in prediction.node_attrs(attr_keys=[keys.NODE_ID, keys.MATCHED_NODE_ID]).to_dicts():
                matched = row[keys.MATCHED_NODE_ID]
                mappings[reverse_p[int(row[keys.NODE_ID])]] = (
                    None if matched is None or int(matched) == -1 else reverse_g[int(matched)])
        post = {(reverse_p[int(r[keys.EDGE_SOURCE])], reverse_p[int(r[keys.EDGE_TARGET])]): r for r in table}
        check(len(post) == len(table), 'Duplicate host table edge')
        raw = {(reverse_p[int(r[keys.EDGE_SOURCE])], reverse_p[int(r[keys.EDGE_TARGET])]): r
               for r in prediction.edge_attrs(attr_keys=[keys.EDGE_ID]).to_dicts()} if graph.edges else {}
        check(set(post) <= set(raw), 'Host returned unknown prediction edge')
        ledger, credited = [], []
        for edge in graph.edges:
            pair = (edge.source_id, edge.target_id)
            row = post.get(pair)
            matched = bool(row[keys.MATCHED_EDGE_MASK]) if row is not None else None
            valid = bool(row['pred_valid']) if row is not None else None
            check(not matched or valid, 'Matched edge is outside official evaluability')
            category = ('FILTERED_BY_HOST' if row is None else 'OFFICIAL_TP' if matched else
                        'OFFICIAL_FP' if valid else 'UNEVALUATED_BY_SPARSE_GT')
            mapped = [mappings[edge.source_id], mappings[edge.target_id]]
            if matched:
                check(tuple(mapped) in gt_edges, 'Host credit is not a GT edge')
                credited.append(tuple(mapped))
            ledger.append({'source_id': edge.source_id, 'target_id': edge.target_id,
                           'attributes': asdict(edge), 'mapped_gt_endpoints': mapped,
                           'host_edge_id': int(raw[pair][keys.EDGE_ID]), 'host_table_membership': row is not None,
                           'matched_edge_mask': matched, 'pred_valid': valid, 'category': category})
        counts = Counter(row['category'] for row in ledger)
        check(len(ledger) == len(graph.edges), 'Input edge partition incomplete')
        check(len(credited) == len(set(credited)), 'Duplicate credited GT edge')
        check(counts['OFFICIAL_TP'] == official.edge_tp and counts['OFFICIAL_FP'] == official.edge_fp,
              'Ledger TP/FP disagrees with host')
        check(len(gt_edges - set(credited)) == official.edge_fn, 'Ledger FN disagrees with host')
        evidence.update(nodes=[{'node_id': d.node_id, 'gt_node_id': mappings[d.node_id], 'attributes': asdict(d)}
                               for d in sorted(graph.detections, key=lambda n: n.node_id)],
                        edges=sorted(ledger, key=lambda r: (r['source_id'], r['target_id'])),
                        credited_gt_edges=[list(e) for e in sorted(credited)],
                        missed_gt_edges=[list(e) for e in sorted(gt_edges - set(credited))],
                        category_counts={k: counts[k] for k in ('OFFICIAL_TP', 'OFFICIAL_FP',
                                        'UNEVALUATED_BY_SPARSE_GT', 'FILTERED_BY_HOST')})
        check(metrics['edge_jaccard'] is not None and adjusted is not None, 'Undefined primary metric')
        check(before == (digest(asdict(graph)), digest(asdict(gt))), 'Evaluation mutated input')
    except Exception as exc:
        evidence['warnings'] = [{'category': w.category.__name__, 'message': str(w.message)} for w in caught]
        evidence['input_mutated'] = before != (digest(asdict(graph)), digest(asdict(gt)))
        raise EvaluationFailure(str(exc), evidence) from exc
    evidence['warnings'] = [{'category': w.category.__name__, 'message': str(w.message)} for w in caught]
    return evidence


def metric_delta(before, after):
    check(set(before) == set(after), 'Metric schema mismatch')
    return {k: None if before[k] is None or after[k] is None else after[k] - before[k] for k in before}


def compare_records(before, after, *, pruning=False):
    check(before['sample_id'] == after['sample_id'], 'Contrast sample mismatch')
    old = {(e['source_id'], e['target_id']): e for e in before['edges']}
    new = {(e['source_id'], e['target_id']): e for e in after['edges']}
    old_nodes = {n['node_id']: n for n in before['nodes']}
    new_nodes = {n['node_id']: n for n in after['nodes']}
    if pruning:
        check(new.keys() <= old.keys() and new_nodes.keys() <= old_nodes.keys(), 'Pruning subset violated')
        check(all(e['attributes'] == old[k]['attributes'] for k, e in new.items()), 'Pruning changed edge attributes')
        check(all(n['attributes'] == old_nodes[k]['attributes'] for k, n in new_nodes.items()), 'Pruning changed node attributes')
    a, b = set(map(tuple, before['credited_gt_edges'])), set(map(tuple, after['credited_gt_edges']))
    delta = metric_delta(before['metrics'], after['metrics'])
    check(len(b - a) - len(a - b) == delta['edge_tp'], 'Credited-set delta mismatch')
    check(delta['edge_fn'] == -delta['edge_tp'], 'FN delta mismatch')
    transitions, rows = Counter(), []
    added_fp = removed_fp = 0
    for pair in sorted(old.keys() | new.keys()):
        x, y = old.get(pair), new.get(pair)
        ca, cb = x['category'] if x else 'ABSENT', y['category'] if y else 'ABSENT'
        transitions[f'{ca}->{cb}'] += 1
        added_fp += cb == 'OFFICIAL_FP' and ca != 'OFFICIAL_FP'
        removed_fp += ca == 'OFFICIAL_FP' and cb != 'OFFICIAL_FP'
        rows.append({'source_id': pair[0], 'target_id': pair[1], 'before': x, 'after': y,
                     'before_category': ca, 'after_category': cb,
                     'deleted_endpoints': [n for n in pair if n not in new_nodes],
                     'mapping_changed': bool(x and y and x['mapped_gt_endpoints'] != y['mapped_gt_endpoints']),
                     'confidence_only_changed': bool(x and y and x['attributes']['confidence'] != y['attributes']['confidence']
                        and {k:v for k,v in x['attributes'].items() if k != 'confidence'} ==
                            {k:v for k,v in y['attributes'].items() if k != 'confidence'})})
    check(added_fp - removed_fp == delta['edge_fp'], 'FP transition delta mismatch')
    counts = {'added_edges': len(new.keys() - old.keys()), 'removed_edges': len(old.keys() - new.keys()),
              'newly_penalized_FP': added_fp, 'relieved_FP': removed_fp,
              'gained_GT_credit': len(b - a), 'lost_GT_credit': len(a - b), 'shared_GT_credit': len(a & b),
              'survivor_mapping_changed': sum(r['mapping_changed'] for r in rows),
              'survivor_category_changed': sum(bool(r['before'] and r['after']) and
                                              r['before_category'] != r['after_category'] for r in rows),
              'confidence_only_changed': sum(r['confidence_only_changed'] for r in rows)}
    return {'sample_id': before['sample_id'], 'metric_delta': delta, 'counts': counts,
            'category_transitions': dict(sorted(transitions.items())), 'edge_union': rows,
            'gained_gt_edges': sorted(b - a), 'lost_gt_edges': sorted(a - b), 'shared_gt_edges': sorted(a & b),
            'deleted_node_ids': sorted(old_nodes.keys() - new_nodes.keys()),
            'added_node_ids': sorted(new_nodes.keys() - old_nodes.keys()),
            'shared_node_mapping_changes': [{'node_id': n, 'before': old_nodes[n]['gt_node_id'], 'after': new_nodes[n]['gt_node_id']}
                                           for n in sorted(old_nodes.keys() & new_nodes.keys())
                                           if old_nodes[n]['gt_node_id'] != new_nodes[n]['gt_node_id']]}


def summarize_records(rows, expected_count):
    check(len(rows) == expected_count, 'Incomplete summary cohort')
    check(len({r['sample_id'] for r in rows}) == expected_count, 'Duplicate summary sample')
    check(all(r['metrics']['edge_jaccard'] is not None and r['metrics']['adjusted_edge_jaccard'] is not None
              for r in rows), 'Undefined primary summary metric')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        summary = asdict(summarize_official_tracking([OfficialTrackingResult(**r['metrics']) for r in rows]))
    check(summary['sample_count'] == expected_count and summary['adjusted_sample_count'] == expected_count,
          'Host summary silently dropped rows')
    return {'metrics': summary, 'warnings': [{'category': w.category.__name__, 'message': str(w.message)} for w in caught]}


def interaction(by_arm):
    return {key: (None if any(by_arm[a][key] is None for a in ('S1','S0','M1','M0')) else
                  (by_arm['S1'][key] - by_arm['S0'][key]) - (by_arm['M1'][key] - by_arm['M0'][key]))
            for key in by_arm['M0']}


def verify_historical(actual, expected):
    check(set(actual) == set(expected), 'Historical metric schema mismatch')
    for key, value in expected.items():
        got = actual[key]
        if value is None or got is None:
            check(value is got, f'Historical null mismatch: {key}')
        elif type(value) is int:
            check(type(got) is int and got == value, f'Historical integer mismatch: {key}')
        else:
            check(math.isfinite(got) and math.isclose(got, value, abs_tol=1e-12, rel_tol=0),
                  f'Historical metric mismatch: {key}')
