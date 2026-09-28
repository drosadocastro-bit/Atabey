"""Build one unapproved offline research notebook from the frozen V28 bundle."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def dump(value):
    return json.dumps(value, indent=2, sort_keys=True) + '\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(ok):
    if not ok:
        raise ValueError('Frozen V28 input changed')


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    contract_bytes = (ROOT / 'tests/fixtures/v29a_tta.json').read_bytes()
    contract = json.loads(contract_bytes)
    require(digest((ROOT / contract['protocol']['path']).read_bytes()) == contract['protocol']['sha256'])
    original = (ROOT / contract['v28_base_bundle']['path']).read_bytes()
    require(digest(original) == contract['v28_base_bundle']['sha256'])
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        sources = {name: z.read(name) for name in z.namelist()}
    base_manifest = sources.pop('package_manifest.json')
    require(digest(base_manifest) == contract['baseline_package_manifest_sha256'])
    manifest = json.loads(base_manifest)
    for name, expected in manifest['files'].items():
        require(digest(sources[name]) == expected)
        if name.startswith(('src/', 'scripts/')):
            require((ROOT / name).read_bytes().replace(b'\r\n', b'\n') == sources[name])
    for name in ('src/atabey/submission/v29a.py', 'scripts/run_v29a_tta.py',
                 'scripts/evaluate_v29a_tta.py', 'scripts/build_v29a_notebook.py'):
        sources[name] = (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
    sources['v29a_contract.json'] = contract_bytes
    sources[contract['protocol']['path']] = (ROOT / contract['protocol']['path']).read_bytes()
    for key in ('validation_budget_wall_hours', 'validation_GPU', 'GPU_budget_user_reported_hours'):
        manifest.pop(key, None)
    manifest.update(status='V29A_RESEARCH_NOT_APPROVED', parent_package_manifest_sha256=digest(base_manifest),
                    research_budgets=contract['budgets'], competition_submission_authorized=False,
                    files={name: digest(data) for name, data in sorted(sources.items())})
    sources['package_manifest.json'] = dump(manifest).encode()
    mh = digest(sources['package_manifest.json'])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(sources.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 28, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    payload = buffer.getvalue()
    notebook = json.loads((ROOT / 'notebooks/V28_validation_offline_kaggle.ipynb').read_text())
    lines = ''.join(notebook['cells'][1]['source']).split('command = ', 1)[0].splitlines()
    receipt = {'status': 'NOT_APPROVED', 'scope': 'V29A_RESEARCH', 'package_manifest_sha256': mh,
               'builder': 'Codex', 'reviewer': None, 'authority': None, 'record': None}
    replacements = {
        'MODE = ': "MODE = 'v29a'",
        'RECEIPT = ': 'RECEIPT = ' + repr(receipt),
        "assert RECEIPT['scope']": "assert RECEIPT['scope'] == 'V29A_RESEARCH'",
        "assert RECEIPT['package_manifest_sha256']": "assert RECEIPT['package_manifest_sha256'] == " + repr(mh),
        'ROOT = WORK': "ROOT = WORK / 'v29a_package'",
        'payload = base64': 'payload = base64.b64decode(' + repr(base64.b64encode(payload).decode()) + ')',
        'assert hashlib.sha256(payload)': 'assert hashlib.sha256(payload).hexdigest() == ' + repr(digest(payload)),
        "assert hashlib.sha256((ROOT / 'package_manifest.json')": "assert hashlib.sha256((ROOT / 'package_manifest.json').read_bytes()).hexdigest() == " + repr(mh),
        'DEPS = WORK': "DEPS = WORK / 'v29a_deps'",
        'receipt_path = WORK': "receipt_path = WORK / 'v29a_receipt.json'",
        'OUTPUT = WORK': "OUTPUT = WORK / 'v29a_run'",
    }
    for prefix, replacement in replacements.items():
        indices = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        require(len(indices) == 1)
        lines[indices[0]] = replacement
    code = '\n'.join(lines) + '''
command = [sys.executable, '-u', str(ROOT / 'scripts/run_v29a_tta.py'), '--package-root', str(ROOT), '--support-root', str(SUPPORT), '--weights', str(WEIGHTS), '--data-root', str(DATA), '--output-dir', str(OUTPUT), '--receipt', str(receipt_path), '--setup-seconds', str(time.perf_counter() - STARTED)]
timeout = 21600 - (time.perf_counter() - STARTED)
assert timeout > 0, 'Setup exhausted the research budget'
try:
    subprocess.run(command, check=True, env=ENV, timeout=timeout)
except BaseException as exc:
    (WORK / 'v29a_bootstrap_failure.json').write_text(json.dumps({'status':'INVALID_EXECUTION','type':type(exc).__name__,'message':str(exc)}, indent=2))
    raise
summary = json.loads((OUTPUT / 'summary.json').read_text())
assert summary['status'] in ['NO_GO_RUNTIME', 'INFERENCE_COMPLETE']
assert not (WORK / 'submission.csv').exists()
print(json.dumps({'status':summary['status'], 'wall_seconds':summary['wall_seconds']}, indent=2))
'''
    compile(code, 'V29A', 'exec')
    notebook['cells'][0]['source'] = ['# V29A: one four-view XY research experiment\n',
        'No ground-truth reads, scoring or submission in this notebook. Exact human research approval required.\n',
        'Package manifest SHA-256: ' + mh + '\n']
    notebook['cells'][1]['source'] = code.splitlines(keepends=True)
    notebook['cells'][1]['outputs'] = []
    notebook['cells'][1]['execution_count'] = None
    (output / 'v29a_source_bundle.zip').write_bytes(payload)
    (output / 'package_manifest.json').write_bytes(sources['package_manifest.json'])
    name = 'V29A_tta_research_offline_kaggle.ipynb'
    (output / name).write_text(dump(notebook), encoding='utf-8', newline='\n')
    metadata = json.loads((ROOT / 'outputs/v28_submission_review_20260928/kernel-metadata.json').read_text())
    metadata.update(id='drakus74/atabey-v29a-tta-research', title='Atabey V29A TTA research', code_file=name,
                    docker_image=contract['docker_image'], docker_image_pinning_type='original', machine_shape='NvidiaTeslaT4')
    (output / 'kernel-metadata.json').write_text(dump(metadata), encoding='utf-8', newline='\n')
    print(dump({'manifest_sha256': mh, 'bundle_bytes': len(payload), 'files': len(manifest['files']), 'output': str(output)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output-dir', type=Path, required=True)
    build(p.parse_args().output_dir)
