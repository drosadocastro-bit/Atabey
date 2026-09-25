"""Read-only post-run artifact audit; never runs linking or modifies frozen evidence."""
import gzip,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/v27b_frozen_20260924'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while chunk:=f.read(1048576):h.update(chunk)
 return h.hexdigest()

def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def loadgraph(path):
 with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)

def edges(g):
 e={(x['source_id'],x['target_id']):x for x in g['edges']}
 assert len(e)==len(g['edges'])
 return e

def nodes(g):
 n={x['node_id']:x for x in g['detections']}
 assert len(n)==len(g['detections'])
 return n

def verify_sample(path):
 summary=json.loads(path.read_text());sid=summary['sample_id']
 science={k:v for k,v in summary.items() if k not in ('sample_id','deterministic_replay')}
 assert summary['deterministic_replay'] is True
 inventory_checked=0
 for p in (1,2):
  directory=OUT/f'{sid}.pass{p}'
  assert json.loads((directory/'summary.json').read_text())==science
  assert {x.name for x in directory.iterdir()}=={a['path'] for a in science['scientific_artifacts']}|{'summary.json'}
  for item in science['scientific_artifacts']:
   artifact=directory/item['path']
   assert artifact.stat().st_size==item['bytes'] and sha(artifact)==item['sha256'],str(artifact)
   inventory_checked+=1
 reference_nodes=None
 for arm in ('H','M0','M1','S0','S1'):
  previous=None
  for stage in ('RAW','P2','P3'):
   graph=loadgraph(OUT/f'{sid}.pass1'/f'{arm}.{stage}.json.gz')
   assert graph['sample_id']==sid
   assert digest(graph)==science['graph_signatures'][arm][stage]['full_sha256']
   nn,ee=nodes(graph),edges(graph)
   assert len(nn)==science['stage_counts'][f'{arm}::{stage}::nodes']
   assert len(ee)==science['stage_counts'][f'{arm}::{stage}::edges']
   for (s,t),edge in ee.items():
    assert s in nn and t in nn and nn[t]['t']==nn[s]['t']+1
    assert edge['relation']=='continuation'
   assert len({s for s,t in ee})==len(ee) and len({t for s,t in ee})==len(ee)
   if stage=='RAW':
    if reference_nodes is None:reference_nodes=graph['detections']
    else:assert graph['detections']==reference_nodes
    assert len(ee)==science['counts'][f'R::{arm}::accepted']
   if previous is not None:
    pn,pe=previous
    assert nn.keys()<=pn.keys() and ee.keys()<=pe.keys()
    assert all(v==pn[k] for k,v in nn.items()) and all(v==pe[k] for k,v in ee.items())
   previous=nn,ee
 return {'sample_id':sid,'sources':science['counts']['sources'],'frames':science['counts']['frames'],
         'matching_pass_inventories':True,'scientific_files_hashed':inventory_checked,
         'unique_graph_stages_parsed':15,'raw_detection_identity_verified':True,'pruning_subset_and_retained_attributes_verified':True}

if __name__=='__main__':
 samples=[verify_sample(p) for p in sorted(OUT.glob('*.summary.json'))]
 print(json.dumps({'method':'Independent read-only artifact verification; no new scientific execution or independent scientific review.',
                   'completed_samples_verified':len(samples),'samples':samples},indent=2))
