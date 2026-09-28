"""Build reviewable offline notebooks; never uploads or executes them."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(data):return hashlib.sha256(data).hexdigest()


def dump(value):return json.dumps(value,indent=2,sort_keys=True)+'\n'


def build(support, extra_wheels, output):
    output.mkdir(parents=True,exist_ok=False)
    contract=json.loads((ROOT/'tests/fixtures/v28a_submission_readiness.json').read_text())
    sources={p.relative_to(ROOT).as_posix():p.read_bytes().replace(b'\r\n',b'\n') for p in (ROOT/'src/atabey').rglob('*.py')}
    sources['scripts/run_v28_submission.py']=(ROOT/'scripts/run_v28_submission.py').read_bytes().replace(b'\r\n',b'\n')
    for path,pin in contract['candidate']['historical_sources'].items():
        assert sha((ROOT/path).read_bytes().replace(b'\r\n',b'\n'))==pin['canonical_sha256'],path
    sources['candidate_contract.json']=(ROOT/'tests/fixtures/v28a_submission_readiness.json').read_bytes()
    report=json.loads((ROOT/'v24_3_full_199_score_validation_report.json').read_text())
    archive=ROOT/report['artifacts']['merged_archive']['filename'];assert sha(archive.read_bytes())==report['artifacts']['merged_archive']['sha256']
    with zipfile.ZipFile(archive) as z:
        records=[json.loads(z.read(n)) for n in z.namelist() if n.startswith('samples/')]
    refs={'source_archive_sha256':report['artifacts']['merged_archive']['sha256'], 'inference_ids':contract['validation']['original_smoke_ids']+contract['validation']['catastrophic_parity_ids'],'samples':{r['sample_id']:{'pruning_eligible':r['sample_id'].startswith('6bba_') and r['v19_reference_detector']=='components','graph_signature_sha256':r['arms'][report['evaluated_arm']]['graph_signature_sha256']} for r in records}}
    assert len(refs['samples'])==199 and len(refs['inference_ids'])==7
    sources['validation_reference.json']=dump(refs).encode()
    extra=list(extra_wheels.glob('tracksdata-*.whl'));assert len(extra)==1
    sources['extra_wheels/'+extra[0].name]=extra[0].read_bytes()
    support_paths=sorted([*support.glob('repo/**/*.py'),*support.glob('wheels/*.whl')])
    # The older support-pack tracksdata wheel is deliberately not installed.
    # The replacement is built from the same commit used by V24 evaluation.
    install=[p.relative_to(support).as_posix() for p in support_paths if p.suffix=='.whl' and not p.name.startswith('tracksdata-')]
    manifest={'status':'IMPLEMENTED_NOT_FROZEN','candidate':contract['candidate'],'files':{p:sha(b) for p,b in sorted(sources.items())},'support_files':{p.relative_to(support).as_posix():sha(p.read_bytes()) for p in support_paths},'offline_install_wheels':install,'extra_install_wheels':['extra_wheels/'+extra[0].name],'tracksdata_source_commit':'39dccf3a243e44274759468cb31b2ad9e7fc1d09','python_minor':[3,12],'inherited_runtime_dependencies':['torch','pandas'],'dataset_versions':{'pilkwang/biohub-tracking-support-pack-50ep-v1':json.loads((ROOT/'outputs/v28_implementation_20260928/support_version.json').read_text(encoding='utf-8-sig'))['current_version_number'],'drakus74/v22-e016-clean-checkpoint':json.loads((ROOT/'outputs/v28_implementation_20260928/checkpoint_version.json').read_text(encoding='utf-8-sig'))['current_version_number']},'GPU_budget_user_reported_hours':45,'validation_budget_wall_hours':2,'validation_GPU':'one_GPU_requested; effective_quota_charge_unverified','competition_submission_authorized':False}
    sources['package_manifest.json']=dump(manifest).encode()
    mh=sha(sources['package_manifest.json'])
    zipped=io.BytesIO()
    with zipfile.ZipFile(zipped,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(sources.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,9,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    payload=zipped.getvalue();encoded=base64.b64encode(payload).decode()
    (output/'v28_source_bundle.zip').write_bytes(payload)
    (output/'package_manifest.json').write_bytes(sources['package_manifest.json'])
    for mode in ['validation','submission']:
        receipt={'status':'NOT_APPROVED','scope':'V28_'+mode.upper(),'package_manifest_sha256':mh,'builder':'Codex','reviewer':None,'authority':None,'record':None}
        setup=f'''from pathlib import Path
import base64, hashlib, io, json, os, subprocess, sys, time, zipfile
STARTED = time.perf_counter()
MODE = {mode!r}
RECEIPT = {receipt!r}
assert RECEIPT['status'] == 'APPROVED', 'Review the exact package and record Danny approval before execution'
assert RECEIPT['scope'] == 'V28_' + MODE.upper()
assert RECEIPT['package_manifest_sha256'] == {mh!r}
assert RECEIPT['reviewer'] == RECEIPT['authority'] == 'Danny' and RECEIPT['record']
assert sys.version_info[:2] == (3, 12), 'Offline wheel ABI requires Python 3.12'
WORK = Path('/kaggle/working')
ROOT = WORK / ('v28_' + MODE + '_package')
ROOT.mkdir(exist_ok=False)
payload = base64.b64decode({encoded!r})
assert hashlib.sha256(payload).hexdigest() == {sha(payload)!r}
with zipfile.ZipFile(io.BytesIO(payload)) as archive:
    for name in archive.namelist():
        assert (ROOT / name).resolve().is_relative_to(ROOT.resolve())
    archive.extractall(ROOT)
manifest = json.loads((ROOT / 'package_manifest.json').read_text())
assert hashlib.sha256((ROOT / 'package_manifest.json').read_bytes()).hexdigest() == {mh!r}
def verify(base, entries):
    for name, expected in entries.items():
        path = (base / name).resolve()
        assert path.is_relative_to(base.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
verify(ROOT, manifest['files'])
INPUT = Path('/kaggle/input')
def mount(name):
    matches = sorted(set(p for pattern in (name, '*/' + name, '*/*/' + name) for p in INPUT.glob(pattern) if p.is_dir()))
    assert len(matches) == 1, 'Missing/ambiguous mounted dataset: ' + name
    return matches[0]
SUPPORT = mount('biohub-tracking-support-pack-50ep-v1')
verify(SUPPORT, manifest['support_files'])
WEIGHTS = mount('v22-e016-clean-checkpoint') / 'edge_predictor_best.pth'
assert hashlib.sha256(WEIGHTS.read_bytes()).hexdigest() == manifest['candidate']['checkpoint_sha256']
assert hashlib.sha256((WEIGHTS.parent / 'config.json').read_bytes()).hexdigest() == manifest['candidate']['runtime_config_sha256']
DATA = mount('biohub-cell-tracking-during-development')
assert (DATA / 'test').is_dir(), 'Competition test directory missing'
DEPS = WORK / ('v28_' + MODE + '_deps')
assert not DEPS.exists()
wheels = [str(SUPPORT / n) for n in manifest['offline_install_wheels']] + [str(ROOT / n) for n in manifest['extra_install_wheels']]
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--target', str(DEPS), *wheels], check=True)
ENV = os.environ.copy()
ENV['PYTHONPATH'] = os.pathsep.join([str(DEPS), str(ROOT / 'src')])
receipt_path = WORK / ('v28_' + MODE + '_receipt.json')
assert not receipt_path.exists()
receipt_path.write_text(json.dumps(RECEIPT, indent=2) + '\\n')
OUTPUT = WORK / ('v28_' + MODE + '_run')
command = [sys.executable, '-u', str(ROOT / 'scripts/run_v28_submission.py'), '--package-root', str(ROOT), '--support-root', str(SUPPORT), '--weights', str(WEIGHTS), '--data-root', str(DATA), '--output-dir', str(OUTPUT), '--receipt', str(receipt_path), '--mode', MODE, '--setup-seconds', str(time.perf_counter() - STARTED)]
timeout = (7200 if MODE == 'validation' else 39600) - (time.perf_counter() - STARTED)
assert timeout > 0, 'Setup exhausted the reviewed job budget'
subprocess.run(command, check=True, env=ENV, timeout=timeout)
summary = json.loads((OUTPUT / 'summary.json').read_text())
assert summary['status'] == ('VALIDATION_COMPLETE' if MODE == 'validation' else 'SUBMISSION_CSV_COMPLETE')
if MODE == 'submission':
    destination = WORK / 'submission.csv'
    assert not destination.exists()
    (OUTPUT / 'submission.csv').replace(destination)
print(json.dumps({{'status':summary['status'], 'wall_seconds':summary['wall_seconds'], 'package_manifest_sha256':summary['package_manifest_sha256']}}, indent=2))
'''
        # Compilation validates generated syntax without approving or executing it.
        compile(setup,'V28_'+mode,'exec')
        notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.12'}},'cells':[{'cell_type':'markdown','metadata':{},'id':'purpose','source':[f'# V28 {mode}: frozen V24.3 offline delivery\n',f'Package manifest SHA-256: `{mh}`.\n','Attach the Biohub competition, the pinned support pack and clean E016 checkpoint. Internet disabled. GPU required. Review and record approval in RECEIPT before running. Validation does not produce the competition submission filename.\n']},{'cell_type':'code','execution_count':None,'outputs':[],'metadata':{},'id':'offline-run','source':setup.splitlines(keepends=True)}]}
        name='V28_'+mode+'_offline_kaggle.ipynb'
        (output/name).write_text(dump(notebook),encoding='utf-8',newline='\n')
        target=ROOT/'notebooks'/name
        target.write_text(dump(notebook),encoding='utf-8',newline='\n')
        # Metadata uses immutable dataset versions. No push is performed.
        metadata={'id':'drakus74/atabey-v28-'+mode,'title':'Atabey V28 '+mode,'code_file':name,'language':'python','kernel_type':'notebook','is_private':True,'enable_gpu':True,'enable_tpu':False,'enable_internet':False,'dataset_sources':[ref+'/'+str(v) for ref,v in manifest['dataset_versions'].items()],'competition_sources':['biohub-cell-tracking-during-development'],'kernel_sources':[],'model_sources':[]}
        (output/(mode+'-kernel-metadata.json')).write_text(dump(metadata))
        dispatch=output/('dispatch_'+mode)
        dispatch.mkdir()
        (dispatch/'kernel-metadata.json').write_text(dump(metadata))
        (dispatch/name).write_text(dump(notebook),encoding='utf-8',newline='\n')
    print(dump({'manifest_sha256':mh,'bundle_bytes':len(payload),'source_files':len(manifest['files']),'support_files':len(manifest['support_files']),'output':str(output)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--support-root',type=Path,required=True);p.add_argument('--extra-wheels',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();build(a.support_root,a.extra_wheels,a.output_dir)
