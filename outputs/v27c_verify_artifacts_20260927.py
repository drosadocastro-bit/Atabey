"""Read-only post-run verification. Does not call matching or scoring."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/v27c_frozen_20260927'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(1048576):h.update(chunk)
    return h.hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def compressed(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)

result=read(OUT/'summary.json')
assert result['status']=='VALID_RETROSPECTIVE_EVALUATION_RESULT'
assert result['sample_count']==16 and result['distinct_graphs']==240 and result['completed_evaluations']==480
assert not (OUT/'invalid_execution.json').exists()
approved=ROOT/'v27c_freeze_approved_20260927.json'
assert sha(approved)==sha(OUT/'freeze_used.json')==result['approved_freeze_sha256']
manifest=read(approved)
assert digest(manifest['payload'])==manifest['payload_sha256']
for path,expected in manifest['payload']['canonical_sources'].items():
    b=(ROOT/path).read_bytes().replace(b'\r\n',b'\n').replace(b'\r',b'\n')
    assert hashlib.sha256(b).hexdigest()==expected,path
inventory=read(OUT/'artifact_inventory.json')
paths=[r['path'] for r in inventory['files']]
assert len(paths)==len(set(paths))
assert set(paths)=={p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file() and p.name!='artifact_inventory.json'}
for row in inventory['files']:
    path=OUT/row['path']
    assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']
first=read(OUT/'pass1/summary.json');second=read(OUT/'pass2/summary.json')
assert first==second==result['result']
assert digest(first)==result['scientific_sha256']
copies=0
for p in (OUT/'pass1').rglob('*'):
    if p.is_file():
        assert sha(p)==sha(OUT/'pass2'/p.relative_to(OUT/'pass1'))
        copies+=1
c=read(ROOT/'tests/fixtures/v27c_official_graph_evaluation.json')
assert [s['sample_id'] for s in first['samples']]==c['cohort']['sample_ids']
sample_lookup={s['sample_id']:s for s in first['samples']}
graph_lookup={(g['sample_id'],g['arm'],g['stage']):g for g in c['graph_inputs']}
cells=ledgers=0
for sid in c['cohort']['sample_ids']:
    folder=OUT/'pass1'/sid
    sample=sample_lookup[sid]
    assert read(folder/'summary.json')==sample
    records={}
    gt_edge_sets=[]
    for arm in c['arms']:
        for stage in c['stages']:
            key=f'{arm}.{stage}'
            r=compressed(folder/f'{key}.json.gz')
            assert digest(r)==sample['cell_digests'][key]
            assert r['sample_id']==sid and r['metrics']==sample['metrics'][key]
            records[(arm,stage)]=r
            g=compressed(ROOT/graph_lookup[(sid,arm,stage)]['evaluation_input']['path'])
            assert {n['node_id']:n['attributes'] for n in r['nodes']}=={n['node_id']:n for n in g['detections']}
            assert {(e['source_id'],e['target_id']):e['attributes'] for e in r['edges']}=={(e['source_id'],e['target_id']):e for e in g['edges']}
            counts=Counter(e['category'] for e in r['edges'])
            assert sum(counts.values())==len(g['edges'])
            assert all(counts[k]==v for k,v in r['category_counts'].items())
            assert counts['OFFICIAL_TP']==r['metrics']['edge_tp'] and counts['OFFICIAL_FP']==r['metrics']['edge_fp']
            credits={tuple(e['mapped_gt_endpoints']) for e in r['edges'] if e['category']=='OFFICIAL_TP'}
            missed=set(map(tuple,r['missed_gt_edges']))
            assert credits==set(map(tuple,r['credited_gt_edges'])) and len(credits)==r['metrics']['edge_tp']
            assert not credits & missed and len(missed)==r['metrics']['edge_fn']
            gt_edge_sets.append(credits|missed)
            assert r['denominators']['edge']==sum(r['metrics'][k] for k in ('edge_tp','edge_fp','edge_fn'))
            for edge in r['edges']:
                if edge['category']=='FILTERED_BY_HOST':
                    assert edge['host_table_membership'] is False and edge['pred_valid'] is None
                else:
                    assert edge['host_table_membership'] is True
                    assert edge['matched_edge_mask']==(edge['category']=='OFFICIAL_TP')
                    assert edge['pred_valid']==(edge['category'] in ('OFFICIAL_TP','OFFICIAL_FP'))
            cells+=1
    assert all(x==gt_edge_sets[0] for x in gt_edge_sets)
    combinations=[(f'{x["id"]}.{stage}',(x['before'],stage),(x['after'],stage),False)
                  for stage in c['stages'] for x in c['paired_contrasts']]
    combinations += [(f'{arm}.{a}_to_{b}',(arm,a),(arm,b),True)
                     for arm in c['arms'] for a,b in c['pruning_contrasts']]
    assert len(combinations)==39
    for key,old_key,new_key,pruning in combinations:
        ledger=compressed(folder/f'{key}.ledger.json.gz')
        assert digest(ledger)==sample['comparisons'][key]['sha256']
        a,b=records[old_key],records[new_key]
        old={(e['source_id'],e['target_id']):e for e in a['edges']}
        new={(e['source_id'],e['target_id']):e for e in b['edges']}
        rows={(e['source_id'],e['target_id']):e for e in ledger['edge_union']}
        assert len(rows)==len(ledger['edge_union']) and rows.keys()==old.keys()|new.keys()
        transitions=Counter()
        for edge,row in rows.items():
            assert row['before']==old.get(edge) and row['after']==new.get(edge)
            ca=old[edge]['category'] if edge in old else 'ABSENT'
            cb=new[edge]['category'] if edge in new else 'ABSENT'
            assert row['before_category']==ca and row['after_category']==cb
            transitions[f'{ca}->{cb}']+=1
        assert dict(transitions)==ledger['category_transitions']
        ac,bc=set(map(tuple,a['credited_gt_edges'])),set(map(tuple,b['credited_gt_edges']))
        assert set(map(tuple,ledger['gained_gt_edges']))==bc-ac
        assert set(map(tuple,ledger['lost_gt_edges']))==ac-bc
        assert set(map(tuple,ledger['shared_gt_edges']))==ac&bc
        assert ledger['counts']['added_edges']==len(new.keys()-old.keys())
        assert ledger['counts']['removed_edges']==len(old.keys()-new.keys())
        if pruning:
            assert new.keys()<=old.keys()
            assert all(e['attributes']==old[k]['attributes'] for k,e in new.items())
        for metric in ledger['metric_delta']:
            x,y=a['metrics'][metric],b['metrics'][metric]
            assert ledger['metric_delta'][metric]==(None if x is None or y is None else y-x)
        ledgers+=1
for key,totals in first['metric_count_totals'].items():
    for field,total in totals.items():assert total==sum(s['metrics'][key][field] for s in first['samples'])
for key,aggregate in first['comparisons'].items():
    counts,transitions=Counter(),Counter()
    for sample in first['samples']:
        counts.update(sample['comparisons'][key]['counts'])
        transitions.update(sample['comparisons'][key]['category_transitions'])
    assert dict(counts)==aggregate['counts'] and dict(transitions)==aggregate['category_transitions']
assert cells==240 and ledgers==624
verification={'status':'POST_RUN_ARTIFACT_CHECKS_PASSED','inventory_files_verified':len(paths),
              'identical_pass_file_pairs':copies,'unique_cells_parsed':cells,'unique_ledgers_parsed':ledgers,
              'frozen_sources_verified':len(manifest['payload']['canonical_sources']),
              'metric_count_totals_independently_resummed':True,'comparison_counts_independently_resummed':True,
              'new_matching_or_scoring_performed':False,'verifier_sha256':sha(Path(__file__))}
with (ROOT/'outputs/v27c_post_run_verification_20260927.json').open('x',encoding='utf-8',newline='\n') as f:
    json.dump(verification,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(verification,indent=2),flush=True)
