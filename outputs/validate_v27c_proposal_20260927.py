"""Independent read-only proposal checks; no cohort matching or metric calls."""
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def load(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()

def canonical(p):
    return hashlib.sha256((ROOT / p).read_bytes().replace(b'\r\n',b'\n').replace(b'\r',b'\n')).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def verify(item):
    assert (ROOT / item['path']).stat().st_size == item['bytes'], item['path']
    assert sha(item['path']) == item['sha256'], item['path']

contract_path = 'tests/fixtures/v27c_official_graph_evaluation.json'
c = load(contract_path)
assert c['status'] == 'PROPOSED'
assert c['review'] is c['human_execution_authorization'] is None
assert not c['authorization']['execution_ready']
assert c['authorization']['implementation_payload'] is None
assert canonical(c['protocol']['path']) == c['protocol']['canonical_sha256']
assert c['arms'] == ['H','M0','M1','S0','S1'] and c['stages'] == ['RAW','P2','P3']
assert c['evaluation']['max_distance_um'] == 7.0
assert c['evaluation']['scale'] is None
assert c['evaluation']['complete_passes'] == 2
assert c['evaluation']['expected_cell_evaluations'] == 480
assert c['evaluation']['distinct_graph_count'] == 240
assert c['evaluation']['primary_diagnostic_endpoint'] == 'adjusted_edge_jaccard'
assert c['evaluation']['expected_summary_count'] == 15
assert c['evaluation']['expected_samples_per_summary'] == 16
assert c['evaluation']['ledger_from_same_matched_state']
assert not c['evaluation']['reuse_archived_matching']
assert len(c['paired_contrasts']) == 8
assert len({(r['before'],r['after']) for r in c['paired_contrasts']}) == 8
assert c['pruning_contrasts'] == [['RAW','P2'],['P2','P3'],['RAW','P3']]
assert c['ledger']['edge_categories'] == ['OFFICIAL_TP','OFFICIAL_FP','UNEVALUATED_BY_SPARSE_GT','FILTERED_BY_HOST']
for key in ['tracking_replay','pruning_rerun','inference','training','threshold_search',
            'arm_selection','production_promotion','submission','independent_validation_claim',
            'v26a_gate_recalculation']:
    assert c['boundaries'][key] is False
for item in c['inputs'].values():
    verify(item)
parent = load(c['inputs']['v27b_contract']['path'])
result = load(c['inputs']['v27b_result']['path'])
assert c['inputs']['v27b_inventory']['sha256'] == result['artifact_inventory']['sha256']
assert c['inputs']['v27b_freeze_copy']['sha256'] == c['inputs']['v27b_approved_manifest']['sha256']
assert c['cohort'] == parent['cohort']
assert len(c['cohort']['sample_ids']) == len(set(c['cohort']['sample_ids'])) == 16
for table in ['parent_source_canonical_sha256','reference_evaluation_source_canonical_sha256']:
    for path,expected in c[table].items():
        assert canonical(path) == expected,path
assert c['parent_source_canonical_sha256'] == load(c['inputs']['v27b_approved_manifest']['path'])['payload']['canonical_sources']
for item in c['parent_pass_summaries']:
    verify(item)
assert len(c['parent_pass_summaries']) == 32

matrix = list(itertools.product(c['cohort']['sample_ids'],c['arms'],c['stages']))
assert [(g['sample_id'],g['arm'],g['stage']) for g in c['graph_inputs']] == matrix
graphs = {}
inventory = {x['path']:x for x in load(c['inputs']['v27b_inventory']['path'])['files']}
base = Path(c['inputs']['v27b_inventory']['path']).parent
for item in c['graph_inputs']:
    key = (item['sample_id'],item['arm'],item['stage'])
    for copy in ['evaluation_input','parent_replay_copy']:
        identity = item[copy]
        verify(identity)
        old = inventory[Path(identity['path']).relative_to(base).as_posix()]
        assert (old['bytes'],old['sha256']) == (identity['bytes'],identity['sha256'])
    assert item['evaluation_input']['sha256'] == item['parent_replay_copy']['sha256']
    with gzip.open(ROOT / item['evaluation_input']['path'],'rt',encoding='utf-8') as f:
        g = json.load(f)
    assert digest(g) == item['full_graph_sha256']
    assert g['sample_id'] == item['sample_id']
    nodes = {n['node_id']:n for n in g['detections']}
    edges = {(e['source_id'],e['target_id']):e for e in g['edges']}
    assert len(nodes) == len(g['detections']) and len(edges) == len(g['edges'])
    assert all(n['sample_id']==item['sample_id'] and all(math.isfinite(n[a]) for a in ['z_um','y_um','x_um']) for n in nodes.values())
    assert all(s in nodes and t in nodes and nodes[t]['t']-nodes[s]['t']==1 for s,t in edges)
    graphs[key] = (nodes,edges)
    if item['arm']=='H':
        assert item['historical_graph_sha256']==parent['anchors']['samples'][item['sample_id']]['r_h_graph_signatures'][item['stage']]
    if item['arm']=='S1' and item['stage']=='P3':
        assert item['historical_graph_sha256']==parent['anchors']['samples'][item['sample_id']]['r_s1_p3_sha256']
for sid,arm in itertools.product(c['cohort']['sample_ids'],c['arms']):
    for before,after in c['pruning_contrasts']:
        nb,eb=graphs[(sid,arm,before)];na,ea=graphs[(sid,arm,after)]
        assert na.keys() <= nb.keys() and ea.keys() <= eb.keys()
        assert all(n==nb[k] for k,n in na.items())
        assert all(e==eb[k] for k,e in ea.items())
assert [g['sample_id'] for g in c['ground_truth']] == c['cohort']['sample_ids']
for gt in c['ground_truth']:
    root = ROOT / gt['path']
    actual_paths = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
    assert actual_paths == [r['path'] for r in gt['files']]
    assert digest(gt['files']) == gt['tree_sha256']
    assert len(actual_paths) == gt['file_count']
    for item in gt['files']:
        verify(dict(item,path=gt['path']+'/'+item['path']))
    geff = load(gt['path']+'/zarr.json')['attributes']['geff']
    assert geff['extra']['estimated_number_of_nodes'] == gt['estimated_number_of_nodes'] > 0
    assert geff['axes'] == gt['axes']
    assert [a['scale'] for a in gt['axes']] == [1.,1.625,.40625,.40625]

assert len(c['historical_metric_anchors']['per_sample']) == 16
for row in c['historical_metric_anchors']['per_sample']:
    assert row['sample_id'] in c['cohort']['sample_ids']
    for key in ['H_P3_metric','S1_P3_metric']:
        assert set(row[key]) == set(c['evaluation']['metrics'])

report = {
    'status':'PROPOSAL_INPUT_AND_DESIGN_CHECKS_PASSED',
    'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
    'builder':'Codex','independent_reviewer':None,
    'repository_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'contract':{'path':contract_path,'sha256':sha(contract_path),'bytes':(ROOT/contract_path).stat().st_size},
    'protocol':c['protocol'],
    'validator':{'path':'outputs/validate_v27c_proposal_20260927.py','sha256':sha('outputs/validate_v27c_proposal_20260927.py')},
    'checks':{'distinct_graphs_verified':len(graphs),'physical_graph_copies_verified':480,
              'parent_pass_summaries_verified':32,'parent_source_identities_verified':len(c['parent_source_canonical_sha256']),
              'ground_truth_trees_verified':16,'ground_truth_files_verified':sum(g['file_count'] for g in c['ground_truth']),
              'ground_truth_metadata_estimates_positive':16,'pruning_subset_and_attribute_comparisons_verified':240,
              'historical_H_graph_anchors_verified':48,'historical_S1_P3_graph_anchors_verified':16,
              'historical_metric_values_recorded_without_new_scoring':32,
              'scope_and_null_authorization_verified':True},
    'not_performed':['cohort_matching','cohort_scoring','evaluator_implementation','implementation_tests',
                     'human_review','execution_freeze','scientific_run','independent_validation'],
    'execution_ready':False,
}
with (ROOT/'v27c_contract_validation_20260927.json').open('x',encoding='utf-8',newline='\n') as f:
    json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps(report,indent=2),flush=True)
