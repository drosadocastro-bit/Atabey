"""Read-only live monitor of the single approved V29A execution."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from kaggle.api.kaggle_api_extended import KaggleApi

OUT = Path(__file__).resolve().parent / 'v29a_execution_20260928'
KERNEL = 'drakus74/atabey-v29a-tta-research'
api = KaggleApi(); api.authenticate()
previous = ''
while True:
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%H%M%S')
    status = api.kernels_status(KERNEL).to_dict()
    logs = api.kernels_logs(KERNEL)
    (OUT / (stamp + '.status.json')).write_text(json.dumps(status, indent=2) + '\n')
    if logs != previous:
        (OUT / (stamp + '.logs.raw.log')).write_text(logs, encoding='utf-8')
        print(json.dumps({'at': now.isoformat(), 'status': status, 'new_log_tail': logs[len(previous):][-5000:]}), flush=True)
        previous = logs
    else:
        print(json.dumps({'at': now.isoformat(), 'status': status, 'log_chars': len(logs)}), flush=True)
    if status.get('status') not in ('RUNNING', 'QUEUED'):
        break
    time.sleep(60)
print('TERMINAL_STATUS: ' + json.dumps(status), flush=True)
