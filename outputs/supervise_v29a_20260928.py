"""Finish the approved run without another dispatch or scientific retry."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from kaggle.api.kaggle_api_extended import KaggleApi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v29a_execution_20260928'
api = KaggleApi(); api.authenticate()
started = datetime.fromisoformat(json.loads((OUT / 'push_attempt.json').read_text())['started_at_utc'])
def save(path, value):
    with path.open('x',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(value,indent=2,sort_keys=True)+'\n')
save(OUT / 'supervisor_started.json', {'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Observe existing version 1; collect output once; conditionally run already approved local evaluation once','new_gpu_dispatches':False})
try:
    while True:
        now = datetime.now(timezone.utc)
        assert now < started + timedelta(hours=8), 'Remote completion/collection watchdog exceeded'
        try:
            status = api.kernels_status('drakus74/atabey-v29a-tta-research').to_dict()
        except Exception:
            save(OUT / (now.strftime('%H%M%S') + '.monitor_transport_error.json'), {'at_utc':now.isoformat(),'traceback':traceback.format_exc(),'scope':'Read-only status; no scientific retry'})
            time.sleep(60)
            continue
        save(OUT / (now.strftime('%H%M%S') + '.supervised_status.json'), status)
        print(json.dumps({'at_utc':now.isoformat(),'status':status}),flush=True)
        if status.get('status') not in ('RUNNING','QUEUED'):
            break
        time.sleep(60)
    api.kernels_pull('drakus74/atabey-v29a-tta-research', str(OUT / 'remote_at_completion'),metadata=True)
    current = json.loads((OUT / 'remote_at_completion/atabey-v29a-tta-research.ipynb').read_text())
    dispatch = json.loads((OUT / 'dispatch/V29A_tta_research_offline_kaggle.ipynb').read_text())
    assert [''.join(c['source']) for c in current['cells']] == [''.join(c['source']) for c in dispatch['cells']], 'Remote source changed'
    result = subprocess.run([sys.executable,'-u',str(ROOT / 'outputs/collect_v29a_20260928.py')],cwd=ROOT,check=False)
    outcome = {'at_utc':datetime.now(timezone.utc).isoformat(),'collection_process_exit':result.returncode,'competition_submission_performed':False}
    scored = OUT / 'local_evaluation/result.json'
    inference = OUT / 'downloaded/v29a_run/summary.json'
    if scored.exists():
        outcome['decision'] = json.loads(scored.read_text())['decision']
    elif inference.exists():
        outcome['inference_status'] = json.loads(inference.read_text())['status']
        outcome['requires_review'] = True
    else:
        outcome['requires_review'] = True
    save(OUT / 'supervisor_finished.json', outcome)
    print(json.dumps(outcome),flush=True)
except BaseException:
    save(OUT / 'supervisor_failure.json', {'at_utc':datetime.now(timezone.utc).isoformat(),'traceback':traceback.format_exc(),'scientific_retry_performed':False})
    raise
