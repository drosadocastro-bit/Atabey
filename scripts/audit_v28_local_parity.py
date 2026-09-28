"""Non-GPU implementation parity against existing V24/V27 artifacts."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from atabey.submission.v28 import route_for_sample, build_graph, export_graph, validate_csv, signature
from atabey.submission.writer import KAGGLE_SUBMISSION_COLUMNS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=False)
    result={'status':'RUNNING','new_inference':False,'new_scoring':False,'routes':[],'graphs':[]}
    def record():
        (a.output_dir/'parity.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    start=time.perf_counter()
    try:
        report=json.loads((ROOT/'v24_3_full_199_score_validation_report.json').read_text())
        archive=ROOT/report['artifacts']['merged_archive']['filename']
        assert sha(archive)==report['artifacts']['merged_archive']['sha256']
        with zipfile.ZipFile(archive) as z:
            records={d['sample_id']:d for n in z.namelist() if n.startswith('samples/') for d in [json.loads(z.read(n))]}
        assert len(records)==199
        for sid,r in sorted(records.items()):
            route=route_for_sample(ROOT/'train'/(sid+'.zarr'))
            expected=sid.startswith('6bba_') and r['v19_reference_detector']=='components'
            row={'sample_id':sid,'expected_pruning':expected,**route,'match':expected==route['apply_pruning']}
            result['routes'].append(row);record()
            assert row['match'],sid
            print('ROUTE',sid,row['match'],flush=True)
        parent=json.loads((ROOT/'v27b_recursive_history_results.json').read_text())
        ip=ROOT/parent['artifact_inventory']['path'];assert sha(ip)==parent['artifact_inventory']['sha256']
        inventory={r['path']:r for r in json.loads(ip.read_text())['files']}
        raws=sorted(k for k in inventory if k.endswith('.pass1/H.RAW.json.gz'))
        assert len(raws)==16
        for rel in raws:
            raw=ip.parent/rel;pruned=ip.parent/rel.replace('H.RAW','H.P3')
            assert sha(raw)==inventory[rel]['sha256'] and sha(pruned)==inventory[rel.replace('H.RAW','H.P3')]['sha256']
            with gzip.open(raw,'rt') as f:r=json.load(f)
            with gzip.open(pruned,'rt') as f:expected=json.load(f)
            coords=[[n[k] for k in ['t','z','y','x']] for n in r['detections']]
            graph,_=build_graph(r['sample_id'],coords,True)
            actual={'sample_id':graph.sample_id,'detections':[asdict(n) for n in graph.detections],'edges':[asdict(e) for e in graph.edges]}
            check=actual==expected
            text,export=export_graph(graph,(100,64,256,256),0)
            csv=a.output_dir/(graph.sample_id+'.csv');csv.write_text(','.join(KAGGLE_SUBMISSION_COLUMNS)+'\n'+text,encoding='utf-8',newline='\n')
            validation=validate_csv(csv,[export])
            old=records[graph.sample_id]['arms']['e016_atabey_relink_v24_3_short_fragment_shadow']['graph_signature_sha256']
            row={'sample_id':graph.sample_id,'full_saved_graph_match':check,'v24_signature_match':signature(graph)==old,'csv_validation':validation,'rounded_nodes':export['rounded_nodes']}
            result['graphs'].append(row);record()
            assert check and row['v24_signature_match'],row
            print('GRAPH',graph.sample_id,check,flush=True)
        result['status']='PASS'
    except BaseException as e:
        result.update(status='FAIL',error=repr(e));record();raise
    finally:
        result['wall_seconds']=time.perf_counter()-start;record()

if __name__=='__main__':main()
