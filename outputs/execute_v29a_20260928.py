"""Freeze the approved candidate and dispatch exactly one bounded research run."""
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import shutil
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kaggle_http_client import KaggleHttpClient
from kagglesdk.competitions.types.competition_api_service import ApiListCompetitionPagesRequest
from kagglesdk.competitions.types.competition_enums import SubmissionGroup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v29a_execution_20260928'
OUT.mkdir(exist_ok=False)
def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
candidate_path = ROOT / 'v29a_research_candidate_20260928.json'
candidate = json.loads(candidate_path.read_text())
payload = candidate['payload']
assert hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == candidate['payload_sha256'] == 'c4edda67ad121bd34c7e4bba6e29f432de039401d3a20fe94846412d0890d25f'
for item in payload['artifacts']:
    path = ROOT / item['path']
    assert sha(path) == item['sha256'] and path.stat().st_size == item['bytes'], item['path']
api = KaggleApi(); api.authenticate()
original = KaggleHttpClient._prepare_response
def raw_quota(self, kind, response):
    if kind.__name__ == 'ApiGetAcceleratorQuotaStatisticsResponse':
        response.raise_for_status()
        return response.json()
    return original(self, kind, response)
KaggleHttpClient._prepare_response = raw_quota
quota = api.quota_view()
save(OUT / 'quota_before.json', quota)
q = quota['gpuQuota']
seconds = lambda value: float(value.removesuffix('s'))
remaining = seconds(q['totalTimeAllowed']) - seconds(q['timeUsed']) - seconds(q['timeReserved'])
assert remaining >= 12 * 3600, 'Insufficient quota for approved bound'
competition = 'biohub-cell-tracking-during-development'
selected = api.competition_submissions(competition, group=SubmissionGroup.SUBMISSION_GROUP_SELECTED, page_size=100)
save(OUT / 'selected_before.json', [s.to_dict() for s in selected])
assert {s.ref for s in selected} == {56631581, 54622713}, 'Selected baseline entries changed'
with api.build_kaggle_client() as client:
    request = ApiListCompetitionPagesRequest(); request.competition_name = competition
    pages = client.competitions.competition_api_client.list_competition_pages(request).to_dict()
save(OUT / 'competition_pages.json', pages)
assert 'September 29, 2026' in json.dumps(pages), 'Competition deadline changed'
now = datetime.now(timezone.utc)
assert now < datetime(2026, 9, 28, 14, 59, tzinfo=timezone.utc), 'Insufficient nine-hour research window before review target'
record = 'User approval in this chat: me parece solido baby aprobado congelado y ejecuta mi vida!'
receipt = {'status': 'APPROVED', 'scope': 'V29A_RESEARCH', 'builder': 'Codex', 'reviewer': 'Danny', 'authority': 'Danny', 'record': record, 'approved_at_utc': now.isoformat(), 'package_manifest_sha256': payload['package_manifest_sha256']}
save(OUT / 'execution_receipt.json', receipt)
freeze = {**candidate, 'status': 'APPROVED_FROZEN', 'reviewer': 'Danny', 'authority': 'Danny', 'approval_record': record, 'frozen_at_utc': now.isoformat(), 'candidate_file_sha256': sha(candidate_path)}
save(ROOT / 'v29a_research_freeze_approved_20260928.json', freeze)
package = ROOT / 'outputs/v29a_preparation_20260928/package_r1'
dispatch = OUT / 'dispatch'; dispatch.mkdir()
name = 'V29A_tta_research_offline_kaggle.ipynb'
template = json.loads((package / name).read_text())
notebook = copy.deepcopy(template)
lines = notebook['cells'][1]['source']
indices = [i for i, line in enumerate(lines) if line.startswith('RECEIPT = ')]
assert len(indices) == 1
lines[indices[0]] = 'RECEIPT = ' + repr(receipt) + '\n'
check = copy.deepcopy(notebook); check['cells'][1]['source'][indices[0]] = template['cells'][1]['source'][indices[0]]
assert check == template
save(dispatch / name, notebook)
shutil.copyfile(package / 'kernel-metadata.json', dispatch / 'kernel-metadata.json')
save(OUT / 'preflight.json', {'checked_at_utc': now.isoformat(), 'candidate_artifacts_verified': len(payload['artifacts']), 'remaining_gpu_hours': remaining / 3600, 'receipt_only_notebook_change': True, 'dispatch_notebook_sha256': sha(dispatch / name), 'dispatch_metadata_sha256': sha(dispatch / 'kernel-metadata.json'), 'competition_submission_authorized': False})
save(OUT / 'push_attempt.json', {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'session_timeout_seconds': 21600, 'accelerator': 'NvidiaTeslaT4', 'retries_authorized': False})
response = api.kernels_push(str(dispatch), timeout='21600', acc='NvidiaTeslaT4')
save(OUT / 'push_response.json', response.to_dict())
print(json.dumps({'remaining_gpu_hours': remaining / 3600, 'response': response.to_dict()}, indent=2))
