from __future__ import annotations
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import zarr

from atabey.submission import v28
from atabey.submission.writer import KAGGLE_SUBMISSION_COLUMNS
from atabey.types import LineageEdge

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v28_runner',ROOT/'scripts/run_v28_submission.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def make_sample(directory,sid='6bba_explicit_synthetic',shape=(2,4,4,4)):
    path=directory/(sid+'.zarr')
    group=zarr.open_group(str(path),mode='w')
    group.create_array('0',data=np.zeros(shape,dtype=np.uint16),chunks=(1,*shape[1:]))
    group.attrs.update({'multiscales':[{'axes':[{'name':n,'unit':'second' if n=='t' else 'micrometer'} for n in 'tzyx'],'datasets':[{'path':'0','coordinateTransformations':[{'type':'scale','scale':[1,1.625,.40625,.40625]}]}]}],'image_statistics':{'quantiles':{'0.001':0,'0.999':100}}})
    return path


def simple_graph(sid='sample'):
    return v28.build_graph(sid,[[0,1,1,1],[1,1,1,1]],False)[0]


def csv_fixture(tmp_path):
    graph=simple_graph();text,record=v28.export_graph(graph,(2,4,4,4),0)
    p=tmp_path/'out.csv';p.write_text(','.join(KAGGLE_SUBMISSION_COLUMNS)+'\n'+text)
    return p,record


def test_streamed_roundtrip_uses_ten_columns_and_matches_graph(tmp_path):
    path,record=csv_fixture(tmp_path)
    assert v28.validate_csv(path,[record])['rows']==3
    assert record['rounded_nodes']==0


@pytest.mark.parametrize('mutation',[
    lambda s:s.replace('id,dataset','bad,dataset',1),
    lambda s:s.replace('0,sample,node','9,sample,node',1),
    lambda s:s.replace('0,sample,node','0,other,node',1),
    lambda s:s.replace('node,1,0,1,1,1','node,1,0,100,1,1',1),
    lambda s:s.replace('node,1,0,1,1,1','node,1,0,1.0,1,1',1),
    lambda s:s.replace('edge,-1,-1,-1,-1,-1,1,2','edge,-1,-1,-1,-1,-1,1,99'),
    lambda s:s.replace('edge,-1,-1,-1,-1,-1,1,2','edge,-1,-1,-1,-1,-1,2,1'),
    lambda s:s.replace('edge,-1,-1,-1,-1,-1,1,2','edge,0,-1,-1,-1,-1,1,2'),
    lambda s:s.replace('node,2,1,1,1,1','node,1,1,1,1,1'),
    lambda s:s.replace('node,2,1,1,1,1','node,2,1,2,1,1'),
    lambda s:s.replace('sample,node','sample,wrong',1),
    lambda s:'\n'.join(s.splitlines()[:-1])+'\n',
    lambda s:s+s.splitlines()[-1]+'\n',
])
def test_malformed_or_changed_csv_is_rejected(tmp_path,mutation):
    path,record=csv_fixture(tmp_path);path.write_text(mutation(path.read_text()))
    with pytest.raises(ValueError):v28.validate_csv(path,[record])


@pytest.mark.parametrize('problem',['duplicate_node','duplicate_edge','missing_endpoint','backward_edge','nonfinite','out_of_bounds','rounded_out_of_bounds','wrong_sample','nonintegral_time','empty'])
def test_invalid_internal_graph_never_exports(problem):
    g=simple_graph()
    if problem=='duplicate_node':g.detections.append(g.detections[0])
    if problem=='duplicate_edge':g.edges.append(g.edges[0])
    if problem=='missing_endpoint':g.edges=[LineageEdge('absent',g.detections[1].node_id)]
    if problem=='backward_edge':g.edges=[LineageEdge(g.detections[1].node_id,g.detections[0].node_id)]
    if problem in ['nonfinite','out_of_bounds','rounded_out_of_bounds']:g.detections[0]=replace(g.detections[0],x={'nonfinite':float('nan'),'out_of_bounds':4,'rounded_out_of_bounds':3.9}[problem])
    if problem=='wrong_sample':g.detections[0]=replace(g.detections[0],sample_id='other')
    if problem=='nonintegral_time':g.detections[0]=replace(g.detections[0],t=.5)
    if problem=='empty':g.detections=[];g.edges=[]
    with pytest.raises(ValueError):v28.export_graph(g,(2,4,4,4),0)


def test_rounding_is_reported_and_python_tie_convention_preserved():
    g=simple_graph();g.detections[0]=replace(g.detections[0],x=2.5)
    text,record=v28.export_graph(g,(2,4,4,4),0)
    assert text.splitlines()[0].split(',')[7]=='2'
    assert record['rounded_nodes']==1


def test_exact_pruning_changes_only_enabled_graph():
    coords=[[0,0,0,200],[1,0,0,0],[2,0,0,0],[3,0,200,200]]
    raw,_=v28.build_graph('6bba_example',coords,False)
    pruned,_=v28.build_graph('6bba_example',coords,True)
    assert len(raw.detections)==4 and len(raw.edges)==1
    assert len(pruned.detections)==2 and not pruned.edges


@pytest.mark.parametrize('sid,expected',[('6bba_new_hidden_id',True),('44b6_new_hidden_id',False),('new_family',False)])
def test_pruning_route_is_metadata_based_not_training_whitelist(tmp_path,sid,expected):
    path=make_sample(tmp_path,sid)
    assert v28.route_for_sample(path)['apply_pruning']==expected


def test_merged_6bba_route_not_pruned(tmp_path,monkeypatch):
    from atabey.detection.adaptive import ForegroundProfile,choose_adaptive_baseline_settings
    profile=ForegroundProfile((0,1),200000,.1,2,2)
    settings=choose_adaptive_baseline_settings(profile)
    assert settings.detector=='local_maxima'
    monkeypatch.setattr(v28,'choose_settings_for_sample',lambda p:(profile,settings))
    assert not v28.route_for_sample(tmp_path/'6bba_explicit_synthetic.zarr')['apply_pruning']


@pytest.mark.parametrize('problem',['axes','scale','quantiles','equal_quantiles','single_frame'])
def test_bad_metadata_stops_before_inference(tmp_path,problem):
    path=make_sample(tmp_path,shape=(1,4,4,4) if problem=='single_frame' else (2,4,4,4))
    g=zarr.open_group(str(path),mode='a');attrs=dict(g.attrs)
    if problem=='axes':attrs['multiscales'][0]['axes'].reverse()
    if problem=='scale':attrs['multiscales'][0]['datasets'][0]['coordinateTransformations'][0]['scale'][1]=1
    if problem=='quantiles':attrs['image_statistics']['quantiles'].pop('0.999')
    if problem=='equal_quantiles':attrs['image_statistics']['quantiles']['0.999']=0
    g.attrs.update(attrs)
    with pytest.raises(ValueError):v28.inspect_sample(path)


def test_full_discovery_and_fail_closed_partial_file(tmp_path):
    test=tmp_path/'test';make_sample(test,'44b6_a');make_sample(test,'6bba_b')
    output=tmp_path/'output';output.mkdir();calls=[]
    def explicit_fake_predictor(path):
        calls.append(path.stem)
        if len(calls)==2:raise RuntimeError('explicit synthetic inference failure')
        return [[0,1,1,1],[1,1,1,1]],{'inference_seconds':0,'peak_gpu_allocated_bytes':0}
    with pytest.raises(RuntimeError):runner.write_test_submission(test,output,explicit_fake_predictor)
    assert calls==['44b6_a','6bba_b']
    assert (output/'submission.partial.csv').exists()
    assert not (output/'submission.csv').exists()


def test_complete_split_validates_cumulative_ids_without_publishing(tmp_path):
    test=tmp_path/'test';make_sample(test,'44b6_a');make_sample(test,'6bba_b');output=tmp_path/'out';output.mkdir()
    def explicit_fake_predictor(path):return [[0,1,1,1],[1,1,1,1]],{'inference_seconds':.01,'peak_gpu_allocated_bytes':0}
    result=runner.write_test_submission(test,output,explicit_fake_predictor)
    assert result['csv_validation']['samples']==2 and result['csv_validation']['rows']==6
    assert not (output/'submission.csv').exists()


def test_no_samples_and_existing_outputs_are_not_success(tmp_path):
    with pytest.raises(ValueError):v28.discover_samples(tmp_path)
    test=tmp_path/'test';make_sample(test);out=tmp_path/'out';out.mkdir();(out/'submission.csv').write_text('preserve')
    with pytest.raises(ValueError):runner.write_test_submission(test,out,None)
    assert (out/'submission.csv').read_text()=='preserve'


@pytest.mark.parametrize('change',[{'status':'PROPOSED'},{'package_manifest_sha256':'other'},{'scope':'V28_SUBMISSION'},{'authority':'Codex'},{'reviewer':None},{'record':None}])
def test_approval_is_exact_package_and_scope(change):
    receipt={'status':'APPROVED','package_manifest_sha256':'fake_fixture','scope':'V28_VALIDATION','authority':'Danny','reviewer':'Danny','builder':'Codex','record':'explicit synthetic unit-test receipt'}
    runner.validate_receipt(receipt,'fake_fixture','validation')
    receipt.update(change)
    with pytest.raises(ValueError):runner.validate_receipt(receipt,'fake_fixture','validation')


def test_manifest_refuses_mutated_or_escaping_files(tmp_path):
    p=tmp_path/'x';p.write_text('known');expected=runner.sha_file(p)
    runner.verify_files(tmp_path,{'x':expected});p.write_text('changed')
    with pytest.raises(ValueError):runner.verify_files(tmp_path,{'x':expected})
    with pytest.raises(ValueError):runner.verify_files(tmp_path,{'../escape':expected})


def test_cli_refuses_unapproved_execution_without_importing_predictor(tmp_path):
    import subprocess
    receipt=tmp_path/'receipt.json';receipt.write_text(json.dumps({'status':'NOT_APPROVED'}))
    package=tmp_path/'package';package.mkdir();(package/'package_manifest.json').write_text('{}')
    output=tmp_path/'out'
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/run_v28_submission.py'),'--package-root',str(package),'--support-root',str(tmp_path),'--weights',str(tmp_path/'missing.pth'),'--data-root',str(tmp_path),'--output-dir',str(output),'--receipt',str(receipt),'--mode','validation'],capture_output=True,text=True)
    assert proc.returncode!=0
    failure=json.loads((output/'FAILURE.json').read_text())
    assert 'not been approved' in failure['message']
    assert not (output/'submission.csv').exists()


def test_no_cuda_stops_before_loading_external_predictor(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:False)))
    with pytest.raises(ValueError,match='CUDA'):
        runner.load_predictor(tmp_path,tmp_path/'weights',{})


def test_missing_pinned_dependency_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='identity'):
        runner.verify_files(tmp_path,{'missing.py':'0'*64})


def test_runtime_projection_names_assumptions_and_does_not_claim_hidden_validation():
    record={'shape':[100,64,256,256],'route':{'seconds':2},'inference_seconds':30,'linking_seconds':1,'pruning_seconds':1,'export_seconds':1}
    parity={'inference_records':[record],'route_records':[record]*199}
    visible={'samples':[record],'csv_validation_seconds':1}
    result=runner.runtime_projection(parity,visible,90)
    assert result['measured_work_multiplier']==2 and result['passes']
    assert not result['hidden_runtime_verified']
    record['inference_seconds']=600
    assert not runner.runtime_projection(parity,visible,90)['passes']
