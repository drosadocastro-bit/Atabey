"""Collect a terminal run, then conditionally execute the approved local phase."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from kaggle.api.kaggle_api_extended import KaggleApi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v29a_execution_20260928'
api = KaggleApi(); api.authenticate()
kernel = 'drakus74/atabey-v29a-tta-research'
status = api.kernels_status(kernel).to_dict()
assert status.get('status') not in ('RUNNING', 'QUEUED'), 'Inference still active'
def save(path, obj):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True) + '\n')
save(OUT / 'terminal_status.json', status)
download = OUT / 'downloaded'
assert not download.exists(), 'Preserve previous collection; do not overwrite'
files, token = api.kernels_output(kernel, str(download), file_pattern=r'(^v29a_run/|^v29a_receipt\.json$|^v29a_bootstrap_failure\.json$)', page_size=100)
assert not token
identities = []
for p in sorted(download.rglob('*')):
    if p.is_file():
        identities.append({'path': p.relative_to(download).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
save(OUT / 'download_receipt.json', {'at_utc':datetime.now(timezone.utc).isoformat(), 'files':identities, 'count':len(files)})
summary_path = download / 'v29a_run/summary.json'
if status.get('status') != 'COMPLETE' or not summary_path.exists():
    print(json.dumps({'status':'INVALID_EXECUTION','remote_status':status,'local_scoring_started':False}),flush=True)
    raise SystemExit(0)
summary = json.loads(summary_path.read_text())
receipt = json.loads((OUT / 'execution_receipt.json').read_text())
assert summary['receipt'] == receipt
assert summary['package_manifest_sha256'] == receipt['package_manifest_sha256']
for item in summary['files']:
    path = (download / 'v29a_run' / item['path']).resolve()
    assert path.is_relative_to((download / 'v29a_run').resolve())
    assert path.stat().st_size == item['bytes']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], item['path']
save(OUT / 'download_integrity.json', {'status':'OUTPUT_HASHES_AND_LINEAGE_VERIFIED','verified_files':len(summary['files']),'package_manifest_sha256':summary['package_manifest_sha256'],'inference_summary_sha256':hashlib.sha256(summary_path.read_bytes()).hexdigest()})
print(json.dumps({'inference_status':summary['status'],'wall_seconds':summary['wall_seconds'],'timing_projection':summary.get('timing_projection'),'full_cohort_projection':summary.get('full_cohort_projection')}),flush=True)
if summary['status'] == 'NO_GO_RUNTIME':
    raise SystemExit(0)
assert summary['status'] == 'INFERENCE_COMPLETE'
local = OUT / 'local_evaluation'
command = [str(ROOT / '.venv/Scripts/python.exe'), '-u', str(ROOT / 'scripts/evaluate_v29a_tta.py'), '--package-dir', str(ROOT / 'outputs/v29a_preparation_20260928/package_r1'), '--inference-dir', str(download / 'v29a_run'), '--output-dir', str(local), '--receipt', str(OUT / 'execution_receipt.json')]
save(OUT / 'local_evaluation_attempt.json', {'at_utc':datetime.now(timezone.utc).isoformat(), 'outer_timeout_seconds':10800, 'command':command})
try:
    with (OUT / 'local_evaluation.stdout.log').open('x',encoding='utf-8') as stdout, (OUT / 'local_evaluation.stderr.log').open('x',encoding='utf-8') as stderr:
        result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=10800)
    save(OUT / 'local_evaluation_exit.json', {'at_utc':datetime.now(timezone.utc).isoformat(),'returncode':result.returncode})
    print(json.dumps({'local_returncode':result.returncode}),flush=True)
except subprocess.TimeoutExpired:
    save(OUT / 'local_evaluation_timeout.json', {'status':'INVALID_EXECUTION','at_utc':datetime.now(timezone.utc).isoformat(),'timeout_seconds':10800})
    raise
