"""V27B shadow orchestration over immutable V27A.1 decision functions."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict

from atabey.tracking.association_factorial_audit_v27a1 import (
    audit_factorial_frame, scientific_digest,
)
from atabey.tracking.association_factorial_audit import CONTRASTS
from atabey.tracking.nearest_neighbor import _greedy_assign
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments
from atabey.tracking.v26_a_forward_ranking_shadow import relink_detections_step_ranked
from atabey.types import LineageGraph

ARM_IDS = ('H', 'M0', 'M1', 'S0', 'S1')
STAGES = ('RAW', 'P2', 'P3')


def graph_digest(graph):
    """Full ordered data, including confidence and every detection attribute."""
    return scientific_digest(asdict(graph))


def edge_map(graph):
    result = {(e.source_id, e.target_id): e for e in graph.edges}
    if len(result) != len(graph.edges):
        raise RuntimeError('Duplicate graph edge')
    return result


def compare_decisions(source_id, before, after):
    old, new = before['accepted_target_id'], after['accepted_target_id']
    category = ('SAME' if old == new else 'GAIN' if old is None else
                'LOSS' if new is None else 'SWITCH')
    return {'category': category,
            'selected_changed': before['selected_target_id'] != after['selected_target_id'],
            'gate_eligible_changed': before['gate_eligible_target_id'] != after['gate_eligible_target_id'],
            'accepted_changed': old != new,
            'accepted_delta': int(new is not None) - int(old is not None),
            'confidence_only_changed': old is not None and old == new and before['confidence'] != after['confidence'],
            'removed_edge': [source_id, old] if old is not None and old != new else None,
            'added_edge': [source_id, new] if new is not None and old != new else None}


def count_comparison(counts, prefix, comparison):
    counts[f'{prefix}::category::{comparison["category"]}'] += 1
    for key in ('selected_changed', 'gate_eligible_changed', 'accepted_changed',
                'accepted_delta', 'confidence_only_changed'):
        counts[f'{prefix}::{key}'] += int(comparison[key])
    for key in ('added_edge', 'removed_edge'):
        counts[f'{prefix}::{key}'] += int(comparison[key] is not None)


def _check(condition, message, emit, context):
    if not condition:
        emit({'type': 'validity_failure', 'check': message, 'context': context})
        raise RuntimeError(message)


def recursive_graphs(baseline, frozen_frames, emit):
    """Consume verified F frames; persist probes before checking or propagating.

    No probe other than its named active arm may update a recursive history.
    The caller owns streaming persistence and the execution/freeze boundary.
    """
    original = graph_digest(baseline)
    frames = defaultdict(list)
    for node in baseline.detections:
        frames[node.t].append(node)
    _check(len({n.node_id for n in baseline.detections}) == len(baseline.detections),
           'Duplicate detection identity', emit, {})
    _check(all(n.sample_id == baseline.sample_id and n.t >= 0 for n in baseline.detections),
           'Invalid sample or time', emit, {})
    graphs = {a: LineageGraph(baseline.sample_id, list(baseline.detections)) for a in ARM_IDS}
    histories = {a: {} for a in ARM_IDS}
    counts = Counter({'sources': 0, 'frames': 0})
    for regime in ('F', 'R'):
        for value in range(-2, 3):
            counts[f'{regime}::interaction::{value}'] = 0
    for value in range(-4, 5):
        counts[f'history::interaction::{value}'] = 0
    first = {a: {k: None for k in ('history', 'selection', 'acceptance')} for a in ARM_IDS}
    iterator = iter(frozen_frames)
    for t in range(max(frames, default=0)):
        context = {'sample_id': baseline.sample_id, 'source_t': t}
        frozen = next(iterator, None)
        _check(frozen is not None, 'Missing frozen frame', emit, context)
        prev, curr = frames[t], frames[t + 1]
        _check(frozen['source_ids'] == [n.node_id for n in prev] and
               frozen['target_ids'] == [n.node_id for n in curr] and not frozen['validity_failures'],
               'Frozen frame identity or validity mismatch', emit, context)
        frows = frozen['rows']
        active = {}
        # Equal full contexts must reproduce the same original observation,
        # even when several independently owned histories converge again.
        context_digests = {frozen['input_sha256_before']: frozen['parent_observation_sha256']}
        for arm in ARM_IDS:
            local_context = {**context, 'history_owner': arm}
            parents = histories[arm]
            _check(all(k in {n.node_id for n in prev} and v.t == t - 1 for k, v in parents.items()),
                   'Recursive predecessor is not adjacent', emit, local_context)
            # The complete input is persisted even if the observer raises before returning.
            emit({'type': 'context', **local_context, 'previous': [asdict(n) for n in prev],
                  'current': [asdict(n) for n in curr],
                  'predecessors': {k: asdict(v) for k, v in parents.items()}})
            probe = audit_factorial_frame(prev, curr, parents)
            emit({'type': 'probe', **local_context, 'frame': probe})
            _check(not probe['validity_failures'], 'Common-context validity failure', emit,
                   {**local_context, 'failures': probe['validity_failures']})
            _check(probe['input_sha256_before'] == probe['input_sha256_after'],
                   'Probe mutated its input', emit, local_context)
            input_key = probe['input_sha256_before']
            observation = probe['parent_observation_sha256']
            _check(context_digests.get(input_key, observation) == observation,
                   'Identical context produced different observations', emit, local_context)
            context_digests[input_key] = observation
            _check(probe['source_ids'] == frozen['source_ids'] and
                   probe['target_ids'] == frozen['target_ids'] and
                   probe['source_positions_um'] == frozen['source_positions_um'] and
                   probe['target_positions_um'] == frozen['target_positions_um'] and
                   probe['reverse_ownership'] == frozen['reverse_ownership'],
                   'History-independent geometry changed', emit, local_context)
            _check(len(probe['rows']) == len(frows), 'Source row count mismatch', emit, local_context)
            active[arm] = probe['rows']
            for fr, rr in zip(frows, probe['rows']):
                _check(fr['source_id'] == rr['source_id'] and fr['physical_steps_um'] == rr['physical_steps_um'],
                       'Source identity or step table changed', emit, local_context)
                if arm == 'H' or t == 0:
                    _check(fr['decisions'][arm] == rr['decisions'][arm] and
                           fr['predecessor_id'] == rr['predecessor_id'] and
                           fr['predicted_position_um'] == rr['predicted_position_um'],
                           'Historical or initial-history anchor mismatch', emit, local_context)
                if arm == 'S0':
                    _check(fr['decisions'][arm]['selected_target_id'] == rr['decisions'][arm]['selected_target_id'],
                           'S0 selection changed with history', emit, local_context)
            # Reuse stable historical assignment to preserve edge ordering and relation.
            src, dst = {n.node_id: n for n in prev}, {n.node_id: n for n in curr}
            pairs = [(row['decisions'][arm]['prediction_error_um'], src[row['source_id']],
                      dst[row['decisions'][arm]['accepted_target_id']])
                     for row in probe['rows'] if row['decisions'][arm]['accepted_target_id'] is not None]
            edges = _greedy_assign(pairs, 9.0)
            _check(len(edges) == len(pairs) and len({e.target_id for e in edges}) == len(edges),
                   'Recursive edge uniqueness mismatch', emit, local_context)
            graphs[arm].edges.extend(edges)
            # Replace, do not update: expired state can never survive this transition.
            histories[arm] = {e.target_id: src[e.source_id] for e in edges}
            for disposition in probe['parent_criterion_dispositions']:
                counts[f'probe::{arm}::disposition::{disposition["disposition"]}'] += 1
            counts[f'probe::{arm}::frames'] += 1
        for index, fr in enumerate(frows):
            sid = fr['source_id']
            rows = {a: active[a][index] for a in ARM_IDS}
            fdec = fr['decisions']
            rdec = {a: rows[a]['decisions'][a] for a in ARM_IDS}
            history_comparisons, contrasts = {}, {}
            counts['sources'] += 1
            for arm in ARM_IDS:
                rr = rows[arm]
                comp = compare_decisions(sid, fdec[arm], rdec[arm])
                comp.update(predecessor_changed=fr['predecessor_id'] != rr['predecessor_id'],
                            prediction_changed=fr['predicted_position_um'] != rr['predicted_position_um'])
                history_comparisons[arm] = comp
                count_comparison(counts, f'history::{arm}', comp)
                for flag in ('predecessor_changed', 'prediction_changed'):
                    counts[f'history::{arm}::{flag}'] += int(comp[flag])
                for kind, changed in (('history', comp['predecessor_changed']),
                                      ('selection', comp['selected_changed']), ('acceptance', comp['accepted_changed'])):
                    if changed and first[arm][kind] is None:
                        first[arm][kind] = {**context, 'source_id': sid}
                for regime, row, decision in (('F', fr, fdec[arm]), ('R', rr, rdec[arm])):
                    counts[f'{regime}::{arm}::accepted'] += int(decision['accepted_target_id'] is not None)
                    counts[f'{regime}::{arm}::available_targets'] += len(row['prediction_errors_um'])
                    counts[f'{regime}::{arm}::feasible_targets'] += len(row['feasible_indices'])
            for name, (before, after) in CONTRASTS.items():
                contrasts[name] = {}
                for regime, decisions in (('F', fdec), ('R', rdec)):
                    c = compare_decisions(sid, decisions[before], decisions[after])
                    contrasts[name][regime] = c
                    count_comparison(counts, f'{regime}::contrast::{name}', c)
                change = contrasts[name]['R']['accepted_delta'] - contrasts[name]['F']['accepted_delta']
                _check(change == history_comparisons[after]['accepted_delta'] - history_comparisons[before]['accepted_delta'],
                       'History accounting identity failed', emit, context)
                contrasts[name]['history_sensitivity'] = change
                counts[f'contrast::{name}::history_sensitivity'] += change
            interactions = {}
            for regime, dec in (('F', fdec), ('R', rdec)):
                y = {a: int(dec[a]['accepted_target_id'] is not None) for a in ARM_IDS}
                interactions[regime] = (y['S1'] - y['S0']) - (y['M1'] - y['M0'])
                counts[f'{regime}::interaction::{interactions[regime]}'] += 1
                counts[f'{regime}::interaction_sum'] += interactions[regime]
            interactions['difference'] = interactions['R'] - interactions['F']
            counts[f'history::interaction::{interactions["difference"]}'] += 1
            counts['history::interaction_sum'] += interactions['difference']
            emit({'type': 'comparison', **context, 'source_id': sid,
                  'F': {'predecessor_id': fr['predecessor_id'], 'predicted_position_um': fr['predicted_position_um'], 'decisions': fdec},
                  'R': {a: {'predecessor_id': rows[a]['predecessor_id'], 'predicted_position_um': rows[a]['predicted_position_um'], 'decision': rdec[a]} for a in ARM_IDS},
                  'history_comparisons': history_comparisons, 'contrasts': contrasts, 'interactions': interactions})
        counts['frames'] += 1
    _check(next(iterator, None) is None, 'Extra frozen frame', emit, {})
    _check(graph_digest(baseline) == original, 'Baseline mutated', emit, {})
    _check(graph_digest(graphs['H']) == original, 'Recursive H graph anchor mismatch', emit, {})
    exact_s1 = relink_detections_step_ranked(baseline.sample_id, tuple(baseline.detections))
    _check(graph_digest(graphs['S1']) == graph_digest(exact_s1), 'Recursive S1 executable anchor mismatch', emit, {})
    return graphs, {'counts': dict(sorted(counts.items())), 'first_divergence': first}


def check_subset(before, after):
    nodes = {n.node_id: n for n in before.detections}
    edges = edge_map(before)
    if (after.sample_id != before.sample_id or len({n.node_id for n in after.detections}) != len(after.detections)
            or any(nodes.get(n.node_id) != n for n in after.detections)
            or any(edges.get((e.source_id, e.target_id)) != e for e in after.edges)):
        raise RuntimeError('Pruning changed a retained attribute or created an identity')
    remaining = {n.node_id for n in after.detections}
    if any(e.source_id not in remaining or e.target_id not in remaining for e in after.edges):
        raise RuntimeError('Pruning left an edge without endpoints')
    edge_map(after)


def pruning_stages(graphs, emit):
    """Produce graph stages and complete raw-union survival ledgers after linking."""
    stages, counts = {}, Counter()
    for arm in ARM_IDS:
        raw = graphs[arm]
        stages[arm] = {'RAW': raw}
        for before_name, after_name, transform in (
                ('RAW', 'P2', prune_interior_isolated_detections),
                ('P2', 'P3', prune_interior_short_fragments)):
            before = stages[arm][before_name]
            digest = graph_digest(before)
            emit({'type': 'pruning_input', 'arm': arm, 'before_stage': before_name,
                  'after_stage': after_name, 'before': asdict(before)})
            after = transform(before)
            emit({'type': 'pruning_context', 'arm': arm, 'before_stage': before_name,
                  'after_stage': after_name, 'before_sha256': digest, 'after': asdict(after)})
            _check(graph_digest(before) == digest, 'Pruning mutated its input', emit, {'arm': arm})
            check_subset(before, after)
            stages[arm][after_name] = after
            removed_nodes = sorted({n.node_id for n in before.detections} - {n.node_id for n in after.detections})
            removed_edges = sorted(set(edge_map(before)) - set(edge_map(after)))
            emit({'type': 'pruning_removed', 'arm': arm, 'before_stage': before_name,
                  'after_stage': after_name, 'nodes': removed_nodes, 'edges': removed_edges})
        for name, graph in stages[arm].items():
            counts[f'{arm}::{name}::nodes'] = len(graph.detections)
            counts[f'{arm}::{name}::edges'] = len(graph.edges)
    for name, (before_arm, after_arm) in CONTRASTS.items():
        lookup = {a: {s: edge_map(g) for s, g in stages[a].items()} for a in (before_arm, after_arm)}
        nodes = {a: {s: {n.node_id for n in g.detections} for s, g in stages[a].items()} for a in lookup}
        for stage in STAGES:
            before, after = lookup[before_arm][stage], lookup[after_arm][stage]
            added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
            changed_confidence = sorted(k for k in before.keys() & after.keys() if before[k].confidence != after[k].confidence)
            emit({'type': 'stage_contrast', 'contrast': name, 'stage': stage,
                  'added_edges': added, 'removed_edges': removed, 'shared_confidence_changed': changed_confidence,
                  'added_nodes': sorted(nodes[after_arm][stage] - nodes[before_arm][stage]),
                  'removed_nodes': sorted(nodes[before_arm][stage] - nodes[after_arm][stage])})
            for label, values in (('added', added), ('removed', removed), ('confidence_changed', changed_confidence)):
                counts[f'contrast::{name}::{stage}::{label}'] = len(values)
        for edge in sorted(lookup[before_arm]['RAW'].keys() | lookup[after_arm]['RAW'].keys()):
            emit({'type': 'edge_survival', 'contrast': name, 'edge': edge,
                  'survival': {a: {s: {'edge': edge in lookup[a][s], 'source': edge[0] in nodes[a][s],
                                       'target': edge[1] in nodes[a][s]} for s in STAGES} for a in lookup}})
    return stages, dict(sorted(counts.items()))
