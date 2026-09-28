from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from atabey.evaluation import frozen_graph_audit as audit
from atabey.evaluation.official_tracking_metric import evaluate_official_tracking
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


def node(name, t, y):
    return Detection(name, 'synthetic', t, 0., y/.40625, 0., 0., y, 0.)


def truth():
    return SparseGroundTruthGraph('synthetic', [GroundTruthNode(10,0,0,0,0,0.,0.,0.),
        GroundTruthNode(11,1,0,0,0,0.,0.,0.)], [(10,11)], 2)


def graph():
    return LineageGraph('synthetic', [node('a',0,0), node('b',1,0)], [LineageEdge('a','b',.7)])


def test_single_host_evaluation_and_adapter_parity(monkeypatch):
    import tracking_cellmot.metrics as host
    original = host.evaluate
    calls = []
    def counted(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    g, gt = graph(), truth()
    expected = asdict(evaluate_official_tracking(g, gt))
    monkeypatch.setattr(host, 'evaluate', counted)
    before = deepcopy((g,gt))
    result = audit.evaluate_graph(g,gt)
    assert calls == [{'scale':None,'max_distance':7.0}]
    assert result['metrics'] == expected
    assert (g,gt) == before
    assert result['credited_gt_edges'] == [[10,11]]
    assert result['category_counts']['OFFICIAL_TP'] == 1
    assert result['metrics']['division_jaccard'] is None
    assert result['undefined']['division_jaccard'] == 'zero_division_denominator'


def test_outside_sparse_gt_is_not_official_fp_but_changes_adjustment():
    g = graph()
    g.detections += [node('noise0',0,100),node('noise1',1,100)]
    g.edges.append(LineageEdge('noise0','noise1'))
    r = audit.evaluate_graph(g,truth())
    assert r['category_counts']['UNEVALUATED_BY_SPARSE_GT'] == 1
    assert r['metrics']['edge_fp'] == 0
    assert r['metrics']['adjusted_edge_jaccard'] == pytest.approx(.9)


def test_evaluable_unmatched_edge_is_official_fp():
    g = graph()
    g.detections[1] = node('b',1,100)
    r = audit.evaluate_graph(g,truth())
    assert r['metrics']['edge_fp'] == r['category_counts']['OFFICIAL_FP'] == 1
    assert r['metrics']['edge_tp'] == 0


@pytest.mark.parametrize('offset,expected', [(7.,1),(7.000001,0)])
def test_physical_distance_boundary_is_host_owned(offset, expected):
    g = LineageGraph('synthetic',[node('a',0,offset),node('b',1,offset)],[LineageEdge('a','b')])
    result = audit.evaluate_graph(g,truth())
    assert result['metrics']['edge_tp'] == expected


def test_tied_matching_fresh_state_and_pruning_remapping_are_visible():
    g = LineageGraph('synthetic',[node('a',0,0),node('b',1,0),node('c',0,0),node('d',1,0)],
                     [LineageEdge('a','b'),LineageEdge('c','d')])
    first = audit.evaluate_graph(g,truth())
    assert audit.digest(first) == audit.digest(audit.evaluate_graph(g,truth()))
    credited = next(e for e in first['edges'] if e['category']=='OFFICIAL_TP')
    deleted = {credited['source_id'],credited['target_id']}
    pruned = LineageGraph('synthetic',[n for n in g.detections if n.node_id not in deleted],
                          [e for e in g.edges if e.source_id not in deleted])
    second = audit.evaluate_graph(pruned,truth())
    ledger = audit.compare_records(first,second,pruning=True)
    assert len(ledger['shared_node_mapping_changes']) == 2
    assert ledger['counts']['survivor_mapping_changed'] == 1
    assert ledger['counts']['removed_edges'] == 1
    assert ledger['metric_delta']['edge_tp'] == 0
    assert audit.digest(first) == audit.digest(audit.evaluate_graph(g,truth()))


def test_host_filter_drops_are_preserved_not_falsely_penalized():
    g = LineageGraph('synthetic',[node('a',0,100)]+[node(str(i),1,100+i) for i in range(3)],
                     [LineageEdge('a',str(i)) for i in range(3)])
    r = audit.evaluate_graph(g,truth())
    assert r['category_counts']['FILTERED_BY_HOST'] == 1
    assert r['category_counts']['UNEVALUATED_BY_SPARSE_GT'] == 2
    assert r['metrics']['edge_fp'] == 0
    assert any('more than' in w['message'] for w in r['warnings'])


@pytest.mark.parametrize('kind',['duplicate_node','duplicate_edge','missing_endpoint','nonadjacent','nan'])
def test_invalid_predictions_rejected_before_matching(kind,monkeypatch):
    import tracking_cellmot.metrics as host
    monkeypatch.setattr(host,'evaluate',lambda *a,**k:pytest.fail('matching must not happen'))
    g = graph()
    if kind=='duplicate_node':g.detections.append(g.detections[0])
    if kind=='duplicate_edge':g.edges.append(g.edges[0])
    if kind=='missing_endpoint':g.edges=[LineageEdge('absent','b')]
    if kind=='nonadjacent':g.detections[1]=replace(g.detections[1],t=3)
    if kind=='nan':g.detections[0]=replace(g.detections[0],y_um=float('nan'))
    with pytest.raises((audit.EvaluationFailure,ValueError)):
        audit.evaluate_graph(g,truth())


@pytest.mark.parametrize('estimate',[None,0,-1])
def test_invalid_estimate_rejected(estimate):
    gt=replace(truth(),estimated_number_of_nodes=estimate)
    with pytest.raises(audit.EvaluationFailure,match='estimated'):
        audit.evaluate_graph(graph(),gt)


def test_undefined_primary_preserves_cell_evidence(monkeypatch):
    import tracking_cellmot.metrics as host
    original=host.per_sample_metrics
    def explicit_undefined(*a,**kw):
        row=original(*a,**kw)
        row['edge_jaccard']=row['adj_edge_jaccard']=float('nan')
        return row
    monkeypatch.setattr(host,'per_sample_metrics',explicit_undefined)
    with pytest.raises(audit.EvaluationFailure,match='Undefined primary') as caught:
        audit.evaluate_graph(graph(),truth())
    assert caught.value.evidence['metrics']['edge_jaccard'] is None
    assert caught.value.evidence['denominators']['edge']==1


def test_empty_host_graph_failure_is_preserved_without_fabricating_metrics():
    with pytest.raises(audit.EvaluationFailure) as caught:
        audit.evaluate_graph(LineageGraph('synthetic',[],[]),SparseGroundTruthGraph('synthetic',[],[],1))
    assert caught.value.evidence['input_mutated'] is False


def test_node_estimate_does_not_clip_adjusted_metric():
    r=audit.evaluate_graph(graph(),replace(truth(),estimated_number_of_nodes=4))
    assert r['metrics']['adjusted_edge_jaccard']==pytest.approx(1.05)


def test_mutation_during_host_call_is_detected(monkeypatch):
    import tracking_cellmot.metrics as host
    original=host.evaluate
    g=graph()
    def mutation(*a,**kw):
        result=original(*a,**kw)
        g.edges[0]=replace(g.edges[0],confidence=.2)
        return result
    monkeypatch.setattr(host,'evaluate',mutation)
    with pytest.raises(audit.EvaluationFailure,match='mutated') as caught:
        audit.evaluate_graph(g,truth())
    assert caught.value.evidence['input_mutated']


def test_full_decode_preserves_order_and_rejects_sanitization():
    payload=asdict(graph())
    assert asdict(audit.decode_graph(payload,'synthetic',audit.digest(payload)))==payload
    payload['detections'][0]['unexpected']='must not be dropped'
    with pytest.raises(TypeError):audit.decode_graph(payload,'synthetic',audit.digest(payload))


def test_confidence_only_change_and_pruning_attribute_guard():
    before=audit.evaluate_graph(graph(),truth())
    g=graph();g.edges[0]=replace(g.edges[0],confidence=.3)
    after=audit.evaluate_graph(g,truth())
    assert audit.compare_records(before,after)['counts']['confidence_only_changed']==1
    with pytest.raises(RuntimeError,match='attributes'):audit.compare_records(before,after,pruning=True)


def test_lost_credit_and_new_fp_reconcile_even_for_shared_edge_identity():
    before=audit.evaluate_graph(graph(),truth())
    g=graph();g.detections[1]=node('b',1,100)
    after=audit.evaluate_graph(g,truth())
    ledger=audit.compare_records(before,after)
    assert ledger['counts']['lost_GT_credit']==1
    assert ledger['counts']['newly_penalized_FP']==1
    assert ledger['counts']['added_edges']==ledger['counts']['removed_edges']==0
    assert ledger['category_transitions']=={'OFFICIAL_TP->OFFICIAL_FP':1}
    assert ledger['metric_delta']['edge_tp']==-1 and ledger['metric_delta']['edge_fn']==1


def test_existing_geff_reader_converts_voxels_once_before_matching(tmp_path,monkeypatch):
    import json
    import numpy as np
    import zarr
    from atabey.io.geff_reader import read_geff_graph
    base=tmp_path/'synthetic.geff';base.mkdir()
    (base/'zarr.json').write_text(json.dumps({'attributes':{'geff':{'extra':{'estimated_number_of_nodes':2}}}}))
    arrays={'nodes/ids':[10,11], 'nodes/props/t/values':[0,1], 'nodes/props/z/values':[0,0],
            'nodes/props/y/values':[16,16], 'nodes/props/x/values':[0,0], 'edges/ids':[[10,11]]}
    def explicit_array(path,mode):
        assert mode=='r'
        from pathlib import Path
        return np.array(arrays[Path(path).relative_to(base).as_posix()])
    monkeypatch.setattr(zarr,'open',explicit_array)
    gt=read_geff_graph(base)
    assert [n.y_um for n in gt.nodes]==[6.5,6.5]
    assert audit.evaluate_graph(graph(),gt)['metrics']['edge_tp']==1


def test_official_summary_weighting_and_missing_rows():
    a=audit.evaluate_graph(graph(),truth())
    b=deepcopy(a);b['sample_id']='synthetic-second'
    b['metrics'].update(edge_tp=1,edge_fn=2,edge_jaccard=1/3,adjusted_edge_jaccard=1/3)
    s=audit.summarize_records([a,b],2)['metrics']
    assert s['edge_jaccard']==pytest.approx(.5)
    assert s['adjusted_edge_jaccard']==pytest.approx(.5)
    with pytest.raises(RuntimeError,match='Incomplete'):audit.summarize_records([a],2)
    with pytest.raises(RuntimeError,match='Duplicate'):audit.summarize_records([a,a],2)
    b['metrics']['adjusted_edge_jaccard']=None
    with pytest.raises(RuntimeError,match='Undefined'):audit.summarize_records([a,b],2)


def test_interactions_null_propagation_and_anchor_tolerances():
    arms={a:{'x':v,'undefined':None} for a,v in [('H',0),('M0',1),('M1',4),('S0',3),('S1',5)]}
    assert audit.interaction(arms)=={'x':-1,'undefined':None}
    audit.verify_historical({'x':.1+1e-13,'i':1,'n':None},{'x':.1,'i':1,'n':None})
    for got,expected in [({'x':.1+1e-10},{'x':.1}),({'i':1.0},{'i':1}),({'n':0},{'n':None})]:
        with pytest.raises(RuntimeError):audit.verify_historical(got,expected)
