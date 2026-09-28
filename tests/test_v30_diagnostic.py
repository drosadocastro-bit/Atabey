"""Synthetic-only instrumentation checks. Never open competition coordinates."""
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import pytest

from atabey.submission.v28 import build_graph, export_graph
from atabey.tracking.unet_graph import detections_from_predictor_coordinates
from atabey.tracking.v30_diagnostic import (
    compare_edges, compare_history, correspondence, diagnose_pair, graph_index,
    metric_context, reconstruct, validate_coordinates,
)
from atabey.types import LineageGraph, LineageEdge

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/run_v30_diagnostic.py'
spec = importlib.util.spec_from_file_location('v30_runner_tests', SCRIPT)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def graph(arm, rows, edges=()):
    nodes = detections_from_predictor_coordinates(arm, rows)
    return LineageGraph(arm, nodes, [LineageEdge(nodes[a].node_id, nodes[b].node_id, confidence) for a, b, confidence in edges])


def ids(g):
    return [n.node_id for n in g.detections]


def labels(result, arm):
    return [r['label'] for r in result['nodes'][arm]]


def record(array, pruning=False, sample_id='synthetic'):
    g, stats = build_graph(sample_id, array, pruning)
    _, rec = export_graph(g, [8, 100, 100, 100], 0)
    rec.update(raw_nodes=stats['raw_nodes'], raw_edges=stats['raw_edges'], route={'apply_pruning': pruning})
    return rec


def metric(score=0.5):
    return {'score': score, 'adjusted_edge_jaccard': score, 'edge_jaccard': .6,
            'division_jaccard': None, 'predicted_nodes': 10}


def test_duplicate_in_either_arm_excludes_both():
    b = graph('b', [[0, 0, 0, 0], [0, 0, 0, 0]])
    t = graph('t', [[0, 0, 0, 0]])
    result, exact, expanded = correspondence(b, t)
    assert not exact and not expanded
    assert labels(result, 'baseline') == ['DUPLICATE_AMBIGUOUS'] * 2
    assert labels(result, 'tta') == ['DUPLICATE_AMBIGUOUS']


def test_crowded_exact_anchor_is_not_removed_to_force_near_pair():
    b = graph('b', [[0, 0, 0, 0], [0, 0, 0, 4]])
    t = graph('t', [[0, 0, 0, 0], [0, 0, 0, 3]])
    result, exact, expanded = correspondence(b, t)
    assert len(exact) == len(expanded) == 1
    assert labels(result, 'baseline') == ['EXACT', 'NEAR_AMBIGUOUS']
    assert labels(result, 'tta') == ['EXACT', 'NEAR_AMBIGUOUS']


@pytest.mark.parametrize('um,expected', [(2.0, 'NEAR_ISOLATED'), (2.000001, 'NO_NEAR_COUNTERPART')])
def test_radius_boundary(um, expected):
    result, exact, expanded = correspondence(graph('b', [[0, 0, 0, 0]]), graph('t', [[0, 0, 0, um / .40625]]))
    assert labels(result, 'tta') == [expected]
    assert not exact
    assert len(expanded) == (expected == 'NEAR_ISOLATED')


def test_anisotropy_and_frame_isolation():
    b = graph('b', [[0, 0, 0, 0], [1, 0, 0, 0]])
    t = graph('t', [[0, 2, 0, 0], [1, 0, 0, 2], [2, 0, 0, 0]])
    result, exact, expanded = correspondence(b, t)
    assert labels(result, 'baseline') == ['NO_NEAR_COUNTERPART', 'NEAR_ISOLATED']
    assert labels(result, 'tta')[-1] == 'NO_NEAR_COUNTERPART'
    assert result['near_displacement_um']['median'] == .8125
    assert len(expanded) == 1 and not exact


def test_no_iterative_matching_on_ambiguous_chain():
    # B0-T0, B1-T0/T1: iterative matching would manufacture pairs.
    b = graph('b', [[0, 0, 0, 0], [0, 0, 0, 4]])
    t = graph('t', [[0, 0, 0, 2], [0, 0, 0, 8]])
    result, _, expanded = correspondence(b, t)
    assert not expanded
    assert labels(result, 'baseline') == ['NEAR_AMBIGUOUS'] * 2


def test_empty_frame_and_exact_coverage_accounting():
    result, exact, expanded = correspondence(graph('b', [[0, 1, 1, 1]]), graph('t', []))
    assert result['frames'][0]['tta']['denominator'] == 0
    assert all(v is None for v in result['frames'][0]['tta']['fractions'].values())
    assert result['near_displacement_um'] == {'count': 0, 'min': None, 'median': None, 'max': None}
    assert not exact and not expanded


@pytest.mark.parametrize('array', [np.zeros((2, 3)), np.array([[0.5, 0, 0, 0]]),
    np.array([[1, 0, 0, 0], [0, 0, 0, 0]]), np.array([[0, -1, 0, 0]]),
    np.array([[0, 1, np.nan, 0]]), np.array([[0, 100, 0, 0]])])
def test_invalid_coordinates_fail(array):
    with pytest.raises(ValueError):
        validate_coordinates(array, [8, 100, 100, 100])


def test_missing_frames_do_not_link_across_gap():
    a = np.array([[0, 1, 1, 1], [2, 1, 1, 1]])
    stages, _, rows = reconstruct('synthetic', a, [8, 100, 100, 100], False, record(a))
    assert not stages['RAW'].edges
    assert rows['P2']['status'] == rows['P3']['status'] == 'BYPASSED'
    assert rows['RAW']['signature'] == rows['P3']['signature']


def test_p2_p3_first_removal_stages():
    a = np.array([[0, 50, 50, 50], [1, 0, 0, 0], [2, 0, 0, 0], [2, 40, 0, 0], [3, 50, 50, 50]])
    stages, removal, rows = reconstruct('synthetic', a, [8, 100, 100, 100], True, record(a, True))
    keys = ids(stages['RAW'])
    assert removal[keys[3]] == 'P2'
    assert removal[keys[1]] == removal[keys[2]] == 'P3'
    assert removal[keys[0]] == removal[keys[4]] == 'SURVIVES'
    assert len(rows['P3']['removed_edges']) == 1


@pytest.mark.parametrize('field', ['raw_nodes', 'raw_edges', 'graph_signature_sha256', 'export_rows_sha256'])
def test_replay_parity_failure_is_not_repaired(field):
    a = np.array([[0, 1, 1, 1], [1, 1, 1, 1]])
    rec = record(a)
    rec[field] = -1 if isinstance(rec[field], int) else 'incorrect'
    with pytest.raises(ValueError, match='parity'):
        reconstruct('synthetic', a, [8, 100, 100, 100], False, rec)


def test_same_counts_different_links_confidence_only_and_unmapped():
    rows = [[0, 0, 0, 0], [0, 0, 0, 20], [1, 0, 0, 0], [1, 0, 0, 20]]
    b = graph('b', rows, [(0, 2, .5), (1, 3, .7)])
    t = graph('t', rows, [(0, 2, .6), (1, 3, .7)])
    pairs = dict(zip(ids(b), ids(t)))
    e = compare_edges(b, t, pairs)
    assert e['common'] == 2 and len(e['confidence_only_changes']) == 1
    t.edges = [LineageEdge(ids(t)[0], ids(t)[3], .5), LineageEdge(ids(t)[1], ids(t)[2], .7)]
    e = compare_edges(b, t, pairs)
    assert e['common'] == 0 and e['baseline_only'] == e['tta_only'] == 2
    h = compare_history(b, t, pairs)['rows']
    assert h[0]['outgoing'] == 'DIFFERENT_MAPPED_SUCCESSOR'
    del pairs[ids(b)[3]]
    assert compare_edges(b, t, pairs)['tta']['unmapped_endpoint'] == 1
    assert compare_history(b, t, pairs)['rows'][0]['outgoing'] == 'UNRESOLVED'


def test_history_propagates_unresolved_and_retains_depth():
    rows = [[0, 0, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0]]
    b, t = (graph(arm, rows, [(0, 1, .5), (1, 2, .5)]) for arm in ('b', 't'))
    pairs = dict(zip(ids(b)[1:], ids(t)[1:]))
    h = compare_history(b, t, pairs)['rows']
    assert h[0]['immediate_history'] == 'UNRESOLVED'
    assert h[1]['immediate_history'] == 'SAME_MAPPED_PREDECESSOR'
    assert h[1]['recursive_history'] == 'UNRESOLVED' and h[1]['baseline_depth'] == 2


def test_history_missing_predecessor_is_confirmed_difference():
    rows = [[0, 0, 0, 0], [1, 0, 0, 0]]
    b, t = graph('b', rows, [(0, 1, .5)]), graph('t', rows)
    h = compare_history(b, t, dict(zip(ids(b), ids(t))))['rows']
    assert h[0]['outgoing'] == 'BASELINE_ONLY_OUTGOING'
    assert h[1]['immediate_history'] == 'ONE_ABSENT' and h[1]['recursive_history'] == 'DIFFERENT_CHAIN'


def test_branching_is_invalid():
    g = graph('b', [[0, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 1]], [(0, 1, .5), (0, 2, .5)])
    with pytest.raises(ValueError, match='branching'):
        graph_index(g)


def test_pair_pipeline_synthetic_only_preserves_metrics_and_nulls():
    a = np.array([[0, 1, 1, 1], [1, 1, 1, 1]])
    official = {'baseline': metric(.5), 'tta': metric(.55)}
    detail, row = diagnose_pair('synthetic', {'baseline': a, 'tta': a.copy()},
        {'shape_tzyx': [8, 100, 100, 100], 'pruning_enabled': False},
        {'baseline': record(a), 'tta': record(a)}, official)
    assert row['final_graph_export_parities'] == 2
    assert detail['views']['EXACT_ONLY']['edges']['RAW']['common'] == 1
    assert detail['existing_official_metrics']['delta']['division_jaccard'] is None
    assert detail['existing_official_metrics']['baseline'] == official['baseline']
    assert detail['existing_official_metrics']['node_adjustment_residual']['delta'] == pytest.approx(.05)
    assert detail['views']['EXACT_ONLY']['raw_history']['rows'][1]['recursive_history'] == 'SAME_CHAIN'


def test_metric_keys_cannot_silently_disappear():
    with pytest.raises(ValueError):
        metric_context({'baseline': metric(), 'tta': {'score': .5}})


def approved(candidate, out):
    return {'status': 'APPROVED_FROZEN', 'authority': 'Danny', 'scope': runner.SCOPE,
            'protocol': runner.PROTOCOL, 'candidate_sha256': runner.sha(candidate),
            'approval_record': 'EXPLICIT FAKE RECEIPT FOR SYNTHETIC TEST ONLY',
            'execution_id': out.name, 'output_directory': str(out.resolve()),
            'submission_authorized': False, 'new_scoring_authorized': False}


@pytest.mark.parametrize('field,value', [('status', 'PROPOSED'), ('authority', 'Codex'),
    ('scope', 'GPU'), ('candidate_sha256', 'bad'), ('approval_record', ''),
    ('execution_id', 'different'), ('submission_authorized', True), ('new_scoring_authorized', True)])
def test_approval_boundaries(tmp_path, field, value):
    candidate = tmp_path / 'candidate.json'; candidate.write_text('{}')
    out = tmp_path / 'run'
    receipt = approved(candidate, out); receipt[field] = value
    with pytest.raises(ValueError):
        runner.validate_receipt(receipt, candidate, out)
    assert not out.exists()


def test_approval_cannot_be_retargeted(tmp_path):
    candidate = tmp_path / 'candidate.json'; candidate.write_text('{}')
    out = tmp_path / 'run'
    receipt = approved(candidate, out)
    runner.validate_receipt(receipt, candidate, out)
    with pytest.raises(ValueError):
        runner.validate_receipt(receipt, candidate, tmp_path / 'retry')


def test_hash_mismatch_and_escape_are_rejected(tmp_path):
    f = tmp_path / 'input'; f.write_bytes(b'a')
    item = runner.identity(tmp_path, f)
    assert runner.artifact(tmp_path, item) == f
    f.write_bytes(b'b')
    with pytest.raises(ValueError, match='identity'):
        runner.artifact(tmp_path, item)
    with pytest.raises(ValueError, match='escapes'):
        runner.artifact(tmp_path, {**item, 'path': '../input'})


def test_outputs_are_exclusive_and_compressed_roundtrip(tmp_path):
    f = tmp_path / 'row.json'; runner.save(f, {'a': 1})
    with pytest.raises(FileExistsError):
        runner.save(f, {'a': 2})
    assert runner.load(f) == {'a': 1}
    compressed = tmp_path / 'detail.json.gz'
    runner.write_compressed(compressed, {'x': [1, 2]})
    with runner.gzip.open(compressed, 'rt', encoding='utf-8') as stream:
        assert json.load(stream) == {'x': [1, 2]}


def test_wall_timeout_stops_worker():
    timed_out, code = runner.bounded_worker(time.sleep, (10,), .1)
    assert timed_out and code != 0


def test_worker_can_finish_without_timeout():
    timed_out, code = runner.bounded_worker(time.sleep, (0,), 10)
    assert not timed_out and code == 0


def test_no_receipt_blocks_before_scientific_work(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'verify_candidate', lambda *_: {})
    monkeypatch.setattr(sys, 'argv', ['run', '--candidate', str(tmp_path / 'fake.json'), '--output-dir', str(tmp_path / 'never')])
    with pytest.raises(ValueError, match='separate frozen approval'):
        runner.main()
    assert not (tmp_path / 'never').exists()


def test_candidate_requires_complete_implementation_binding(tmp_path):
    candidate = tmp_path / 'candidate.json'
    candidate.write_text(json.dumps({'protocol': runner.PROTOCOL, 'status': 'IMPLEMENTED_AWAITING_REVIEW',
                                    'execution_authorized': False, 'artifacts': []}))
    with pytest.raises(ValueError, match='Incomplete implementation binding'):
        runner.verify_candidate(tmp_path, candidate)


def test_worker_full_synthetic_cohort_and_closure(tmp_path, monkeypatch):
    # The inventory/evaluator registry is explicitly fake; actual graph replay,
    # export parity, correspondence, file writing and accounting are exercised.
    sample_ids = [f'synthetic_{i:03}' for i in range(199)]
    a = np.array([[0, 1, 1, 1], [1, 1, 1, 1]])
    samples = {}
    for sid in sample_ids:
        coordinates = tmp_path / (sid + '.npy'); np.save(coordinates, a)
        rec = tmp_path / (sid + '.json'); runner.save(rec, record(a, sample_id=sid))
        samples[sid] = {'shape_tzyx': [8, 100, 100, 100], 'pruning_enabled': False,
                        'arms': {arm: {'coordinates': runner.identity(tmp_path, coordinates),
                                       'record': runner.identity(tmp_path, rec)} for arm in ('baseline', 'tta')}}
    proposal = {'sample_order': sample_ids, 'samples': samples,
                'existing_strata': {'all_synthetic': sample_ids}, 'new_route_groups': {'false': sample_ids, 'true': []},
                'focus_union': sample_ids[:1], 'protected_ids': sample_ids[:1], 'focus_loss_ids': []}
    runner.save(tmp_path / runner.PROPOSAL, proposal)
    candidate = tmp_path / 'candidate.json'; candidate.write_text('{}')
    out = tmp_path / 'run'; out.mkdir()
    receipt = tmp_path / 'fake_receipt.json'; runner.save(receipt, approved(candidate, out))
    official = {'rows': [{'sample_id': sid, 'baseline': metric(), 'tta': metric()} for sid in sample_ids],
                'summaries': {'FAKE': 'synthetic aggregate'}, 'strata': {}, 'decision': {'FAKE': 'not a research result'}}
    calls = []
    def fake_preflight(*args):
        calls.append('preflight')
        return {'status': 'FAKE_SYNTHETIC_INPUT_REGISTRY'}, official
    monkeypatch.setattr(runner, 'verify_candidate', lambda *_: {})
    monkeypatch.setattr(runner, 'preflight', fake_preflight)
    runner.worker(str(tmp_path), str(candidate), str(receipt), str(out), time.monotonic() + 60)
    result = runner.load(out / 'completed_payload.json')
    assert result['completed_ids'] == sample_ids and len(calls) == 2
    assert sum(r['final_graph_export_parities'] for r in result['rows']) == 398
    assert result['existing_official_aggregates'] == official['summaries']
    assert result['groups']['all_synthetic']['coordinate_counts']['baseline']['EXACT'] == 398
    assert result['groups']['focus']['coordinate_counts']['baseline']['EXACT'] == 2
    assert len(list((out / 'samples').glob('*.json.gz'))) == 199
    assert 'synthetic_198' in runner.report(result)
    assert not (out / 'result.json').exists()  # Only successful parent may publish completion.


def test_worker_preserves_first_failure_and_no_completion(tmp_path, monkeypatch):
    candidate = tmp_path / 'candidate.json'; candidate.write_text('{}')
    out = tmp_path / 'run'; out.mkdir()
    receipt = tmp_path / 'receipt.json'; runner.save(receipt, approved(candidate, out))
    runner.save(tmp_path / runner.PROPOSAL, {})
    monkeypatch.setattr(runner, 'verify_candidate', lambda *_: {})
    def fail(*args):
        raise ValueError('deliberate synthetic input mismatch')
    monkeypatch.setattr(runner, 'preflight', fail)
    with pytest.raises(ValueError, match='deliberate synthetic'):
        runner.worker(str(tmp_path), str(candidate), str(receipt), str(out), time.monotonic() + 10)
    failure = runner.load(out / 'worker_failure.json')
    assert failure['status'] == 'INVALID_INCOMPLETE' and failure['completed_ids'] == []
    assert not (out / 'completed_payload.json').exists()
