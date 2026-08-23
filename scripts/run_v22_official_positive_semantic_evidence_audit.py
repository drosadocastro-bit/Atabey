from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import rankdata
from atabey.io.zarr_reader import open_competition_array,read_timepoint
from atabey.tracking.semantic_patch_features import peak_patch_features,division_action_appearance_features

ROOT=Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def auc(labels,scores):
    y=np.asarray(labels)==1; s=np.asarray(scores,float); ok=np.isfinite(s); y=y[ok]; s=s[ok]
    n1=int(y.sum()); n0=int((~y).sum())
    if not n1 or not n0:return None
    ranks=rankdata(s,method='average'); return float((ranks[y].sum()-n1*(n1+1)/2)/(n1*n0))
def event_mean_auc(df,feature,sign):
    vals=[]
    for _,g in df.groupby('event_id',sort=True):
        value=auc((g.official_label=='official_tp').astype(int),sign*g[feature].to_numpy(float))
        if value is not None: vals.append(value)
    return float(np.mean(vals)) if vals else None

def extract_peaks(peaks,train_dir,contract):
    rows=[]; patch=contract['patch']
    for sample_id,sample_peaks in peaks.groupby('sample_id',sort=True):
        array=open_competition_array(train_dir/f'{sample_id}.zarr')
        for t,frame_peaks in sample_peaks.groupby('t',sort=True):
            volume=np.asarray(read_timepoint(array,int(t)))
            for row in frame_peaks.itertuples(index=False):
                f=peak_patch_features(volume,(row.z_um,row.y_um,row.x_um),voxel_scale_um=patch['voxel_scale_um'],core_radius_um=patch['core_radius_um'],shell_inner_radius_um=patch['shell_inner_radius_um'],shell_outer_radius_um=patch['shell_outer_radius_um'],threshold_mad=patch['effective_volume_threshold_mad'])
                rows.append({'peak_id':row.peak_id,'sample_id':sample_id,'t':int(t),'confidence':float(row.confidence),**f})
        print(f'peaks {sample_id}: {len(sample_peaks)}',flush=True)
    return pd.DataFrame(rows)

def build_actions(shard_dir,peak_features,feature_groups):
    peak_map=peak_features.set_index('peak_id').to_dict('index'); frames=[]; feature_names=[f for values in feature_groups.values() for f in values]
    for path in sorted(shard_dir.glob('*.csv.gz')):
        source=pd.read_csv(path,usecols=['action_id','sample_id','fold','event_id','source_detector','source_link_strategy','parent_peak_id','child_1_peak_id','child_2_peak_id','parent_confidence','child_1_confidence','child_2_confidence','official_label','registered_official_positive','graph_mutated'])
        rows=[]
        for r in source.itertuples(index=False):
            p=peak_map[r.parent_peak_id]; c1=peak_map[r.child_1_peak_id]; c2=peak_map[r.child_2_peak_id]
            features=division_action_appearance_features(p,c1,c2,parent_confidence=r.parent_confidence,child_1_confidence=r.child_1_confidence,child_2_confidence=r.child_2_confidence)
            rows.append({'action_id':r.action_id,'sample_id':r.sample_id,'family':r.sample_id.split('_',1)[0],'fold':int(r.fold),'event_id':r.event_id,'route':f'{r.source_detector}/{r.source_link_strategy}','official_label':r.official_label,'registered_official_positive':bool(r.registered_official_positive),'graph_mutated':bool(r.graph_mutated),**features})
        frame=pd.DataFrame(rows); frames.append(frame); print(f'actions {path.stem}: {len(frame)}',flush=True)
    result=pd.concat(frames,ignore_index=True)
    if set(feature_names)-set(result.columns): raise RuntimeError('Frozen action features missing')
    return result

def evaluate(actions,contract):
    groups=contract['feature_groups']; confidence=set(groups['confidence_baseline']); raw=[f for group,fs in groups.items() if group!='confidence_baseline' for f in fs]
    labeled=actions[actions.official_label.isin(['official_tp','official_fp'])].copy(); event_rows=[]
    for heldout in contract['evaluation']['folds']:
        train=labeled[labeled.fold!=heldout]; test=labeled[labeled.fold==heldout]
        for group,features in groups.items():
            for feature in features:
                train_auc=event_mean_auc(train,feature,1.0); sign=1.0 if train_auc is None or train_auc>=0.5 else -1.0
                for event_id,event in test.groupby('event_id',sort=True):
                    value=auc((event.official_label=='official_tp').astype(int),sign*event[feature].to_numpy(float))
                    if value is None: continue
                    first=event.iloc[0]; event_rows.append({'feature':feature,'feature_group':group,'heldout_fold':int(heldout),'event_id':event_id,'family':first.family,'route':first.route,'sign':int(sign),'auc':value})
    events=pd.DataFrame(event_rows); metrics={}
    for feature,g in events.groupby('feature',sort=True):
        metrics[feature]={'feature_group':g.feature_group.iloc[0],'event_count':len(g),'oof_equal_event_auc':float(g.auc.mean()),'by_fold':{str(int(k)):float(v.auc.mean()) for k,v in g.groupby('heldout_fold')},'by_family':{str(k):float(v.auc.mean()) for k,v in g.groupby('family')},'by_route':{str(k):float(v.auc.mean()) for k,v in g.groupby('route')}}
    best_conf=max((metrics[f]['oof_equal_event_auc'],f) for f in confidence)
    best_raw=max((metrics[f]['oof_equal_event_auc'],f) for f in raw)
    d=contract['decision']; group_best={group:max(metrics[f]['oof_equal_event_auc'] for f in fs) for group,fs in groups.items() if group!='confidence_baseline'}
    groups_passing=sum(v>=d['raw_feature_group_auc_min'] for v in group_best.values())
    stable=[]
    for f in raw:
        m=metrics[f]; decision_routes=[r for r in ('cfar_sidelobe/bipartite','components/greedy') if r in m['by_route']]
        if (m['oof_equal_event_auc']>=d['raw_feature_group_auc_min'] and min(m['by_fold'].values())>=d['passing_feature_min_fold_auc'] and min(m['by_family'].values())>=d['passing_feature_min_family_auc'] and len(decision_routes)==2 and min(m['by_route'][r] for r in decision_routes)>=d['passing_feature_min_route_auc']): stable.append(f)
    primary=['patch_contrast','patch_signal_mass','patch_effective_volume','patch_anisotropy','patch_coverage']; peak_complete=float(np.isfinite(peak_features_global[primary].to_numpy(float)).all(axis=1).mean())
    action_features=[f for fs in groups.values() for f in fs]; tp=actions.official_label=='official_tp'; fp=actions.official_label=='official_fp'; complete=np.isfinite(actions[action_features].to_numpy(float)).all(axis=1)
    availability={'peak_descriptor_completeness':peak_complete,'official_tp_action_completeness':float(complete[tp].mean()),'official_fp_action_completeness':float(complete[fp].mean())}
    gates={'peak_descriptor_completeness_min':availability['peak_descriptor_completeness']>=d['peak_descriptor_completeness_min'],'official_tp_action_completeness_min':availability['official_tp_action_completeness']>=d['official_tp_action_completeness_min'],'official_fp_action_completeness_min':availability['official_fp_action_completeness']>=d['official_fp_action_completeness_min'],'raw_feature_groups_passing_min':groups_passing>=d['raw_feature_groups_passing_min'],'stable_raw_feature_exists':bool(stable),'best_raw_auc_advantage_over_best_confidence_min':best_raw[0]-best_conf[0]>=d['best_raw_auc_advantage_over_best_confidence_min']}
    availability_ok=all(gates[k] for k in ('peak_descriptor_completeness_min','official_tp_action_completeness_min','official_fp_action_completeness_min'))
    if not availability_ok or groups_passing==0: decision='NO_GO_NONMOTION_SEMANTIC_EVIDENCE'
    elif all(gates.values()): decision='GO_TO_POSITIVE_UNLABELED_RANKER_PREREGISTRATION'
    else: decision='HOLD_NONMOTION_SIGNAL_UNSTABLE'
    return {'decision':decision,'availability':availability,'feature_metrics':metrics,'feature_group_best_auc':group_best,'best_confidence_feature':{'feature':best_conf[1],'auc':best_conf[0]},'best_raw_feature':{'feature':best_raw[1],'auc':best_raw[0]},'best_raw_advantage_over_confidence':best_raw[0]-best_conf[0],'stable_raw_features':stable,'gates':gates,'event_auc_rows':events}

def write_report(path,summary):
    e=summary['evaluation']
    lines=['# V22 Official-Positive Semantic Evidence Audit Results','',f"Decision: **{e['decision']}**",'', 'This is conditional discrimination among sampled official TP/FP actions, not biological truth or full-candidate precision.','', '## Availability','', '| Population | Completeness |','| --- | ---: |',f"| peaks | {e['availability']['peak_descriptor_completeness']:.6f} |",f"| official TP actions | {e['availability']['official_tp_action_completeness']:.6f} |",f"| official FP actions | {e['availability']['official_fp_action_completeness']:.6f} |",'', '## Best Evidence','',f"- Best confidence baseline: `{e['best_confidence_feature']['feature']}` AUC `{e['best_confidence_feature']['auc']:.6f}`.",f"- Best raw feature: `{e['best_raw_feature']['feature']}` AUC `{e['best_raw_feature']['auc']:.6f}`.",f"- Raw advantage: `{e['best_raw_advantage_over_confidence']:+.6f}`."]
    best_name=e['best_raw_feature']['feature']; best=e['feature_metrics'][best_name]
    lines += ['', '## Best Raw Feature By Stratum','', '| Stratum | OOF event-balanced AUC |','| --- | ---: |']
    for fold,value in best['by_fold'].items(): lines.append(f'| fold {fold} | {value:.6f} |')
    for family,value in best['by_family'].items(): lines.append(f'| family {family} | {value:.6f} |')
    for route,value in best['by_route'].items(): lines.append(f'| {route} | {value:.6f} |')
    lines += ['',f"Stable raw features: `{', '.join(e['stable_raw_features'])}`.",'', '## Feature Groups','', '| Group | Best OOF event-balanced AUC |','| --- | ---: |']
    for group,value in e['feature_group_best_auc'].items(): lines.append(f'| {group} | {value:.6f} |')
    lines += ['', '## Frozen Gates','']
    for name,passed in e['gates'].items(): lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines += ['', '## Boundaries','', '- Unknown and unsupported actions were not negatives.', '- Local-maxima is descriptive only and cannot carry the decision.', '- CFAR is the weakest supported route and should remain an explicit generalization watchpoint.', '- No model, assignment, graph mutation, locked validation, or full-199 evaluation was used.']
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    global peak_features_global
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=ROOT/'tests/fixtures/v22_official_positive_semantic_evidence_audit.json'); ap.add_argument('--train-dir',type=Path,default=ROOT/'train'); ap.add_argument('--peaks',type=Path,default=ROOT/'v22_unet_detection_development_46_peaks.csv'); ap.add_argument('--shards',type=Path,default=ROOT/'v22_semantic_action_shards'); ap.add_argument('--peak-output',type=Path,default=ROOT/'v22_semantic_peak_patch_features.csv.gz'); ap.add_argument('--action-output',type=Path,default=ROOT/'v22_semantic_action_appearance_features.csv.gz'); ap.add_argument('--output',type=Path,default=ROOT/'v22_official_positive_semantic_evidence_audit_summary.json'); ap.add_argument('--report',type=Path,default=ROOT/'V22_OFFICIAL_POSITIVE_SEMANTIC_EVIDENCE_AUDIT_RESULTS.md'); args=ap.parse_args()
    c=json.loads(args.contract.read_text(encoding='utf-8-sig'))
    for p,h in [('source_peak_csv','source_peak_sha256'),('source_action_summary','source_action_summary_sha256'),('source_development_contract','source_development_contract_sha256'),('source_proxy_audit','source_proxy_audit_sha256')]:
        if sha(ROOT/c[p])!=c[h]: raise RuntimeError(f'Pinned source changed: {p}')
    peaks=pd.read_csv(args.peaks); peak_features_global=extract_peaks(peaks,args.train_dir,c); peak_features_global.to_csv(args.peak_output,index=False,compression='gzip')
    actions=build_actions(args.shards,peak_features_global,c['feature_groups']); actions.to_csv(args.action_output,index=False,compression='gzip')
    e=evaluate(actions,c); events=e.pop('event_auc_rows'); events.to_csv(ROOT/'v22_semantic_evidence_event_auc.csv',index=False)
    summary={'contract':c['name'],'contract_sha256':sha(args.contract),'population':{'peaks':len(peaks),'actions':len(actions),'official_tp':int((actions.official_label=='official_tp').sum()),'official_fp':int((actions.official_label=='official_fp').sum())},'evaluation':e,'tta_variance_available':False,'model_fitting_enabled':False,'assignment_enabled':False,'graph_mutated':bool(actions.graph_mutated.any()),'full_199_authorized':False}
    args.output.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8'); write_report(args.report,summary); print(json.dumps({'decision':e['decision'],'availability':e['availability'],'best_confidence':e['best_confidence_feature'],'best_raw':e['best_raw_feature'],'raw_advantage':e['best_raw_advantage_over_confidence'],'groups':e['feature_group_best_auc'],'gates':e['gates']},indent=2),flush=True)
if __name__=='__main__': main()

