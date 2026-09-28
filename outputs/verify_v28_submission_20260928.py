"""Read-only verification of the approved visible V28 submission run."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/v28_submission_20260928'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    target = OUT / 'visible_verification.json'
    assert not target.exists(), 'Preserve previous verification'
    frozen = json.loads((ROOT / 'v28_submission_freeze_approved_20260928.json').read_text())
    previous = json.loads((ROOT / 'v28_validation_freeze_approved_20260928.json').read_text())
    identities = previous['payload']['artifacts'] + [frozen['candidate_identity'],
        frozen['dispatch']['notebook'], frozen['dispatch']['metadata'],
        frozen['payload']['validation_result']]
    for item in identities:
        path = ROOT / item['path']
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], str(path)
    run = OUT / 'downloaded/v28_submission_run'
    summary = json.loads((run / 'summary.json').read_text())
    validation = json.loads((ROOT / 'outputs/v28_validation_20260928/downloaded/v28_validation_run/summary.json').read_text())
    assert summary['status'] == 'SUBMISSION_CSV_COMPLETE' and summary['mode'] == 'submission'
    assert summary['receipt'] == frozen['execution_receipt']
    assert summary['package_manifest_sha256'] == frozen['payload']['package_manifest_sha256']
    assert not summary['kaggle_submission_performed']
    assert 'parity' not in summary and not list(run.glob('*parity*'))
    actual = summary['visible_or_hidden_test']
    expected = validation['visible_or_hidden_test']
    rows = actual['samples']
    assert [r['sample_id'] for r in rows] == [r['sample_id'] for r in expected['samples']]
    fields = ('graph_signature_sha256', 'shape', 'rows', 'nodes', 'edges',
              'raw_nodes', 'raw_edges', 'rounded_nodes', 'export_rows_sha256')
    for r, baseline in zip(rows, expected['samples']):
        assert all(r[k] == baseline[k] for k in fields), r['sample_id']
        assert r['route']['apply_pruning'] == baseline['route']['apply_pruning']
        assert json.loads((run / (r['sample_id'] + '.record.json')).read_text()) == r
    csv = OUT / 'downloaded/submission.csv'
    assert sha(csv) == actual['csv_sha256'] == expected['csv_sha256']
    sys.path.insert(0, str(ROOT / 'src'))
    from atabey.submission.v28 import validate_csv
    assert validate_csv(csv, rows) == actual['csv_validation'] == expected['csv_validation']
    assert summary['runtime']['gpu'] == validation['runtime']['gpu']
    assert summary['runtime']['cuda'] == validation['runtime']['cuda']
    for package in ('torch', 'numpy', 'scipy', 'pandas', 'zarr', 'tracksdata', 'scikit-image'):
        assert summary['runtime']['packages'][package] == validation['runtime']['packages'][package], package
    assert summary['wall_seconds'] <= frozen['payload']['per_execution_wall_cap_seconds']
    assert not list((OUT / 'downloaded').rglob('FAILURE.json'))
    record = {'status': 'PASS', 'builder_verification_not_independent_review': True,
        'sample_count': len(rows), 'csv_rows': actual['csv_validation']['rows'],
        'csv_sha256': actual['csv_sha256'], 'csv_bytes': csv.stat().st_size,
        'all_visible_graphs_and_csv_identical_to_validation': True,
        'wall_seconds': summary['wall_seconds'], 'gpu': summary['runtime']['gpu'],
        'package_manifest_sha256': summary['package_manifest_sha256'],
        'competition_submission_authorized': True, 'competition_submission_performed': False,
        'new_inference_in_local_verifier': False, 'new_scoring': False,
        'hidden_runtime_verified': False,
        'artifacts': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                       'sha256': sha(p)} for p in sorted((OUT / 'downloaded').rglob('*')) if p.is_file()]}
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k != 'artifacts'}, indent=2))


if __name__ == '__main__':
    main()
