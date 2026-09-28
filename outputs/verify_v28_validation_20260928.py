"""Verify saved V28 validation output without model inference or scoring."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--download-dir',type=Path,required=True);p.add_argument('--record',type=Path,required=True);a=p.parse_args()
    assert not a.record.exists(), 'Preserve earlier verification record'
    frozen=json.loads((ROOT/'v28_validation_freeze_approved_20260928.json').read_text())
    for item in frozen['payload']['artifacts']:
        path=ROOT/item['path'];assert sha(path)==item['sha256'] and path.stat().st_size==item['bytes'],str(path)
    bundles=[ROOT/i['path'] for i in frozen['payload']['artifacts'] if i['path'].endswith('v28_source_bundle.zip')]
    assert len(bundles)==1
    with zipfile.ZipFile(bundles[0]) as bundle:
        references=json.loads(bundle.read('validation_reference.json'))
    matches=list(a.download_dir.rglob('v28_validation_run/summary.json'))
    assert len(matches)==1, 'Complete validation summary required'
    run=matches[0].parent;summary=json.loads(matches[0].read_text())
    assert summary['status']=='VALIDATION_COMPLETE' and summary['mode']=='validation'
    assert summary['package_manifest_sha256']==frozen['payload']['package_manifest_sha256']
    assert summary['receipt']==frozen['execution_receipt']
    assert not summary['kaggle_submission_performed']
    routes=json.loads((run/'route_parity.json').read_text());parity=json.loads((run/'inference_parity.json').read_text());repeat=json.loads((run/'repeat_parity.json').read_text())
    assert len(routes)==199 and len({r['sample_id'] for r in routes})==199 and all(r['match'] and r['apply_pruning']==r['expected_pruning'] for r in routes)
    assert len(parity)==7 and len({r['sample_id'] for r in parity})==7 and all(r['match'] and r['graph_signature_sha256']==r['expected_graph_signature_sha256'] for r in parity)
    assert [r['sample_id'] for r in routes]==sorted(references['samples'])
    assert all(r['expected_pruning']==references['samples'][r['sample_id']]['pruning_eligible'] for r in routes)
    assert [r['sample_id'] for r in parity]==references['inference_ids']
    assert all(r['graph_signature_sha256']==references['samples'][r['sample_id']]['graph_signature_sha256'] for r in parity)
    assert repeat['sample_id']==references['inference_ids'][0]
    assert repeat['match'] and repeat['graph_signature_sha256']==parity[0]['graph_signature_sha256']
    assert summary['parity']['route_records']==routes and summary['parity']['inference_records']==parity and summary['parity']['repeat']==repeat
    sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
    from atabey.submission.v28 import validate_csv
    from run_v28_submission import runtime_projection
    visible=summary['visible_or_hidden_test'];csv=run/'validation_submission.csv'
    assert sha(csv)==visible['csv_sha256']
    assert validate_csv(csv,visible['samples'])==visible['csv_validation']
    projection=runtime_projection(summary['parity'],visible,summary['initialization_seconds'])
    assert projection==summary['runtime_projection']==json.loads((run/'runtime_projection.json').read_text())
    assert projection['passes'] and not projection['hidden_runtime_verified']
    assert not list(a.download_dir.rglob('submission.csv'))
    result={'status':'PASS','builder_verification_not_independent_review':True,'route_checks':len(routes),'fresh_inference_checks':len(parity),'repeat_match':True,'visible_samples':len(visible['samples']),'csv_rows':visible['csv_validation']['rows'],'csv_sha256':visible['csv_sha256'],'projected_seconds':projection['projected_seconds'],'wall_seconds':summary['wall_seconds'],'gpu':summary['runtime']['gpu'],'new_inference':False,'new_scoring':False,'competition_submission_authorized':False,'verified_artifacts':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(run.rglob('*')) if p.is_file()]}
    a.record.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='verified_artifacts'},indent=2))


if __name__=='__main__':main()
