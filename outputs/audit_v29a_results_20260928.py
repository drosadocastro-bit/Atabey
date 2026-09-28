"""Audit retained V29A evidence; never run prediction or per-graph scoring."""
from datetime import datetime, timezone
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from atabey.submission.v29a import sha, digest, metric_parity, tree_identity
from evaluate_v29a_tta import host_identity,local_runtime_identity,verify_inference
from atabey.evaluation.official_tracking_metric import OfficialTrackingResult,summarize_official_tracking
OUT=ROOT/'outputs/v29a_execution_20260928'
DATA=OUT/'downloaded/v29a_run'
c=json.loads((ROOT/'tests/fixtures/v29a_tta.json').read_text())
freeze=json.loads((ROOT/'v29a_research_freeze_approved_20260928.json').read_text())
assert freeze['status']=='APPROVED_FROZEN' and freeze['authority']==freeze['reviewer']=='Danny'
assert digest(freeze['payload'])==freeze['payload_sha256']
for item in freeze['payload']['artifacts']:
    p=ROOT/item['path'];assert sha(p)==item['sha256'] and p.stat().st_size==item['bytes'],item['path']
manifest_sha=sha(ROOT/'outputs/v29a_preparation_20260928/package_r1/package_manifest.json')
assert manifest_sha==freeze['payload']['package_manifest_sha256']
s=json.loads((DATA/'summary.json').read_text())
receipt=json.loads((OUT/'execution_receipt.json').read_text())
records=verify_inference(DATA,s,c,manifest_sha,receipt)
assert s['wall_seconds']<=c['budgets']['gpu_seconds']
workload=sum(math.prod(v['image_metadata']['shape']) for v in c['samples'].values())
projections={}
for key,subset in [('timing_projection',[r for r in records if r['sample_id'] in c['timing_ids']]),('full_cohort_projection',records)]:
    all_records=subset+s['visible']['samples']
    rates=[(r['route']['seconds']+r['inference_seconds']+r['linking_seconds']+r['pruning_seconds']+r['export_seconds'])/math.prod(r['shape']) for r in all_records]
    seconds=s['initialization_seconds']+600+2*(max(rates)*workload+s['visible']['csv_validation_seconds']*199/len(s['visible']['samples']))
    assert seconds==s[key]['projected_seconds'] and seconds<=36000
    projections[key]={'projected_seconds':seconds,'measured_samples':len(all_records),'worst_sample_id':all_records[rates.index(max(rates))]['sample_id']}
r=json.loads((OUT/'local_evaluation/result.json').read_text())
assert r['package_manifest_sha256']==manifest_sha and r['inference_summary_sha256']==sha(DATA/'summary.json')
assert r['wall_seconds']<=c['budgets']['local_scoring_seconds']
assert json.loads((OUT/'local_evaluation_exit.json').read_text())['returncode']==0
assert sorted(x['sample_id'] for x in r['rows'])==sorted(c['samples'])
assert sha(ROOT/c['historical_archive']['path'])==c['historical_archive']['sha256']
with zipfile.ZipFile(ROOT/c['historical_archive']['path']) as z:
    for row in r['rows']:
        sid=row['sample_id']
        assert row==json.loads((OUT/'local_evaluation'/f'{sid}.json').read_text())
        old=json.loads(z.read('samples/'+sid+'.json'))['arms'][c['baseline_arm']]['metrics']
        metric_parity(row['baseline'],old,c['metric_absolute_tolerance'])
        assert tree_identity(ROOT/'train'/(sid+'.geff'))==c['samples'][sid]['gt_tree']
for group,ids in [('ALL',list(c['samples'])),*c['strata'].items()]:
    expected=r['summaries'] if group=='ALL' else r['strata'][group]
    for arm in ['baseline','tta']:
        actual=asdict(summarize_official_tracking([OfficialTrackingResult(**row[arm]) for row in r['rows'] if row['sample_id'] in ids]))
        metric_parity(actual,expected[arm],c['metric_absolute_tolerance'])
repeat=json.loads((OUT/'local_evaluation/official_repeat.json').read_text())
metric_parity(repeat,next(row['tta'] for row in r['rows'] if row['sample_id']==c['repeat_ids'][0]),c['metric_absolute_tolerance'])
host_identity(c['host_evaluator']);assert local_runtime_identity(c['local_runtime']['packages'])==c['local_runtime']
baseline=r['summaries']['baseline'];tta=r['summaries']['tta'];limits=c['quality_gates']
deltas={row['sample_id']:row['tta']['score']-row['baseline']['score'] for row in r['rows']}
improved=sum(d>limits['comparison_epsilon'] for d in deltas.values());regressed=sum(d < -limits['comparison_epsilon'] for d in deltas.values())
checks={'score_gain':tta['score']-baseline['score']>=limits['minimum_score_gain'],
 'adjusted_edge_noninferiority':tta['adjusted_edge_jaccard']>=baseline['adjusted_edge_jaccard'],
 'all_strata_noninferiority':all(v['tta']['score']>=v['baseline']['score'] for v in r['strata'].values()),
 'improved_exceeds_regressed':improved>regressed,
 'bounded_individual_loss':min(deltas.values())>=-limits['maximum_individual_score_loss'],
 'four_catastrophic_noninferiority':all(deltas[sid]>=0 for sid in c['catastrophic_ids']),
 'node_recall':tta['node_recall']>=baseline['node_recall']-limits['maximum_node_recall_loss'],
 'official_edge_fp_nonincrease':sum(row['tta']['edge_fp'] for row in r['rows'])<=sum(row['baseline']['edge_fp'] for row in r['rows'])}
assert checks==r['decision']['gates']
assert (improved,regressed)==(r['decision']['improved'],r['decision']['regressed'])
assert r['decision']['status']==('GO_TO_HUMAN_SUBMISSION_REVIEW' if all(checks.values()) else 'NO_GO')
result={'status':'FINAL_EVIDENCE_VERIFIED','checked_at_utc':datetime.now(timezone.utc).isoformat(),
 'package_manifest_sha256':manifest_sha,'result_sha256':sha(OUT/'local_evaluation/result.json'),
 'inference_summary_sha256':sha(DATA/'summary.json'),'frozen_artifacts_verified':len(freeze['payload']['artifacts']),
 'paired_samples_verified':len(r['rows']),'historical_baseline_metric_parity':True,'official_repeat_verified':True,
 'gt_trees_verified':199,'source_runtime_verified':True,'timing_independently_recomputed':projections,
 'decision':r['decision']['status'],'quality_gates_independently_recomputed':checks,
 'score_gain':tta['score']-baseline['score'],'improved':improved,'regressed':regressed,
 'worst_sample':min(deltas,key=deltas.get),'worst_delta':min(deltas.values()),
 'catastrophic_deltas':{sid:deltas[sid] for sid in c['catastrophic_ids']},
 'official_edge_fp_totals':{arm:sum(row[arm]['edge_fp'] for row in r['rows']) for arm in ['baseline','tta']},
 'submission_authorized':False,'new_prediction_or_per_graph_scoring_performed':False}
with (OUT/'final_evidence_verification.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,sort_keys=True)
print(json.dumps(result,indent=2))
