"""Paced read-only retrieval after a preserved API listing rate limit."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import requests
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v29a_execution_20260928'
DOWNLOAD = OUT / 'downloaded'
assert not list(DOWNLOAD.rglob('*')), 'Preserve existing retrieved evidence'
assert not (OUT / 'local_evaluation_attempt.json').exists(), 'No duplicate local evaluation'
def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest()
api=KaggleApi();api.authenticate()
items=[]; token=None; pages=0
pattern=re.compile(r'(^v29a_run/|^v29a_receipt\.json$|^v29a_bootstrap_failure\.json$)')
with (OUT/'retrieval_listing.jsonl').open('x',encoding='utf-8') as ledger:
    with api.build_kaggle_client() as client:
        while True:
            req=ApiListKernelSessionOutputRequest();req.user_name='drakus74';req.kernel_slug='atabey-v29a-tta-research';req.page_size=1000
            if token: req.page_token=token
            for attempt in range(4):
                try:
                    response=client.kernels.kernels_api_client.list_kernel_session_output(req)
                    break
                except requests.HTTPError as exc:
                    ledger.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'page':pages+1,'attempt':attempt+1,'http_status':exc.response.status_code})+'\n');ledger.flush()
                    if exc.response.status_code!=429 or attempt==3: raise
                    time.sleep(30)
            pages+=1
            matches=[f for f in response.files if pattern.search(f.file_name)]
            items.extend(matches)
            ledger.write(json.dumps({'page':pages,'listed':len(response.files),'matched':len(matches),'matched_names':[f.file_name for f in matches]})+'\n');ledger.flush()
            print(json.dumps({'page':pages,'matched_total':len(items)}),flush=True)
            token=response.next_page_token
            if not token: break
            time.sleep(2)
assert items, 'No run evidence found'
assert len({f.file_name for f in items})==len(items)
def download(item):
    target=(DOWNLOAD/item.file_name).resolve()
    assert target.is_relative_to(DOWNLOAD.resolve()) and not target.exists()
    target.parent.mkdir(parents=True,exist_ok=True)
    response=requests.get(item.url,timeout=(20,120))
    response.raise_for_status()
    with target.open('xb') as f:f.write(response.content)
    return {'path':item.file_name,'bytes':target.stat().st_size,'sha256':sha(target)}
identities=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    futures=[pool.submit(download,item) for item in items]
    for future in as_completed(futures):
        identities.append(future.result())
        if len(identities)%100==0:print(json.dumps({'downloaded':len(identities),'total':len(items)}),flush=True)
save(OUT/'download_receipt.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'count':len(identities),'files':sorted(identities,key=lambda x:x['path']),'listing_pages':pages,'transport':'paced 1000-item pages; four concurrent read-only file transfers'})
summary_path=DOWNLOAD/'v29a_run/summary.json'
summary=json.loads(summary_path.read_text())
receipt=json.loads((OUT/'execution_receipt.json').read_text())
assert summary['receipt']==receipt and summary['package_manifest_sha256']==receipt['package_manifest_sha256']
for item in summary['files']:
    target=(DOWNLOAD/'v29a_run'/item['path']).resolve()
    assert target.is_relative_to((DOWNLOAD/'v29a_run').resolve())
    assert target.stat().st_size==item['bytes'] and sha(target)==item['sha256'],item['path']
save(OUT/'download_integrity.json',{'status':'OUTPUT_HASHES_AND_LINEAGE_VERIFIED','verified_files':len(summary['files']),'package_manifest_sha256':summary['package_manifest_sha256'],'inference_summary_sha256':sha(summary_path)})
print(json.dumps({k:summary.get(k) for k in ['status','wall_seconds','timing_projection','full_cohort_projection']}),flush=True)
if summary['status']=='NO_GO_RUNTIME':raise SystemExit(0)
assert summary['status']=='INFERENCE_COMPLETE'
command=[str(ROOT/'.venv/Scripts/python.exe'),'-u',str(ROOT/'scripts/evaluate_v29a_tta.py'),'--package-dir',str(ROOT/'outputs/v29a_preparation_20260928/package_r1'),'--inference-dir',str(DOWNLOAD/'v29a_run'),'--output-dir',str(OUT/'local_evaluation'),'--receipt',str(OUT/'execution_receipt.json')]
save(OUT/'local_evaluation_attempt.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'outer_timeout_seconds':10800,'command':command})
try:
    with (OUT/'local_evaluation.stdout.log').open('x',encoding='utf-8') as stdout,(OUT/'local_evaluation.stderr.log').open('x',encoding='utf-8') as stderr:
        result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=10800)
    save(OUT/'local_evaluation_exit.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'returncode':result.returncode})
    print(json.dumps({'local_returncode':result.returncode}),flush=True)
except subprocess.TimeoutExpired:
    save(OUT/'local_evaluation_timeout.json',{'status':'INVALID_EXECUTION','at_utc':datetime.now(timezone.utc).isoformat(),'timeout_seconds':10800})
    raise
