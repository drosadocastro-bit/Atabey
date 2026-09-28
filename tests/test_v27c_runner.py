from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v27c_official_graph_evaluation as runner
from atabey.evaluation import frozen_graph_audit as audit
from test_v27c_frozen_graph_audit import graph, truth


@pytest.fixture
def fake_freeze(tmp_path,monkeypatch):
    """Explicit synthetic authority/evidence, never an approval of cohort work."""
    c=runner.science_contract(ROOT)
    root=tmp_path/'repo';root.mkdir()
    for relative in runner.required_sources(ROOT,c):
        dst=root/relative;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/relative,dst)
    monkeypatch.setattr(runner,'runtime_identity',lambda:c['observed_runtime_reference'])
    monkeypatch.setattr(runner,'host_identity',lambda c:{'explicit_synthetic_host':True})
    monkeypatch.setattr(runner,'verify_evidence',lambda c,r:{'explicit_synthetic_inputs':True})
    report=root/'synthetic.xml'
    report.write_text('<testsuite><testcase name="explicit_fake"/></testsuite>')
    m=runner.prepare_candidate(root,report)
    assert m['status']=='READY_FOR_HUMAN_REVIEW' and m['review'] is None
    m['status']='FROZEN';pin=m['payload_sha256']
    m['review']={'reviewer':'explicit_fake_reviewer','record':'synthetic only','reviewed_payload_sha256':pin}
    m['human_execution_authorization']={'authority':'explicit_fake_authority','record':'synthetic only',
                                      'scope':runner.SCOPE,'approved_payload_sha256':pin}
    return root,m


def test_exact_explicit_fake_freeze_validates(fake_freeze):
    root,m=fake_freeze
    assert runner.validate_freeze(m,root)['scope']==runner.SCOPE


@pytest.mark.parametrize('change,pattern',[
    ('proposal','not FROZEN'),('review','Missing human'),('authority','Missing human'),
    ('builder','Distinct reviewer'),('wrong_scope','exact V27C'),('stale_review','Distinct reviewer'),
    ('stale_authority','exact V27C'),('payload','integrity/scope'),('omitted_source','source closure'),
    ('source','Frozen source'),('report','Test evidence'),('contract','contract identity')])
def test_freeze_rejects_drift_and_wrong_authority(fake_freeze,change,pattern):
    root,m=fake_freeze
    if change=='proposal':m['status']='READY_FOR_HUMAN_REVIEW'
    if change=='review':m['review']=None
    if change=='authority':m['human_execution_authorization']=None
    if change=='builder':m['review']['reviewer']=m['payload']['builder']
    if change=='wrong_scope':m['human_execution_authorization']['scope']='V27B_RECURSIVE_HISTORY_AND_PRUNING_RESPONSE'
    if change=='stale_review':m['review']['reviewed_payload_sha256']='stale'
    if change=='stale_authority':m['human_execution_authorization']['approved_payload_sha256']='stale'
    if change=='payload':m['payload']['builder']='tampered'
    if change=='omitted_source':
        m['payload']['canonical_sources'].pop('src/atabey/evaluation/frozen_graph_audit.py')
        pin=audit.digest(m['payload']);m['payload_sha256']=pin
        m['review']['reviewed_payload_sha256']=pin;m['human_execution_authorization']['approved_payload_sha256']=pin
    if change=='source':(root/'src/atabey/evaluation/frozen_graph_audit.py').write_text('tampered')
    if change=='report':(root/'synthetic.xml').write_text('<testsuite><testcase name="changed"/></testsuite>')
    if change=='contract':(root/runner.CONTRACT).write_text('{}')
    with pytest.raises(RuntimeError,match=pattern):runner.validate_freeze(m,root)


@pytest.mark.parametrize('kind',['runtime','host','inputs'])
def test_freeze_rejects_environment_or_evidence_drift(fake_freeze,monkeypatch,kind):
    root,m=fake_freeze
    name={'runtime':'runtime_identity','host':'host_identity','inputs':'verify_evidence'}[kind]
    monkeypatch.setattr(runner,name,lambda *args:{'changed':True})
    with pytest.raises(RuntimeError):runner.validate_freeze(m,root)


@pytest.mark.parametrize('element',['failure','error','skipped'])
def test_nonpassing_or_skipped_tests_cannot_prepare(tmp_path,element):
    p=tmp_path/'tests.xml';p.write_text(f'<testsuite><testcase><{element}/></testcase></testsuite>')
    with pytest.raises(RuntimeError,match='zero skips'):runner.test_report_identity(p)


def test_empty_test_report_rejected(tmp_path):
    p=tmp_path/'tests.xml';p.write_text('<testsuite tests="999"/>')
    with pytest.raises(RuntimeError):runner.test_report_identity(p)


def test_unsafe_path_and_raw_input_changes_rejected(tmp_path):
    with pytest.raises(RuntimeError,match='escapes'):runner.safe_path(tmp_path,'../escape')
    p=tmp_path/'input';p.write_text('abc')
    c={'inputs':{'synthetic':{'path':'input','bytes':3,'sha256':runner.sha256_file(p)}},'parent_pass_summaries':[]}
    p.write_text('abd')
    with pytest.raises(RuntimeError,match='Input identity'):runner.verify_evidence(c,tmp_path)


def test_rejected_real_entry_preserves_failure_and_never_calls_evaluator(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'evaluate_graph',lambda *a:pytest.fail('cohort evaluation forbidden'))
    p=tmp_path/'proposal.json';runner.write_new(p,{'status':'PROPOSED'})
    output=tmp_path/'attempt'
    with pytest.raises(RuntimeError,match='not FROZEN'):
        runner.execute(p,runner.sha256_file(p),output)
    failure=runner.read_json(output/'invalid_execution.json')
    assert failure['completed_cells']==[]
    assert (output/'artifact_inventory.json').exists()
    with pytest.raises(FileExistsError):runner.execute(p,runner.sha256_file(p),output)


def test_entry_requires_exact_manifest_digest(tmp_path):
    p=tmp_path/'freeze.json';runner.write_new(p,{'status':'FROZEN'})
    with pytest.raises(RuntimeError,match='approved freeze SHA'):runner.execute(p,'',tmp_path/'attempt')


def test_source_closure_includes_new_instrument_and_parent_sources():
    c=runner.science_contract(ROOT)
    paths=runner.required_sources(ROOT,c)
    assert set(c['parent_source_canonical_sha256']) <= paths
    assert {'src/atabey/evaluation/frozen_graph_audit.py',runner.CONTRACT,
            'scripts/run_v27c_official_graph_evaluation.py','tests/test_v27c_runner.py',
            'src/atabey/io/geff_reader.py','src/atabey/evaluation/official_division_metric.py'} <= paths


@pytest.fixture
def synthetic_run(tmp_path,monkeypatch):
    """Real orchestration and aggregation, explicitly substituted synthetic cells."""
    c=deepcopy(runner.science_contract(ROOT))
    c['cohort']={'sample_ids':['synthetic'],'sample_count':1}
    c['evaluation']['expected_cell_evaluations']=30
    c['graph_inputs']=[{'sample_id':'synthetic','arm':a,'stage':t,'evaluation_input':{'path':'synthetic'}}
                       for a in c['arms'] for t in c['stages']]
    c['ground_truth']=[{'sample_id':'synthetic','path':'synthetic.geff','estimated_number_of_nodes':2}]
    cell=audit.evaluate_graph(graph(),truth())
    aggregate=audit.summarize_records([cell],1)['metrics']
    c['historical_metric_anchors']={'per_sample':[{'sample_id':'synthetic','H_P3_metric':cell['metrics'],
        'S1_P3_metric':cell['metrics']}],'H_P3_summary':aggregate,'S1_P3_summary':aggregate}
    monkeypatch.setattr(runner,'validate_freeze',lambda *a:c)
    monkeypatch.setattr(runner,'read_graph',lambda *a:graph())
    monkeypatch.setattr(runner,'read_geff_graph',lambda *a:truth())
    monkeypatch.setattr(runner,'evaluate_graph',lambda *a:deepcopy(cell))
    p=tmp_path/'explicit_synthetic_freeze.json'
    runner.write_new(p,{'payload':{'inputs':{'explicit_synthetic_substitutions':True}}})
    return p,tmp_path/'run',cell


def test_full_synthetic_orchestration_replays_ledgers_and_aggregates(synthetic_run):
    p,output,cell=synthetic_run
    result=runner.execute(p,runner.sha256_file(p),output)
    assert result['status']=='VALID_RETROSPECTIVE_EVALUATION_RESULT'
    assert result['completed_evaluations']==30
    assert len(result['result']['host_summaries'])==15
    assert len(result['result']['comparisons'])==39
    for path in (output/'pass1').rglob('*'):
        if path.is_file():assert path.read_bytes()==(output/'pass2'/path.relative_to(output/'pass1')).read_bytes()
    assert not (output/'invalid_execution.json').exists()


def test_second_pass_divergence_stops_and_retains_partial_evidence(synthetic_run,monkeypatch):
    p,output,cell=synthetic_run
    calls=[]
    def changed(*a):
        calls.append(1);r=deepcopy(cell)
        if len(calls)>15:r['warnings'].append({'category':'explicit_fake','message':'changed pass'})
        return r
    monkeypatch.setattr(runner,'evaluate_graph',changed)
    with pytest.raises(RuntimeError,match='replay mismatch'):
        runner.execute(p,runner.sha256_file(p),output)
    failure=runner.read_json(output/'invalid_execution.json')
    assert len(failure['completed_cells'])==15
    assert failure['active_context']['pass']==2
    assert (output/'pass2/synthetic/H.RAW.json.gz').exists()


def test_failing_cell_diagnostics_persist(synthetic_run,monkeypatch):
    p,output,cell=synthetic_run
    def failed(*a):raise audit.EvaluationFailure('explicit_fake_failure',{'metrics':{'edge_jaccard':None}})
    monkeypatch.setattr(runner,'evaluate_graph',failed)
    with pytest.raises(audit.EvaluationFailure):runner.execute(p,runner.sha256_file(p),output)
    assert (output/'failing_cell.json.gz').exists()
    assert runner.read_json(output/'invalid_execution.json')['completed_cells']==[]
