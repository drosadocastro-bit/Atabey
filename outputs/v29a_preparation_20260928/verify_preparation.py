"""Read-only identity audit; no inference, graph evaluation or submission."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from atabey.submission.v29a import sha, tree_identity
from atabey.submission.v28 import inspect_sample
from evaluate_v29a_tta import host_identity, local_runtime_identity

OUT = ROOT / 'outputs/v29a_preparation_20260928'
PACKAGE = OUT / 'package_r1'
contract = json.loads((ROOT / 'tests/fixtures/v29a_tta.json').read_text())
manifest_path = PACKAGE / 'package_manifest.json'
manifest = json.loads(manifest_path.read_text())
assert sha(manifest_path) == '7d93749e50dfe95fa1643dceb39e870f9111850ce994c14c30ca1496ddd4dc67'
with zipfile.ZipFile(PACKAGE / 'v29a_source_bundle.zip') as bundle:
    assert set(bundle.namelist()) == set(manifest['files']) | {'package_manifest.json'}
    assert bundle.read('package_manifest.json') == manifest_path.read_bytes()
    for name, expected in manifest['files'].items():
        data = bundle.read(name)
        assert hashlib.sha256(data).hexdigest() == expected, name
        if name.startswith(('scripts/', 'src/')):
            assert data == (ROOT / name).read_bytes().replace(b'\r\n', b'\n'), name
    assert bundle.read('v29a_contract.json') == (ROOT / 'tests/fixtures/v29a_tta.json').read_bytes()
    assert bundle.read(contract['protocol']['path']) == (ROOT / contract['protocol']['path']).read_bytes()
assert sha(ROOT / contract['protocol']['path']) == contract['protocol']['sha256']
assert sha(ROOT / contract['historical_archive']['path']) == contract['historical_archive']['sha256']
assert sha(ROOT / contract['v28_base_bundle']['path']) == contract['v28_base_bundle']['sha256']
notebook_name = 'V29A_tta_research_offline_kaggle.ipynb'
assert (ROOT / 'notebooks' / notebook_name).read_bytes() == (PACKAGE / notebook_name).read_bytes()
assert len(contract['samples']) == 199
gt_files = 0
for sid, expected in contract['samples'].items():
    assert inspect_sample(ROOT / 'train' / (sid + '.zarr')) == expected['image_metadata'], sid
    actual = tree_identity(ROOT / 'train' / (sid + '.geff'))
    assert actual == expected['gt_tree'], sid
    gt_files += actual['files']
host_identity(contract['host_evaluator'])
assert local_runtime_identity(contract['local_runtime']['packages']) == contract['local_runtime']
release = json.loads((ROOT / 'v28_release_freeze_20260928.json').read_text())
for item in release['payload']['artifacts']:
    path = ROOT / item['path']
    assert sha(path) == item['sha256'] and path.stat().st_size == item['bytes'], item['path']
protected = ROOT / 'notebooks/V25_upstream_association_forensics_cuda_kaggle.ipynb'
assert sha(protected) == 'f9f13081e96b1925903e1ccb5ae464744b0eb5cc0daf3774f45ba33ce86c33e1'
suites = ET.parse(OUT / 'tests_r2.xml').getroot().findall('testsuite')
assert sum(int(s.attrib['tests']) for s in suites) == 110
assert all(int(s.attrib['failures']) == int(s.attrib['errors']) == 0 for s in suites)
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
assert head == contract['base_commit']
result = {'status': 'PREPARATION_IDENTITIES_VERIFIED', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
          'base_commit': head, 'package_manifest_sha256': sha(manifest_path),
          'source_members': len(manifest['files']), 'sample_metadata_verified': 199,
          'gt_trees_verified': 199, 'gt_files_verified': gt_files,
          'v28_release_artifacts_verified': len(release['payload']['artifacts']),
          'protected_v25_sha256': sha(protected), 'tests_passed': 110,
          'official_host_and_runtime_verified': True, 'inference_performed': False,
          'official_scoring_performed': False, 'execution_approved': False}
with (OUT / 'preparation_audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, indent=2))
