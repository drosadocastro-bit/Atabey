"""Record proposal identities only. Never import or call the cohort evaluator."""
import gzip
import hashlib
import importlib.metadata as metadata
import json
import platform
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1048576):
            h.update(chunk)
    return h.hexdigest()

def identity(relative):
    path = ROOT / relative
    return {'path': relative, 'bytes': path.stat().st_size, 'sha256': sha(path)}

def canonical(relative):
    return hashlib.sha256((ROOT / relative).read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')).hexdigest()

def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))

def write_new(relative, value):
    with (ROOT / relative).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')

parent = read('tests/fixtures/v27b_recursive_history.json')
approved = read('v27b_freeze_approved_20260924.json')
result = read('v27b_recursive_history_results.json')
assert result['status'] == 'VALID_RECURSIVE_MECHANISM_RESULT'
assert sha(ROOT / 'v27b_freeze_approved_20260924.json') == '6f7e35cb652f9d95f4de47f7c13bcde49bdfe04ed6a2b7504c5edb6e8fda7847'
assert sha(ROOT / 'v27b_recursive_history_results.json') == '27a6c91a4f583e6dd7ef0732048c67945c08b42cba6f6c8118621d86ef86f9be'
for path, expected in approved['payload']['canonical_sources'].items():
    assert canonical(path) == expected, path

samples = parent['cohort']['sample_ids']
arms = ['H', 'M0', 'M1', 'S0', 'S1']
stages = ['RAW', 'P2', 'P3']
base = 'outputs/v27b_frozen_20260924'
inventory = read(base + '/artifact_inventory.json')
files = {r['path']: r for r in inventory['files']}
graphs = []
summaries = []
for sid in samples:
    passes = {}
    for pass_id in (1, 2):
        relative = f'{sid}.pass{pass_id}/summary.json'
        item = identity(f'{base}/{relative}')
        assert {k:item[k] for k in ('bytes','sha256')} == {k:files[relative][k] for k in ('bytes','sha256')}
        summaries.append(item)
        passes[pass_id] = read(item['path'])
    assert passes[1]['graph_signatures'] == passes[2]['graph_signatures']
    for arm in arms:
        for stage in stages:
            copies = []
            for pass_id in (1, 2):
                relative = f'{sid}.pass{pass_id}/{arm}.{stage}.json.gz'
                item = identity(f'{base}/{relative}')
                assert {k:item[k] for k in ('bytes','sha256')} == {k:files[relative][k] for k in ('bytes','sha256')}
                with gzip.open(ROOT / item['path'], 'rt', encoding='utf-8') as f:
                    graph = json.load(f)
                assert graph['sample_id'] == sid
                assert digest(graph) == passes[pass_id]['graph_signatures'][arm][stage]['full_sha256']
                copies.append(item)
            assert copies[0]['sha256'] == copies[1]['sha256']
            graphs.append({'sample_id': sid, 'arm': arm, 'stage': stage,
                           'full_graph_sha256': digest(graph),
                           'historical_graph_sha256': passes[1]['graph_signatures'][arm][stage]['historical_sha256'],
                           'evaluation_input': copies[0], 'parent_replay_copy': copies[1]})

ground_truth = []
for sid in samples:
    relative = f'train/{sid}.geff'
    path = ROOT / relative
    records = [{'path': p.relative_to(path).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
               for p in sorted(path.rglob('*')) if p.is_file()]
    records.sort(key=lambda r:r['path'])
    geff = read(relative + '/zarr.json')['attributes']['geff']
    axes = geff['axes']
    assert [a['name'] for a in axes] == ['t', 'z', 'y', 'x']
    assert [a['scale'] for a in axes] == [1.0, 1.625, .40625, .40625]
    assert all(a.get('offset') in (None, 0, 0.0) for a in axes)
    estimate = geff['extra']['estimated_number_of_nodes']
    assert isinstance(estimate, int) and estimate > 0
    ground_truth.append({'sample_id': sid, 'path': relative, 'files': records,
                         'file_count': len(records), 'tree_sha256': digest(records),
                         'estimated_number_of_nodes': estimate,
                         'axes': axes})

host = {}
for dist_name, module, commit in [
    ('tracking-cellmot', 'tracking_cellmot', '075fc5f5a52d11077f9dc2b074644618f26939e2'),
    ('tracksdata', 'tracksdata', '39dccf3a243e44274759468cb31b2ad9e7fc1d09')]:
    dist = metadata.distribution(dist_name)
    direct = json.loads(dist.read_text('direct_url.json'))
    assert direct['vcs_info']['commit_id'] == commit
    module_root = Path(dist.locate_file(module))
    sources = [{'path': p.relative_to(module_root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
               for p in sorted(module_root.rglob('*.py'))]
    host[dist_name] = {'module':module, 'version':dist.version, 'commit':commit,
                       'direct_url':direct, 'source_files':sources, 'source_tree_sha256':digest(sources)}

runtime = {'python':platform.python_version(), 'implementation':platform.python_implementation(),
           'platform':platform.platform(),
           'packages':sorted({(d.metadata['Name'],d.version) for d in metadata.distributions()})}
historical = parent['inputs']['v26a_archive']
assert identity(historical['path']) == historical
with zipfile.ZipFile(ROOT / historical['path']) as archive:
    anchors = []
    for sid in samples:
        member = f'samples/{sid}.json.gz'
        payload = archive.read(member)
        old = json.loads(gzip.decompress(payload))
        assert old['sample_id'] == sid
        anchors.append({'sample_id':sid, 'member':member,
                        'member_sha256':hashlib.sha256(payload).hexdigest(),
                        'H_P3_metric':old['baseline_metric'], 'S1_P3_metric':old['ablation_metric']})
    old_summary = json.loads(archive.read('summary.json'))

protocol = 'V27C_OFFICIAL_GRAPH_EVALUATION_PREREGISTRATION.md'
contract = {
    'schema_version':1, 'experiment':'V27C', 'status':'PROPOSED',
    'scope':'V27C_OFFICIAL_FROZEN_GRAPH_RETROSPECTIVE_EVALUATION',
    'builder':'Codex', 'review':None, 'human_execution_authorization':None,
    'protocol':{'path':protocol,'canonical_sha256':canonical(protocol)},
    'cohort':parent['cohort'], 'arms':arms, 'stages':stages,
    'evaluation':{
        'distinct_graph_count':240, 'complete_passes':2, 'expected_cell_evaluations':480,
        'order':['sample_id_as_listed','arm_as_listed','stage_as_listed'],
        'input_pass':1, 'matching':'fresh_host_graphs_per_cell_per_pass',
        'scale':None,'max_distance_um':7.0,'voxel_scale_um':[1.625,.40625,.40625],
        'preserve_input_node_edge_order':True, 'reuse_archived_matching':False,
        'ledger_from_same_matched_state':True,
        'entry_points':['tracking_cellmot.metrics.evaluate','tracking_cellmot.metrics._evaluate_matched_graph',
                        'tracking_cellmot.metrics.node_recall','tracking_cellmot.metrics.per_sample_metrics',
                        'tracking_cellmot.metrics.summarise'],
        'primary_diagnostic_endpoint':'adjusted_edge_jaccard',
        'metrics':['edge_tp','edge_fp','edge_fn','edge_jaccard','adjusted_edge_jaccard',
                   'node_recall','predicted_nodes','estimated_total_nodes','total_node_ratio',
                   'division_tp','division_fp','division_fn','division_jaccard','score'],
        'aggregation':'host_summarise_per_arm_stage_no_reweighting',
        'expected_summary_count':15,'expected_samples_per_summary':16,
        'null_policy':{'missing_primary_or_invalid_estimate':'INVALID_EXECUTION',
                       'zero_division_denominator':'null_with_reason_host_score_omits_term',
                       'null_delta_operands':'null','silent_row_drop':False},
        'clip_adjusted_jaccard_at_one':False,
    },
    'paired_contrasts':[
        {'id':name,'before':a,'after':b,'kind':kind} for name,a,b,kind in [
        ('historical_forward_ties','H','M0','mechanism'),('order_motion','M0','M1','mechanism'),
        ('order_step','S0','S1','mechanism'),('ranking_select_first','M0','S0','mechanism'),
        ('ranking_filter_first','M1','S1','mechanism'),('baseline_M1','H','M1','baseline'),
        ('baseline_S0','H','S0','baseline'),('baseline_S1','H','S1','baseline')]],
    'pruning_contrasts':[['RAW','P2'],['P2','P3'],['RAW','P3']],
    'interaction':'(Y[S1]-Y[S0])-(Y[M1]-Y[M0]) per stage; descriptive only',
    'ledger':{'edge_categories':['OFFICIAL_TP','OFFICIAL_FP','UNEVALUATED_BY_SPARSE_GT','FILTERED_BY_HOST'],
              'missing_side':'ABSENT','gt_credit_namespace':['sample_id','gt_source_id','gt_target_id'],
              'prediction_namespace':['sample_id','source_id','target_id'],
              'required_fields':['prediction_endpoints','mapped_gt_endpoints','matched_edge_mask',
                                 'pred_valid','host_edge_id','host_table_membership','warnings'],
              'required_outputs':['credited_gt_gained_lost_shared','prediction_edge_union_transitions',
                                  'shared_node_mapping_changes','confidence_only_changes',
                                  'pruning_edge_endpoint_survival','survivor_mapping_evaluability_changes'],
              'reconciliation':['all_input_edges_partitioned','TP_equals_host_TP','FP_equals_host_FP',
                                'credited_GT_unique_valid','GT_complement_equals_FN','all_contrast_deltas_reconcile']},
    'inputs':{
        'v27b_approved_manifest':identity('v27b_freeze_approved_20260924.json'),
        'v27b_result':identity('v27b_recursive_history_results.json'),
        'v27b_inventory':identity(base+'/artifact_inventory.json'),
        'v27b_freeze_copy':identity(base+'/freeze_used.json'),
        'v27b_contract':identity('tests/fixtures/v27b_recursive_history.json'),
        'v26a_archive':historical,
    },
    'graph_inputs':graphs, 'parent_pass_summaries':summaries, 'ground_truth':ground_truth,
    'parent_source_canonical_sha256':approved['payload']['canonical_sources'],
    'reference_evaluation_source_canonical_sha256':{
        p:canonical(p) for p in [
            'src/atabey/evaluation/official_tracking_metric.py',
            'src/atabey/evaluation/official_division_metric.py',
            'src/atabey/evaluation/official_association_forensics.py',
            'src/atabey/io/geff_reader.py','src/atabey/constants.py','src/atabey/types.py',
            'tests/test_official_tracking_metric.py','tests/test_official_division_metric.py',
            'tests/test_official_association_forensics.py','pyproject.toml']},
    'host_evaluator':host, 'observed_runtime_reference':runtime,
    'historical_metric_anchors':{'per_sample':anchors,
        'H_P3_summary':old_summary['baseline_official_summary'],
        'S1_P3_summary':old_summary['ablation_official_summary'],
        'integer_and_null_masks':'exact','finite_float_absolute_tolerance':1e-12,
        'finite_float_relative_tolerance':0.0,
        'mismatch':'INVALID_EXECUTION_preserve_diagnose_no_silent_adjustment'},
    'integrity':{'replay':'exact_scientific_digests',
        'timing_memory_process_paths_excluded_from_digest':True,
        'historical_H_stage_signatures':48,'historical_S1_P3_signatures':16,
        'parent_graph_physical_copies':480,'graph_mutation_allowed':False,
        'missing_cell_or_identity_drift':'INVALID_EXECUTION',
        'failure_output':'preserve_partial_evidence_completed_cells_last_attempt_inventory',
        'retry_resume_overwrite':False},
    'authorization':{'execution_ready':False,'implementation_payload':None,
        'required_before_execution':['implementation_review','complete_source_closure',
                                     'passing_tests','runtime_and_input_verification',
                                     'distinct_reviewer','human_exact_payload_and_scope_approval']},
    'boundaries':{'new_matching_and_scoring_only_after_new_freeze':True,
        'tracking_replay':False,'pruning_rerun':False,'inference':False,'training':False,
        'threshold_search':False,'arm_selection':False,'production_promotion':False,
        'submission':False,'independent_validation_claim':False,'v26a_gate_recalculation':False},
    'valid_result_status':'VALID_RETROSPECTIVE_EVALUATION_RESULT',
}
write_new('tests/fixtures/v27c_official_graph_evaluation.json',contract)
print(json.dumps({'contract':identity('tests/fixtures/v27c_official_graph_evaluation.json'),
                  'graphs':len(graphs),'GT_files':sum(x['file_count'] for x in ground_truth),
                  'host_source_files':{k:len(v['source_files']) for k,v in host.items()},
                  'runtime_packages':len(runtime['packages'])},indent=2),flush=True)
