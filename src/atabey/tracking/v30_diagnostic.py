"""Descriptive geometry/graph comparisons; correspondence is not cell identity.

Only saved detections and existing graph builders are used. This module neither
scores ground truth nor implements a new tracking policy.
"""
from collections import Counter, defaultdict
import math

import numpy as np
from scipy.spatial import cKDTree

from atabey.submission.v28 import export_graph, require, signature
from atabey.tracking.unet_graph import relink_predictor_detections
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments

LABELS = ('EXACT', 'NEAR_ISOLATED', 'NO_NEAR_COUNTERPART',
          'NEAR_AMBIGUOUS', 'DUPLICATE_AMBIGUOUS')
STAGES = ('RAW', 'P2', 'P3')


def validate_coordinates(coordinates, shape):
    a = np.asarray(coordinates)
    require(a.ndim == 2 and a.shape[1] == 4, 'Expected N-by-4 coordinates')
    require(a.dtype.kind in 'iuf' and np.isfinite(a).all(), 'Nonfinite/nonnumeric coordinates')
    require(len(shape) == 4 and all(int(v) == v and v > 0 for v in shape), 'Invalid shape')
    require(np.all(a >= 0) and np.all(a < np.asarray(shape)), 'Coordinate out of bounds')
    require(np.all(a[:, 0] == np.floor(a[:, 0])), 'Nonintegral time')
    require(np.all(a[1:, 0] >= a[:-1, 0]), 'Time order changed')


def graph_index(graph):
    nodes = {n.node_id: n for n in graph.detections}
    require(len(nodes) == len(graph.detections), 'Duplicate node ID')
    incoming, outgoing = {}, {}
    for e in graph.edges:
        require(e.source_id in nodes and e.target_id in nodes, 'Missing edge endpoint')
        require(nodes[e.target_id].t == nodes[e.source_id].t + 1, 'Nonadjacent edge')
        require(e.source_id not in outgoing and e.target_id not in incoming,
                'Unexpected branching, merging or duplicate edge')
        require(e.relation == 'continuation', 'Unexpected relation in fixed linker')
        require(e.confidence is not None and math.isfinite(e.confidence), 'Invalid confidence')
        incoming[e.target_id] = e.source_id
        outgoing[e.source_id] = e.target_id
    depth = {}
    for n in sorted(graph.detections, key=lambda n: n.t):
        depth[n.node_id] = 0 if n.node_id not in incoming else depth[incoming[n.node_id]] + 1
    return nodes, incoming, outgoing, depth


def edge_rows(graph):
    return [[e.source_id, e.target_id, e.confidence, e.relation] for e in graph.edges]


def reconstruct(sample_id, coordinates, shape, pruning, record):
    validate_coordinates(coordinates, shape)
    require(record['sample_id'] == sample_id and record['shape'] == list(shape), 'Record metadata mismatch')
    require(record['route']['apply_pruning'] is pruning, 'Record route mismatch')
    raw = relink_predictor_detections(sample_id, coordinates)
    graph_index(raw)
    require(len(raw.detections) == record['raw_nodes'] and len(raw.edges) == record['raw_edges'], 'RAW parity failed')
    p2 = prune_interior_isolated_detections(raw) if pruning else raw
    p3 = prune_interior_short_fragments(p2) if pruning else p2
    stages = dict(zip(STAGES, (raw, p2, p3)))
    _, exported = export_graph(p3, shape, 0)
    require(all(record[k] == v for k, v in exported.items()), 'FINAL graph/export parity failed')
    removal = {n.node_id: 'SURVIVES' for n in raw.detections}
    stage_rows = {}
    previous = raw
    for name, graph in stages.items():
        nodes, _, _, _ = graph_index(graph)
        old_nodes = {n.node_id: n for n in previous.detections}
        old_edges = {(e.source_id, e.target_id): e for e in previous.edges}
        edges = {(e.source_id, e.target_id): e for e in graph.edges}
        require(all(nid in old_nodes and n == old_nodes[nid] for nid, n in nodes.items()), 'Pruning changed/added a node')
        require(all(key in old_edges and e == old_edges[key] for key, e in edges.items()), 'Pruning changed/added an edge')
        removed = [n.node_id for n in previous.detections if n.node_id not in nodes]
        removed_edges = [list(key) for key in old_edges if key not in edges]
        require(len(nodes) + len(removed) == len(old_nodes), 'Node removal accounting failed')
        require(len(edges) + len(removed_edges) == len(old_edges), 'Edge removal accounting failed')
        for nid in removed:
            removal[nid] = name
        stage_rows[name] = {'status': 'BYPASSED' if name != 'RAW' and not pruning else 'EXECUTED',
                            'nodes': len(nodes), 'edges': len(edges), 'signature': signature(graph),
                            'removed_node_ids': removed, 'removed_edges': removed_edges}
        previous = graph
    require(sum(Counter(removal.values()).values()) == len(raw.detections), 'Removal coverage failed')
    return stages, removal, stage_rows


def correspondence(baseline, tta):
    graphs = (baseline, tta)
    by_key = []
    for graph in graphs:
        lookup = defaultdict(list)
        for n in graph.detections:
            lookup[(n.t, n.z, n.y, n.x)].append(n)
        by_key.append(lookup)
    duplicate_keys = {key for lookup in by_key for key, nodes in lookup.items() if len(nodes) > 1}
    records, frames = [{}, {}], [defaultdict(list), defaultdict(list)]
    frame_records = [defaultdict(list), defaultdict(list)]
    exact, near = {}, {}
    for arm, graph in enumerate(graphs):
        for n in graph.detections:
            key = (n.t, n.z, n.y, n.x)
            records[arm][n.node_id] = {'node_id': n.node_id, 'coordinate_tzyx': list(key),
                                      'label': 'DUPLICATE_AMBIGUOUS' if key in duplicate_keys else None,
                                      'counterpart_id': None, 'eligible_neighborhood_degree': None,
                                      'displacement_um': None}
            frame_records[arm][n.t].append(records[arm][n.node_id])
            if key not in duplicate_keys:
                frames[arm][n.t].append(n)
    for key in sorted(set(by_key[0]) & set(by_key[1]) - duplicate_keys):
        b, t = by_key[0][key][0], by_key[1][key][0]
        exact[b.node_id] = t.node_id
        for arm, node, other in [(0, b, t), (1, t, b)]:
            records[arm][node.node_id].update(label='EXACT', counterpart_id=other.node_id, displacement_um=0.0)
    frame_rows, distances = [], []
    for frame in sorted(set(frames[0]) | set(frames[1]) | {n.t for g in graphs for n in g.detections}):
        left, right = frames[0][frame], frames[1][frame]
        neighbors = [[] for _ in left]
        degrees_right = [0] * len(right)
        if left and right:
            positions = np.asarray([n.position_um for n in right], dtype=np.float64)
            tree = cKDTree(positions)
            for i, n in enumerate(left):
                point = np.asarray(n.position_um, dtype=np.float64)
                # Expand retrieval by one ULP, then apply the exact squared-distance rule.
                for j in sorted(tree.query_ball_point(point, np.nextafter(2.0, np.inf))):
                    delta = positions[j] - point
                    if float(np.dot(delta, delta)) <= 4.0:
                        neighbors[i].append(j)
                        degrees_right[j] += 1
        for i, n in enumerate(left):
            records[0][n.node_id]['eligible_neighborhood_degree'] = len(neighbors[i])
        for j, n in enumerate(right):
            records[1][n.node_id]['eligible_neighborhood_degree'] = degrees_right[j]
        for i, js in enumerate(neighbors):
            if len(js) != 1 or degrees_right[js[0]] != 1:
                continue
            b, t = left[i], right[js[0]]
            if records[0][b.node_id]['label'] == 'EXACT' or records[1][t.node_id]['label'] == 'EXACT':
                continue
            distance = float(np.linalg.norm(np.asarray(b.position_um) - np.asarray(t.position_um)))
            near[b.node_id] = t.node_id
            distances.append(distance)
            for arm, node, other in [(0, b, t), (1, t, b)]:
                records[arm][node.node_id].update(label='NEAR_ISOLATED', counterpart_id=other.node_id, displacement_um=distance)
        row = {'t': frame}
        for arm, label in enumerate(('baseline', 'tta')):
            # Frame output includes duplicates, although they were excluded from neighborhoods.
            selected = frame_records[arm][frame]
            for r in selected:
                if r['label'] is None:
                    r['label'] = 'NO_NEAR_COUNTERPART' if r['eligible_neighborhood_degree'] == 0 else 'NEAR_AMBIGUOUS'
            counts = {key: sum(r['label'] == key for r in selected) for key in LABELS}
            require(sum(counts.values()) == len(selected), 'Coordinate label accounting failed')
            row[label] = {'denominator': len(selected), 'counts': counts,
                          'fractions': {k: v / len(selected) if selected else None for k, v in counts.items()}}
        frame_rows.append(row)
    for pairs in (exact, {**exact, **near}):
        require(len(set(pairs.values())) == len(pairs), 'Correspondence is not one-to-one')
    stats = {'count': len(distances), 'min': min(distances) if distances else None,
             'median': float(np.median(distances)) if distances else None, 'max': max(distances) if distances else None}
    return {'nodes': {'baseline': list(records[0].values()), 'tta': list(records[1].values())},
            'frames': frame_rows, 'near_displacement_um': stats}, exact, {**exact, **near}


def compare_edges(baseline, tta, pairs):
    inverse = {v: k for k, v in pairs.items()}
    mapped = []
    for graph, mapping in ((baseline, {k: k for k in pairs}), (tta, inverse)):
        entries = {}
        for e in graph.edges:
            if e.source_id in mapping and e.target_id in mapping:
                key = (mapping[e.source_id], mapping[e.target_id])
                require(key not in entries, 'Duplicate mapped edge')
                entries[key] = e
        mapped.append(entries)
    common = set(mapped[0]) & set(mapped[1])
    only = [set(mapped[0]) - common, set(mapped[1]) - common]
    relation, confidence_only, all_confidence = [], [], []
    for key in sorted(common):
        b, t = mapped[0][key], mapped[1][key]
        if b.relation != t.relation:
            relation.append(list(key))
        if b.confidence != t.confidence:
            all_confidence.append(abs(b.confidence - t.confidence))
            if b.relation == t.relation:
                confidence_only.append([*key, b.confidence, t.confidence])
    answer = {'common': len(common), 'baseline_only': len(only[0]), 'tta_only': len(only[1]),
              'relation_changes': relation, 'confidence_only_changes': confidence_only,
              'max_absolute_confidence_difference': max(all_confidence, default=0.0)}
    for arm, graph, entries, diff in zip(('baseline', 'tta'), (baseline, tta), mapped, only):
        unmapped = len(graph.edges) - len(entries)
        require(len(common) + len(diff) + unmapped == len(graph.edges), 'Edge partition failed')
        answer[arm] = {'total': len(graph.edges), 'both_endpoints_mapped': len(entries),
                       'unmapped_endpoint': unmapped, 'only_endpoint_pairs': [list(k) for k in sorted(diff)]}
    return answer


def compare_history(baseline, tta, pairs):
    bn, bi, bo, bd = graph_index(baseline)
    tn, ti, to, td = graph_index(tta)
    inverse = {v: k for k, v in pairs.items()}
    rows, memo, cross = [], {}, Counter()
    for b in sorted(pairs, key=lambda k: (bn[k].t, k)):
        t = pairs[b]
        require(bn[b].t == tn[t].t, 'Cross-frame correspondence')
        bp, tp = bi.get(b), ti.get(t)
        if bp is None and tp is None:
            immediate, recursive = 'BOTH_ABSENT', 'SAME_CHAIN'
        elif bp is None or tp is None:
            immediate, recursive = 'ONE_ABSENT', 'DIFFERENT_CHAIN'
        elif bp not in pairs or tp not in inverse:
            immediate, recursive = 'UNRESOLVED', 'UNRESOLVED'
        elif pairs[bp] != tp:
            immediate, recursive = 'DIFFERENT_MAPPED_PREDECESSOR', 'DIFFERENT_CHAIN'
        else:
            immediate, recursive = 'SAME_MAPPED_PREDECESSOR', memo[bp]
        memo[b] = recursive
        bs, ts = bo.get(b), to.get(t)
        if (bs is not None and bs not in pairs) or (ts is not None and ts not in inverse):
            outgoing = 'UNRESOLVED'
        elif bs is None and ts is None:
            outgoing = 'NEITHER'
        elif ts is None:
            outgoing = 'BASELINE_ONLY_OUTGOING'
        elif bs is None:
            outgoing = 'TTA_ONLY_OUTGOING'
        else:
            outgoing = 'SAME_MAPPED_SUCCESSOR' if pairs[bs] == ts else 'DIFFERENT_MAPPED_SUCCESSOR'
        row = {'baseline_node_id': b, 'tta_node_id': t, 'outgoing': outgoing,
               'immediate_history': immediate, 'recursive_history': recursive,
               'baseline_depth': bd[b], 'tta_depth': td[t],
               'baseline_predecessor': bp, 'tta_predecessor': tp,
               'baseline_successor': bs, 'tta_successor': ts}
        rows.append(row)
        cross[(outgoing, immediate, recursive)] += 1
    require(sum(cross.values()) == len(pairs) == len(rows), 'History accounting failed')
    return {'rows': rows, 'cross_tab': [{'outgoing': k[0], 'immediate_history': k[1],
                                       'recursive_history': k[2], 'count': v} for k, v in sorted(cross.items())]}


def compare_pruning(removals, pairs):
    b, t = removals
    counts = Counter((b[k], t[v]) for k, v in pairs.items())
    result = {'mapped_pairs': len(pairs),
              'cross_tab': [{'baseline': k[0], 'tta': k[1], 'count': v} for k, v in sorted(counts.items())]}
    require(sum(counts.values()) == len(pairs), 'Pruning pair accounting failed')
    for arm, removal, mapped in [('baseline', b, set(pairs)), ('tta', t, set(pairs.values()))]:
        missing = Counter(v for k, v in removal.items() if k not in mapped)
        require(sum(missing.values()) + len(pairs) == len(removal), 'Pruning coverage failed')
        result[arm + '_unmapped_removal_counts'] = dict(sorted(missing.items()))
    return result


def metric_context(row):
    b, t = row['baseline'], row['tta']
    require(set(b) == set(t), 'Official metric fields differ')
    deltas = {k: None if b[k] is None or t[k] is None else t[k] - b[k] for k in b}
    residual = {arm: row[arm]['adjusted_edge_jaccard'] - row[arm]['edge_jaccard'] for arm in ('baseline', 'tta')}
    residual['delta'] = residual['tta'] - residual['baseline']
    return {'baseline': b, 'tta': t, 'delta': deltas, 'node_adjustment_residual': residual,
            'new_scoring_performed': False}


def diagnose_pair(sample_id, arrays, info, records, official, checkpoint=lambda: None):
    stages, removals, stage_rows = {}, {}, {}
    for arm in ('baseline', 'tta'):
        checkpoint()
        stages[arm], removals[arm], stage_rows[arm] = reconstruct(
            sample_id, arrays[arm], info['shape_tzyx'], info['pruning_enabled'], records[arm])
    checkpoint()
    coords, exact, expanded = correspondence(stages['baseline']['RAW'], stages['tta']['RAW'])
    for arm in ('baseline', 'tta'):
        for node in coords['nodes'][arm]:
            node['first_removal_stage'] = removals[arm][node['node_id']]
    views = {}
    for name, pairs in [('EXACT_ONLY', exact), ('EXACT_PLUS_NEAR', expanded)]:
        checkpoint()
        views[name] = {'mapped_pairs': len(pairs),
                       'edges': {stage: compare_edges(stages['baseline'][stage], stages['tta'][stage], pairs) for stage in STAGES},
                       'raw_history': compare_history(stages['baseline']['RAW'], stages['tta']['RAW'], pairs),
                       'pruning': compare_pruning((removals['baseline'], removals['tta']), pairs)}
    detail = {'sample_id': sample_id, 'pruning_enabled': info['pruning_enabled'], 'stages': stage_rows,
              'correspondence': coords, 'views': views, 'existing_official_metrics': metric_context(official),
              'raw_edges': {arm: edge_rows(stages[arm]['RAW']) for arm in ('baseline', 'tta')},
              'tie_order_eligibility_causal_mechanisms': 'UNMEASURED'}
    summary = {'sample_id': sample_id, 'pruning_enabled': info['pruning_enabled'],
               'official_metrics': detail['existing_official_metrics'],
               'near_displacement_um': coords['near_displacement_um'],
               'coordinate_counts': {arm: dict(Counter(r['label'] for r in coords['nodes'][arm])) for arm in ('baseline', 'tta')},
               'stages': {arm: {s: {k: v for k, v in entry.items() if k not in ('removed_node_ids', 'removed_edges')} for s, entry in stage_rows[arm].items()} for arm in ('baseline', 'tta')},
               'views': {name: {'mapped_pairs': v['mapped_pairs'], 'history_cross_tab': v['raw_history']['cross_tab'],
                                'pruning': v['pruning'], 'edges': {s: {
                                    **{k: e[k] for k in ('common', 'baseline_only', 'tta_only', 'max_absolute_confidence_difference')},
                                    'relation_changes': len(e['relation_changes']),
                                    'confidence_only_changes': len(e['confidence_only_changes']),
                                    'baseline_unmapped_endpoint': e['baseline']['unmapped_endpoint'],
                                    'tta_unmapped_endpoint': e['tta']['unmapped_endpoint'],
                                } for s, e in v['edges'].items()}} for name, v in views.items()},
               'final_graph_export_parities': 2}
    return detail, summary
