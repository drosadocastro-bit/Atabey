from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from atabey.tracking import recursive_history_audit as audit
from atabey.tracking.association_factorial_audit_v27a1 import audit_factorial_frame
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageGraph, LineageEdge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v27a1_association_decomposition as parent
import run_v27b_recursive_history as runner


def node(name, t, x, sample='synthetic'):
    return Detection(name, sample, t, 0, 0, x, 0, 0, x)


def baseline(frames):
    graph = LineageGraph('synthetic', [n for frame in frames for n in frame])
    parents = {}
    for prev, curr in zip(frames, frames[1:]):
        edges = link_adjacent_timepoints(prev, curr, 9, strategy='motion_mutual', predecessor_by_node_id=parents)
        graph.edges.extend(edges)
        lookup = {n.node_id: n for n in prev}
        parents = {e.target_id: lookup[e.source_id] for e in edges}
    return graph


def frozen(graph):
    frames = {}
    for n in graph.detections:
        frames.setdefault(n.t, []).append(n)
    nodes = {n.node_id: n for n in graph.detections}
    parents = {e.target_id: nodes[e.source_id] for e in graph.edges}
    for t in range(max(frames, default=0)):
        prev = frames.get(t, [])
        yield audit_factorial_frame(prev, frames.get(t + 1, []), {n.node_id: parents[n.node_id] for n in prev if n.node_id in parents})


def run(graph):
    events = []
    graphs, result = audit.recursive_graphs(graph, frozen(graph), events.append)
    return graphs, result, events


def divergent_graph():
    return baseline([[node('p', 0, -4)], [node('s', 1, 0)],
                     [node('a', 2, 1), node('b', 2, 4)], [node('next', 3, 2)]])


def test_own_history_diverges_and_arms_and_passes_are_isolated():
    graph = divergent_graph(); before = deepcopy(graph)
    graphs, summary, events = run(graph)
    comparisons = {e['source_id']: e for e in events if e['type'] == 'comparison'}
    assert comparisons['s']['R']['S0']['decision']['accepted_target_id'] == 'a'
    assert comparisons['a']['F']['predecessor_id'] is None
    assert comparisons['a']['R']['S0']['predecessor_id'] == 's'
    assert comparisons['a']['R']['H']['predecessor_id'] is None
    assert comparisons['a']['history_comparisons']['S0']['confidence_only_changed']
    assert graphs['H'] == graph == before
    again = run(graph)
    assert (graphs, summary, events) == again
    assert summary['counts']['sources'] == 4
    for arm in audit.ARM_IDS:
        initial = comparisons['p']['history_comparisons'][arm]
        assert not initial['accepted_changed'] and not initial['predecessor_changed']


def test_empty_frame_breaks_history_and_does_not_bridge():
    graph = baseline([[node('a', 0, 0)], [node('b', 1, 1)], [],
                      [node('c', 3, 3)], [node('d', 4, 4)]])
    graphs, result, events = run(graph)
    for arm in audit.ARM_IDS:
        assert {(e.source_id, e.target_id) for e in graphs[arm].edges} == {('a', 'b'), ('c', 'd')}
    c = next(e for e in events if e['type'] == 'comparison' and e['source_id'] == 'c')
    assert all(r['predecessor_id'] is None for r in c['R'].values())
    assert result['counts']['frames'] == 4


def test_later_non_tied_difference_after_forward_tie_is_valid_across_histories():
    # >16 targets uses the pinned cKDTree partition tie behavior: +1 wins over
    # original index zero (-1). This is synthetic geometry, not opened labels.
    targets = [node('left', 1, -1), node('right', 1, 1)] + [node(f'far{i}', 1, 20 + i) for i in range(15)]
    graph = baseline([[node('start', 0, 0)], targets,
                      [node('near', 2, 1.25), node('ahead', 2, 2.25)]])
    graphs, result, events = run(graph)
    first = next(e for e in events if e['type'] == 'comparison' and e['source_id'] == 'start')
    assert first['R']['H']['decision']['accepted_target_id'] == 'right'
    assert first['R']['M0']['decision']['accepted_target_id'] == 'left'
    later = next(e for e in events if e['type'] == 'comparison' and e['source_id'] == 'right')
    h, m = later['R']['H'], later['R']['M0']
    assert h['decision']['accepted_target_id'] == 'ahead'
    assert m['decision']['accepted_target_id'] == 'near'
    assert len(h['decision']['rank_tie_indices']) == len(m['decision']['rank_tie_indices']) == 1
    assert h['predecessor_id'] != m['predecessor_id']
    assert all(not e['frame']['validity_failures'] for e in events if e['type'] == 'probe')


def test_s0_original_index_tie_and_selection_survive_history_changes():
    graph = baseline([[node('p', 0, -2)], [node('s', 1, 0)],
                      [node('first', 2, -1), node('second', 2, 1)]])
    _, _, events = run(graph)
    s = next(e for e in events if e['type'] == 'comparison' and e['source_id'] == 's')
    assert s['R']['S0']['decision']['selected_target_id'] == 'first'
    assert s['F']['decisions']['S0']['selected_target_id'] == 'first'


def test_failure_probe_is_persisted_before_propagation(monkeypatch):
    graph = divergent_graph(); saved = []
    original = audit.audit_factorial_frame
    def invalid(*args):
        record = original(*args)
        record['validity_failures'].append({'check': 'explicit_synthetic_failure'})
        return record
    # Materialize valid F before injecting a recursive-only failure.
    reference = list(frozen(graph))
    monkeypatch.setattr(audit, 'audit_factorial_frame', invalid)
    with pytest.raises(RuntimeError, match='Common-context validity'):
        audit.recursive_graphs(graph, reference, saved.append)
    assert saved[0]['type'] == 'context'
    assert saved[1]['frame']['validity_failures'] == [{'check': 'explicit_synthetic_failure'}]
    assert not any(e['type'] == 'comparison' for e in saved)


def test_observer_exception_retains_full_inputs(monkeypatch):
    graph = divergent_graph(); saved = []; reference = list(frozen(graph))
    def failure(*args): raise ValueError('explicit synthetic exception')
    monkeypatch.setattr(audit, 'audit_factorial_frame', failure)
    with pytest.raises(ValueError, match='explicit synthetic'):
        audit.recursive_graphs(graph, reference, saved.append)
    assert saved[0]['previous'] and saved[0]['current'] and saved[0]['history_owner'] == 'H'


def test_pruning_never_feeds_history_and_records_shared_edge_survival():
    graphs, summary, events = run(divergent_graph())
    before = deepcopy(graphs); output = []
    stages, counts = audit.pruning_stages(graphs, output.append)
    assert graphs == before
    assert len(stages) == 5 and all(tuple(s) == audit.STAGES for s in stages.values())
    assert any(e['type'] == 'edge_survival' for e in output)
    for a in audit.ARM_IDS:
        audit.check_subset(stages[a]['RAW'], stages[a]['P2'])
        audit.check_subset(stages[a]['P2'], stages[a]['P3'])
    assert run(divergent_graph())[1] == summary


def test_shared_raw_edge_can_survive_only_one_final_graph():
    ns = [node('boundary0', 0, 50), node('a', 1, 0), node('b', 2, 1), node('c', 3, 2), node('boundary4', 4, 50)]
    short = LineageGraph('synthetic', ns, [LineageEdge('a', 'b', .5)])
    long = LineageGraph('synthetic', ns, [LineageEdge('a', 'b', .5), LineageEdge('b', 'c', .5)])
    graphs = {a: deepcopy(short) for a in audit.ARM_IDS}; graphs['M1'] = long
    events = []; stages, counts = audit.pruning_stages(graphs, events.append)
    witness = next(e for e in events if e['type'] == 'edge_survival' and e['contrast'] == 'order_motion' and e['edge'] == ('a', 'b'))
    assert witness['survival']['M0']['RAW']['edge'] and witness['survival']['M1']['RAW']['edge']
    assert not witness['survival']['M0']['P3']['edge'] and witness['survival']['M1']['P3']['edge']


@pytest.mark.parametrize('mutation', ['confidence', 'coordinate', 'extra_edge', 'missing_endpoint'])
def test_pruning_subset_rejects_corruption(mutation):
    graph = baseline([[node('a', 0, 0)], [node('b', 1, 1)]])
    child = deepcopy(graph)
    if mutation == 'confidence': child.edges[0] = replace(child.edges[0], confidence=.123)
    if mutation == 'coordinate': child.detections[0] = replace(child.detections[0], x_um=123)
    if mutation == 'extra_edge': child.edges.append(LineageEdge('b', 'a'))
    if mutation == 'missing_endpoint': child.detections.pop()
    with pytest.raises(RuntimeError): audit.check_subset(graph, child)


@pytest.mark.parametrize('old,new,expected', [(None,None,'SAME'),(None,'b','GAIN'),('a',None,'LOSS'),('a','b','SWITCH'),('a','a','SAME')])
def test_comparison_counts_target_replacements_once(old, new, expected):
    def decision(target): return {'accepted_target_id':target,'selected_target_id':target,'gate_eligible_target_id':target,'confidence':.5 if target else None}
    c = audit.compare_decisions('s',decision(old),decision(new))
    assert c['category'] == expected
    assert c['accepted_delta'] == int(new is not None)-int(old is not None)
    if expected == 'SWITCH': assert c['added_edge'] == ['s','b'] and c['removed_edge'] == ['s','a']


def test_two_complete_synthetic_passes_match_graphs_streams_and_ledgers(tmp_path):
    graph = divergent_graph()
    record = {'sample_id':'synthetic','v19_credited_v24_3_lost_edges':[]}
    f = parent.replay_sample(record,graph,tmp_path/'reference.gz')
    graphs, _, _ = run(graph); stages, _ = audit.pruning_stages(graphs,lambda event:None)
    anchors = {'f_frame_stream_sha256':f['frame_stream_sha256'],'f_counts':f['counts'],
               'r_h_graph_signatures':{s:parent._graph_signature_sha256(stages['H'][s]) for s in audit.STAGES},
               'r_s1_p3_sha256':parent._graph_signature_sha256(stages['S1']['P3'])}
    first = runner.run_sample_pass(record,graph,anchors,tmp_path/'pass1')
    second = runner.run_sample_pass(record,graph,anchors,tmp_path/'pass2')
    assert first == second
    assert len(list((tmp_path/'pass1').glob('*.json.gz'))) == 15
    assert len(first['scientific_artifacts']) == 18
    with pytest.raises(FileExistsError): runner.run_sample_pass(record,graph,anchors,tmp_path/'pass1')


def test_wrong_f_reference_stops_before_recursive_work(tmp_path):
    graph = divergent_graph(); record = {'sample_id':'synthetic','v19_credited_v24_3_lost_edges':[]}
    with pytest.raises(RuntimeError,match='Frozen frame stream mismatch'):
        runner.run_sample_pass(record,graph,{'f_frame_stream_sha256':'wrong'},tmp_path/'pass')
    assert (tmp_path/'pass/frozen.jsonl.gz').is_file()
    assert not (tmp_path/'pass/recursive.jsonl.gz').exists()


def test_pruning_mutation_keeps_preimage_and_stops(monkeypatch):
    graphs, _, _ = run(divergent_graph()); events = []
    original = audit.graph_digest(graphs['H'])
    def corrupt(graph):
        graph.edges.clear()
        return deepcopy(graph)
    monkeypatch.setattr(audit, 'prune_interior_isolated_detections', corrupt)
    with pytest.raises(RuntimeError, match='Pruning mutated'):
        audit.pruning_stages(graphs, events.append)
    assert events[0]['type'] == 'pruning_input'
    assert events[0]['before']['edges']
    assert audit.scientific_digest(events[0]['before']) == original


def test_missing_and_extra_frozen_frames_cannot_complete():
    graph = divergent_graph(); rows = list(frozen(graph))
    for reference, message in ((rows[:-1], 'Missing frozen frame'), (rows + [rows[-1]], 'Extra frozen frame')):
        with pytest.raises(RuntimeError, match=message):
            audit.recursive_graphs(graph, reference, lambda event: None)


def test_initial_confidence_and_step_anchor_failures_are_not_excused(monkeypatch):
    graph = divergent_graph(); rows = list(frozen(graph)); events = []
    original = audit.audit_factorial_frame
    def corrupt(*args):
        probe = original(*args)
        probe['rows'][0]['decisions']['H']['confidence'] = .01
        return probe
    monkeypatch.setattr(audit, 'audit_factorial_frame', corrupt)
    with pytest.raises(RuntimeError, match='anchor mismatch'):
        audit.recursive_graphs(graph, rows, events.append)
    assert any(e['type'] == 'validity_failure' for e in events)


def test_graph_stage_anchor_failure_preserves_written_graph(tmp_path):
    graph = divergent_graph(); record = {'sample_id':'synthetic','v19_credited_v24_3_lost_edges':[]}
    f = parent.replay_sample(record,graph,tmp_path/'ref.gz')
    anchors = {'f_frame_stream_sha256':f['frame_stream_sha256'],'f_counts':f['counts'],
               'r_h_graph_signatures':{'RAW':'wrong'}}
    with pytest.raises(RuntimeError, match='historical graph mismatch'):
        runner.run_sample_pass(record,graph,anchors,tmp_path/'attempt')
    assert (tmp_path/'attempt/H.RAW.json.gz').exists()
    assert (tmp_path/'attempt/pruning.jsonl.gz').exists()
