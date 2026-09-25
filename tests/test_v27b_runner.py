from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v27b_recursive_history as runner
from atabey.provenance import sha256_file,canonical_text_sha256
from atabey.tracking.association_factorial_audit import scientific_digest


@pytest.fixture
def fake_freeze(tmp_path, monkeypatch):
    """Explicit test-only review, runtime and evidence; never a cohort approval."""
    root=tmp_path/'repo'
    for relative in runner.required_source_paths(ROOT):
        dst=root/relative; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/relative,dst)
    report=root/'synthetic.xml'
    report.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"/>')
    monkeypatch.setattr(runner,'runtime_identity',lambda:{'explicit_synthetic_runtime':True})
    monkeypatch.setattr(runner,'verify_evidence',lambda contract,root:{'explicit_synthetic_evidence':True})
    manifest=runner.prepare_candidate(root,report)
    manifest['status']='FROZEN'; digest=manifest['payload_sha256']
    manifest['review']={'reviewer':'explicit_test_reviewer','record':'synthetic only','reviewed_payload_sha256':digest}
    manifest['human_execution_authorization']={'authority':'explicit_test_authority','record':'synthetic only','scope':runner.SCOPE,'approved_payload_sha256':digest}
    return root,manifest


def test_valid_explicit_fake_freeze_can_validate_without_executing(fake_freeze):
    root,manifest=fake_freeze
    assert runner.validate_freeze(manifest,root)['phase']==runner.SCOPE


@pytest.mark.parametrize('field',['review','human_execution_authorization'])
def test_missing_authority_rejected(fake_freeze,field):
    root,m=fake_freeze; m[field]=None
    with pytest.raises(RuntimeError,match='Missing human'):runner.validate_freeze(m,root)


def test_builder_is_not_reviewer(fake_freeze):
    root,m=fake_freeze; m['review']['reviewer']=m['payload']['builder']
    with pytest.raises(RuntimeError,match='distinct'):runner.validate_freeze(m,root)


def test_changed_payload_rejected(fake_freeze):
    root,m=fake_freeze; m['payload']['scope']='OTHER'
    with pytest.raises(RuntimeError,match='integrity/scope'):runner.validate_freeze(m,root)


def test_changed_source_rejected(fake_freeze):
    root,m=fake_freeze; (root/'src/atabey/tracking/recursive_history_audit.py').write_text('tampered')
    with pytest.raises(RuntimeError,match='source mismatch'):runner.validate_freeze(m,root)


def test_unpinned_source_rejected(fake_freeze):
    root,m=fake_freeze; m['payload']['canonical_sources'].pop('src/atabey/tracking/recursive_history_audit.py')
    digest=scientific_digest(m['payload']); m['payload_sha256']=digest
    m['review']['reviewed_payload_sha256']=digest; m['human_execution_authorization']['approved_payload_sha256']=digest
    with pytest.raises(RuntimeError,match='omits required'):runner.validate_freeze(m,root)


def test_runtime_drift_rejected(fake_freeze,monkeypatch):
    root,m=fake_freeze; monkeypatch.setattr(runner,'runtime_identity',lambda:{'different':True})
    with pytest.raises(RuntimeError,match='runtime mismatch'):runner.validate_freeze(m,root)


def test_test_evidence_drift_rejected(fake_freeze):
    root,m=fake_freeze; (root/'synthetic.xml').write_text('<testsuite tests="2" failures="0"/>')
    with pytest.raises(RuntimeError,match='test evidence mismatch'):runner.validate_freeze(m,root)


def test_v27a1_scope_cannot_authorize_v27b(fake_freeze):
    root,m=fake_freeze; m['human_execution_authorization']['scope']='V27A1_FIXED_HISTORY_CANDIDATE_WISE_GATES'
    with pytest.raises(RuntimeError,match='exact V27B'):runner.validate_freeze(m,root)


def test_contract_change_cannot_silently_enter_freeze(fake_freeze):
    root,m=fake_freeze; p=root/runner.CONTRACT
    c=json.loads(p.read_text()); c['boundaries']['new_official_matching_or_scoring']=True
    p.write_text(json.dumps(c))
    with pytest.raises(RuntimeError,match='contract identity'):runner.validate_freeze(m,root)


def test_real_entry_rejects_proposal_and_retains_failure(tmp_path):
    path=tmp_path/'candidate.json'; runner.write_json_new(path,{'status':'READY_FOR_HUMAN_REVIEW'})
    output=tmp_path/'attempt'
    with pytest.raises(RuntimeError,match='not FROZEN'):runner.execute(path,sha256_file(path),output)
    failure=json.loads((output/'invalid_execution.json').read_text())
    assert failure['status']=='INVALID_EXECUTION' and failure['completed_sample_ids']==[]
    assert (output/'artifact_inventory.json').is_file()
    with pytest.raises(FileExistsError):runner.execute(path,sha256_file(path),output)


def test_explicit_digest_required(tmp_path):
    path=tmp_path/'candidate.json'; runner.write_json_new(path,{'status':'FROZEN'})
    with pytest.raises(RuntimeError,match='approved freeze SHA'):runner.execute(path,'',tmp_path/'attempt')


def test_evidence_check_detects_byte_changes(tmp_path):
    p=tmp_path/'evidence'; p.write_bytes(b'abc')
    c={'inputs':{'synthetic':{'path':'evidence','bytes':3,'sha256':sha256_file(p)}},'reference_raw_artifacts':[],'reference_source_canonical_sha256':{}}
    assert runner.verify_evidence(c,tmp_path)
    p.write_bytes(b'abd')
    with pytest.raises(RuntimeError,match='input mismatch'):runner.verify_evidence(c,tmp_path)


def test_required_sources_cover_reviewed_contract_parent_and_new_implementation():
    paths=runner.required_source_paths(ROOT)
    assert {'V27B_RECURSIVE_HISTORY_PREREGISTRATION.md',runner.CONTRACT,
            'src/atabey/tracking/recursive_history_audit.py','scripts/run_v27a1_association_decomposition.py',
            'scripts/run_v27b_recursive_history.py','tests/test_v27b_recursive_history.py','tests/test_v27b_runner.py'}.issubset(paths)
