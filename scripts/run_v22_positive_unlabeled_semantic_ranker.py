from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[1]
ROUTES=('cfar_sidelobe/bipartite','components/greedy'); LOCAL='local_maxima/motion_mutual'; TOL=1e-12
PRIMARY=['minimum_daughter_contrast','mean_daughter_contrast','contrast_conservation_error','daughter_mass_balance','mean_daughter_anisotropy']
ABLATIONS={'contrast_only':['minimum_daughter_contrast','mean_daughter_contrast','contrast_conservation_error'],'mass_shape_only':['daughter_mass_balance','mean_daughter_anisotropy'],'raw_plus_confidence':PRIMARY+['mean_detection_confidence']}

class Prep:
 def __init__(self,median,mean,scale): self.median=median; self.mean=mean; self.scale=scale
 def transform(self,x):
  x=np.asarray(x,float); miss=~np.isfinite(x); y=np.where(miss,self.median,x); return np.concatenate([(y-self.mean)/self.scale,miss.astype(float)],axis=1)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def weighted_median(x,w):
 o=np.argsort(x,kind='stable'); x=x[o]; w=w[o]; return float(x[min(np.searchsorted(np.cumsum(w),.5*w.sum(),'left'),len(x)-1)])
def fit_prep(rows,features):
 x=rows[features].to_numpy(float); ev=rows.event_id.astype(str); groups=ev.groupby(ev).transform('size').to_numpy(float); n=ev.nunique(); w=np.full(len(rows),1/n)/groups
 med=np.array([weighted_median(x[np.isfinite(x[:,j]),j],w[np.isfinite(x[:,j])]) if np.isfinite(x[:,j]).any() else 0.0 for j in range(x.shape[1])]); y=np.where(np.isfinite(x),x,med); wn=w/w.sum(); mean=wn@y; var=wn@((y-mean)**2); scale=np.where(var>1e-12,np.sqrt(var),1.0); return Prep(med,mean,scale)
def pair_data(rows,features,prep):
 labeled=rows[rows.official_label.isin(['official_tp','official_fp'])].copy(); diffs=[]; weights=[]
 events=[g for _,g in labeled.groupby('event_id',sort=True) if (g.official_label=='official_tp').any() and (g.official_label=='official_fp').any()]
 for g in events:
  gx=prep.transform(g[features].to_numpy(float)); tp=gx[g.official_label.to_numpy()=='official_tp']; fp=gx[g.official_label.to_numpy()=='official_fp']; d=(tp[:,None,:]-fp[None,:,:]).reshape(-1,gx.shape[1]); diffs.append(d); weights.append(np.full(len(d),1/(len(events)*len(tp)*len(fp))))
 return np.concatenate(diffs),np.concatenate(weights)
def fit_logistic(d,w,c):
 w=w/w.sum();
 def fun(beta):
  m=d@beta; loss=np.logaddexp(0,-m); val=float(w@loss)+.5*float(beta@beta)/c; grad=d.T@(-expit(-m)*w)+beta/c; return val,grad
 r=minimize(fun,np.zeros(d.shape[1]),method='L-BFGS-B',jac=True,options={'maxiter':150,'ftol':1e-10,'gtol':1e-7});
 if not r.success: raise RuntimeError(f'fit did not converge: {r.message}')
 return r.x

def choose_sign(train,feature):
 vals=[]
 for _,g in train[train.official_label.isin(['official_tp','official_fp'])].groupby('event_id'):
  tp=g[g.official_label=='official_tp'][feature].to_numpy(float); fp=g[g.official_label=='official_fp'][feature].to_numpy(float)
  if len(tp) and len(fp): vals.append(float(np.mean((tp[:,None]>fp[None,:]).astype(float))))
 return 1.0 if not vals or np.mean(vals)>=.5 else -1.0

def score_rows(rows,scores):
 out=[]; event_rows=[]
 for event,g in rows.groupby('event_id',sort=True):
  idx=g.index.to_numpy(); s=scores[idx]; pos=(g.official_label.to_numpy()=='official_tp');
  if not pos.any(): continue
  ranks=[]
  for local_i in np.flatnonzero(pos): ranks.append(1+int(np.sum(s>=s[local_i]-TOL)))
  first=g.iloc[0]; event_rows.append({'event_id':event,'fold':int(first.fold),'family':first.family,'route':first.route,'min_positive_rank':min(ranks),'positive_count':len(ranks)})
  for rank in ranks: out.append({'event_id':event,'fold':int(first.fold),'family':first.family,'route':first.route,'rank':rank})
 return pd.DataFrame(out),pd.DataFrame(event_rows)
def metrics(pos,event):
 if pos.empty:return {'event_count':0,'tp_count':0,**{f'action_recall@{k}':None for k in [1,5,10,50]},**{f'event_recall@{k}':None for k in [1,5,10,50]},'mrr':None}
 result={'event_count':len(event),'tp_count':len(pos),'mrr':float(np.mean(1/pos['rank']))}
 for k in [1,5,10,50]: result[f'action_recall@{k}']=float(np.mean(pos['rank']<=k)); result[f'event_recall@{k}']=float(np.mean(event['min_positive_rank']<=k))
 return result
def strata(pos,event):
 result={'pooled':metrics(pos[pos.route.isin(ROUTES)],event[event.route.isin(ROUTES)])}
 result['by_fold']={str(k):metrics(g,event[event.fold==k]) for k,g in pos.groupby('fold')}
 result['by_family']={str(k):metrics(g,event[event.family==k]) for k,g in pos.groupby('family')}
 result['by_route']={str(k):metrics(g,event[event.route==k]) for k,g in pos.groupby('route')}
 result['local_maxima_unproven'] = metrics(pos[pos.route==LOCAL],event[event.route==LOCAL]) if (pos.route==LOCAL).any() else None
 return result

def fit_model(all_rows,features,head_contract,label):
 folds=[1,2,3]; grid=[.01,.1,1.,10.]; allp=[]; alle=[]; folds_meta=[]
 for outer in folds:
  train_folds=[f for f in folds if f!=outer]; inner_scores={c:[] for c in grid}
  for val in train_folds:
   tr=all_rows[all_rows.fold.isin([f for f in train_folds if f!=val])]; va=all_rows[all_rows.fold==val].reset_index(drop=True); prep=fit_prep(tr,features); d,w=pair_data(tr,features,prep)
   for c in grid:
    beta=fit_logistic(d,w,c); scores=prep.transform(va[features].to_numpy(float))@beta; p,e=score_rows(va,scores); inner_scores[c].append(strata(p,e)['pooled']['event_recall@50'])
  means={c:float(np.mean(v)) for c,v in inner_scores.items()}; best=max(means.values()); selected=min(c for c in grid if abs(means[c]-best)<=1e-12)
  tr=all_rows[all_rows.fold!=outer]; va=all_rows[all_rows.fold==outer].reset_index(drop=True); prep=fit_prep(tr,features); d,w=pair_data(tr,features,prep); beta=fit_logistic(d,w,selected); scores=prep.transform(va[features].to_numpy(float))@beta; p,e=score_rows(va,scores); allp.append(p); alle.append(e); folds_meta.append({'heldout_fold':outer,'selected_c':selected,'inner_event_recall50_by_c':means,'coefficients':beta.tolist(),'fit_features':features})
  print(f'{label}: heldout fold {outer} selected C={selected:g}',flush=True)
 p=pd.concat(allp,ignore_index=True); e=pd.concat(alle,ignore_index=True); return {'model':label,'features':features,'metrics':strata(p,e),'per_positive':p,'per_event':e,'outer_fits':folds_meta}

def baseline(all_rows,feature,label):
 allp=[]; alle=[]
 for outer in [1,2,3]:
  tr=all_rows[all_rows.fold!=outer]; va=all_rows[all_rows.fold==outer]; sign=choose_sign(tr,feature); scores=sign*va[feature].to_numpy(float); p,e=score_rows(va.reset_index(drop=True),scores); allp.append(p); alle.append(e); print(f'{label}: heldout fold {outer} sign={sign:+.0f}',flush=True)
 p=pd.concat(allp,ignore_index=True); e=pd.concat(alle,ignore_index=True); return {'model':label,'features':[feature],'metrics':strata(p,e),'per_positive':p,'per_event':e}

def gate(summary):
 primary=summary['primary']; base=summary['best_univariate']; m=primary['metrics']; d=summary['contract']['decision']; pooled=m['pooled']; folds=m['by_fold']; routes=m['by_route']; fam=m['by_family']; delta=pooled['event_recall@50']-base['metrics']['pooled']['event_recall@50']; gates={'pooled_action_recall50':pooled['action_recall@50']>=d['action_recall_at_50_min'],'pooled_event_recall50':pooled['event_recall@50']>=d['positive_event_recall_at_50_min'],'each_fold_event_recall50':min(v['event_recall@50'] for v in folds.values())>=d['per_fold_positive_event_recall_at_50_min'],'cfar_action_recall50':routes.get(ROUTES[0],{}).get('action_recall@50',0)>=d['cfar_action_recall_at_50_min'],'cfar_event_recall50':routes.get(ROUTES[0],{}).get('event_recall@50',0)>=d['cfar_event_recall_at_50_min'],'components_action_recall50':routes.get(ROUTES[1],{}).get('action_recall@50',0)>=d['components_action_recall_at_50_min'],'components_event_recall50':routes.get(ROUTES[1],{}).get('event_recall@50',0)>=d['components_event_recall_at_50_min'],'each_family_event_recall50':min(v['event_recall@50'] for v in fam.values())>=d['each_family_event_recall_at_50_min'],'advantage_over_best_univariate':delta>=d['event_recall_at_50_advantage_over_best_univariate_min'],'fold_spread':max(v['event_recall@50'] for v in folds.values())-min(v['event_recall@50'] for v in folds.values())<=d['maximum_fold_event_recall_at_50_spread'],'route_gap':max(v['event_recall@50'] for k,v in routes.items() if k in ROUTES)-min(v['event_recall@50'] for k,v in routes.items() if k in ROUTES)<=d['maximum_route_event_recall_at_50_gap']}
 state='GO_TO_LOCAL_CONSTRAINT_SHADOW_PREREGISTRATION' if all(gates.values()) else ('NO_GO_POSITIVE_UNLABELED_RANKER' if not (pooled['action_recall@50']>=d['action_recall_at_50_min'] and pooled['event_recall@50']>=d['positive_event_recall_at_50_min']) else 'HOLD_SEMANTIC_RETRIEVAL_UNSTABLE'); return {'decision':state,'gates':gates,'event_recall50_delta_over_best_univariate':delta}

def write_report(path,s):
 m=s['primary']['metrics']; lines=['# V22 Positive-Unlabeled Semantic Ranker Results','',f"Decision: **{s['decision']['decision']}**",'', 'Unknown actions remained in every held-out ranking pool and were never treated as negatives. No assignment or graph mutation occurred.','', '## Primary Retrieval','', '| Stratum | Action R@50 | Event R@50 | MRR |','| --- | ---: | ---: | ---: |']
 for name,v in [('pooled',m['pooled']),*[(f'fold {k}',v) for k,v in m['by_fold'].items()],*[(k,v) for k,v in m['by_route'].items()],*[(f'family {k}',v) for k,v in m['by_family'].items()]]: lines.append(f"| {name} | {v['action_recall@50']:.6f} | {v['event_recall@50']:.6f} | {v['mrr']:.6f} |")
 lines += ['',f"Best univariate baseline: `{s['best_univariate']['model']}`, event R@50 `{s['best_univariate']['metrics']['pooled']['event_recall@50']:.6f}`.",f"Primary event R@50 delta: `{s['decision']['event_recall50_delta_over_best_univariate']:+.6f}`.",'','## Frozen Gates','']
 for k,v in s['decision']['gates'].items(): lines.append(f"- {'PASS' if v else 'FAIL'}: `{k}`")
 lines += ['', '## Local-Maxima','', 'Reported separately as zero-shot/unproven generalization; excluded from the decision.', '', '## Boundary','', '- This evaluates conditional retrieval of sampled official actions, not biological probability.', '- Assignment, calibration, locked validation, and full-199 execution remain closed.']
 path.write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=ROOT/'tests/fixtures/v22_positive_unlabeled_semantic_ranker.json'); ap.add_argument('--input',type=Path,default=ROOT/'v22_semantic_action_appearance_features.csv.gz'); ap.add_argument('--output',type=Path,default=ROOT/'v22_positive_unlabeled_semantic_ranker_summary.json'); ap.add_argument('--ranks',type=Path,default=ROOT/'v22_positive_unlabeled_semantic_ranker_positive_ranks.csv'); ap.add_argument('--report',type=Path,default=ROOT/'V22_POSITIVE_UNLABELED_SEMANTIC_RANKER_RESULTS.md'); args=ap.parse_args(); c=json.loads(args.contract.read_text(encoding='utf-8-sig')); 
 for k,h in [('source_action_features','source_action_features_sha256'),('source_evidence_summary','source_evidence_summary_sha256'),('source_evidence_contract','source_evidence_contract_sha256'),('source_development_contract','source_development_contract_sha256')]:
  if sha(ROOT/c[k])!=c[h]: raise RuntimeError(f'Pinned source changed: {k}')
 rows=pd.read_csv(args.input); rows['family']=rows.sample_id.astype(str).str.split('_',n=1).str[0]; features=c['primary_features'];
 primary=fit_model(rows,features,c,'primary'); bases=[baseline(rows,'mean_daughter_contrast','mean_daughter_contrast'),baseline(rows,'mean_detection_confidence','mean_detection_confidence')]; best=max(bases,key=lambda x:x['metrics']['pooled']['event_recall@50']); diagnostics={name:fit_model(rows,fs,c,name) for name,fs in c['mandatory_ablations'].items()}; ranks=primary['per_positive'].copy(); ranks.to_csv(args.ranks,index=False); s={'contract':c['name'],'contract_sha256':sha(args.contract),'primary':primary,'baselines':bases,'best_univariate':best,'diagnostics':diagnostics,'contract':c}; decision=gate(s); s['decision']=decision; 
 for key in ['primary','best_univariate']:
  for sub in ['per_positive','per_event']:
   if sub in s[key]: s[key].pop(sub)
 for b in s['baselines']:
  b.pop('per_positive',None); b.pop('per_event',None)
 for d in s['diagnostics'].values(): d.pop('per_positive',None); d.pop('per_event',None)
 s['model_fitting_enabled']=True; s['assignment_enabled']=False; s['graph_mutation_enabled']=False; s['full_199_authorized']=False; args.output.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8'); write_report(args.report,s); print(json.dumps({'decision':decision,'primary_pooled':primary['metrics']['pooled'],'best_univariate':best['model'],'best_univariate_event_recall50':best['metrics']['pooled']['event_recall@50']},indent=2),flush=True)
if __name__=='__main__': main()



