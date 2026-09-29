"""Inventory existing evidence for a proposed diagnostic; no graph replay/scoring."""
from datetime import datetime, timezone
from importlib import metadata
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from atabey.submission.v29a import digest, require, sha


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def identity(path):
    p = ROOT / path
    return {'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}


def save_new(path, data):
    with (ROOT / path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')


def main():
    out = ROOT / 'outputs/v30_preparation_20260928'
    out.mkdir(exist_ok=False)
    audit = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
             'graph_replay_performed': False, 'coordinate_comparison_performed': False,
             'inference_performed': False, 'scoring_performed': False}
    try:
        release_checks = {}
        for name in ['v28_release_freeze_20260928.json', 'v29a_release_freeze_20260928.json']:
            freeze = read(name)
            require(digest(freeze['payload']) == freeze['payload_sha256'], 'Release payload mismatch')
            for item in freeze['payload']['artifacts']:
                require(identity(item['path']) == item, 'Frozen artifact mismatch: ' + item['path'])
            release_checks[name] = {'artifacts_verified': len(freeze['payload']['artifacts']),
                                   'identity': identity(name)}
        parent = read('tests/fixtures/v29a_tta.json')
        package = 'outputs/v29a_preparation_20260928/package_r1/'
        manifest = read(package + 'package_manifest.json')
        expected_manifest = '7d93749e50dfe95fa1643dceb39e870f9111850ce994c14c30ca1496ddd4dc67'
        require(sha(ROOT / package / 'package_manifest.json') == expected_manifest, 'Package mismatch')
        sources = []
        with zipfile.ZipFile(ROOT / package / 'v29a_source_bundle.zip') as bundle:
            require(bundle.read('package_manifest.json') == (ROOT / package / 'package_manifest.json').read_bytes(), 'Embedded manifest mismatch')
            for name, expected in manifest['files'].items():
                data = bundle.read(name)
                require(hashlib.sha256(data).hexdigest() == expected, 'Bundle member mismatch')
                if name.startswith(('src/', 'scripts/')):
                    require((ROOT / name).read_bytes().replace(b'\r\n', b'\n') == data, 'Source mismatch: ' + name)
                    sources.append(identity(name))
        runtime = {'python': platform.python_version(), 'system': platform.system(),
                   'machine': platform.machine(), 'packages': {
                       name: metadata.version(name) for name in parent['local_runtime']['packages']}}
        require(runtime == parent['local_runtime'], 'Runtime mismatch')
        run = 'outputs/v29a_execution_20260928/downloaded/v29a_run/'
        summary = read(run + 'summary.json')
        result_path = 'outputs/v29a_execution_20260928/local_evaluation/result.json'
        result = read(result_path)
        require(summary['package_manifest_sha256'] == expected_manifest == result['package_manifest_sha256'], 'Result lineage mismatch')
        require(result['inference_summary_sha256'] == sha(ROOT / run / 'summary.json'), 'Summary lineage mismatch')
        file_map = {item['path']: item for item in summary['files']}
        require(len(file_map) == len(summary['files']), 'Duplicate output paths')
        ids = sorted(parent['samples'])
        require(len(ids) == 199 and summary['baseline_ids'] == ids == summary['candidate_ids'], 'Cohort mismatch')
        require(sorted(row['sample_id'] for row in result['rows']) == ids, 'Official rows mismatch')
        samples = {}
        for sid in ids:
            sample = parent['samples'][sid]
            arms = {}
            for arm, prefix in [('baseline', 'baseline/'), ('tta', '')]:
                record_rel = prefix + 'records/' + sid + '.json'
                record = read(run + record_rel)
                require(record['sample_id'] == sid, 'Record sample mismatch')
                require(record['route']['apply_pruning'] == sample['pruning_eligible'], 'Route mismatch')
                require(record['shape'] == sample['image_metadata']['shape'], 'Shape mismatch')
                require(record['scale'] == [1.0, 1.625, 0.40625, 0.40625], 'Scale mismatch')
                coordinate_rel = prefix + record['coordinates']['path']
                require(coordinate_rel == prefix + 'coordinates/' + sid + '.npy', 'Coordinate path mismatch')
                for rel in [record_rel, coordinate_rel]:
                    observed = identity(run + rel)
                    expected = file_map[rel]
                    require(observed['sha256'] == expected['sha256'] and observed['bytes'] == expected['bytes'], 'Downloaded identity mismatch: ' + rel)
                coord = identity(run + coordinate_rel)
                require(coord['sha256'] == record['coordinates']['sha256'] and coord['bytes'] == record['coordinates']['bytes'], 'Record coordinate mismatch')
                if arm == 'baseline':
                    require(record['graph_signature_sha256'] == sample['baseline_graph_sha256'], 'Historical graph mismatch')
                arms[arm] = {'coordinates': coord, 'record': identity(run + record_rel),
                             'expected_final_signature': record['graph_signature_sha256']}
            samples[sid] = {'arms': arms, 'pruning_enabled': sample['pruning_eligible'],
                            'shape_tzyx': sample['image_metadata']['shape']}
        deltas = result['decision']['score_deltas']
        require(sorted(deltas) == ids, 'Delta coverage mismatch')
        losses = sorted(sid for sid in ids if deltas[sid] < -0.020)
        require(len(losses) == 25, 'Opened focus count mismatch')
        protected = sorted(parent['catastrophic_ids'])
        require(len(protected) == 4 and set(protected) <= set(ids), 'Protected coverage mismatch')
        refs = [result_path, run + 'summary.json', 'tests/fixtures/v29a_tta.json',
                package + 'package_manifest.json', package + 'v29a_source_bundle.zip',
                'v29a_research_freeze_approved_20260928.json',
                'v28_release_freeze_20260928.json', 'v29a_release_freeze_20260928.json',
                'outputs/v29a_execution_20260928/final_evidence_verification.json',
                'V29A_RESULTS.md', 'V29A_LESSONS_LEARNED.md', 'V30_DIAGNOSTIC_CONTRACT.md']
        proposal = {
            'protocol': 'V30_SAVED_COORDINATE_DIAGNOSTIC_V1',
            'status': 'PROPOSED_IMPLEMENTATION_PENDING',
            'execution_authorized': False, 'submission_authorized': False,
            'independent_validation': False, 'causal_attribution_authorized': False,
            'builder': 'Codex', 'reviewer': 'Danny', 'authority': 'Danny',
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'references': [identity(p) for p in refs], 'scientific_sources': sources,
            'runtime': runtime, 'samples': samples, 'sample_order': ids,
            'existing_strata': parent['strata'], 'focus_loss_ids': losses,
            'protected_ids': protected, 'focus_union': sorted(set(losses) | set(protected)),
            'focus_selection': 'Previously opened V29A score delta < -0.020; union all four protected IDs',
            'new_route_groups': {str(flag).lower(): [sid for sid in ids if samples[sid]['pruning_enabled'] == flag] for flag in [False, True]},
            'geometry': {'scale_zyx_um': [1.625, 0.40625, 0.40625], 'near_radius_um': 2.0,
                         'primary': 'unique exact coordinates', 'secondary': 'degree-one non-exact pairs in full eligible bipartite radius graph',
                         'duplicate_coordinates': 'ambiguous; excluded from correspondence',
                         'iterative_rematching': False, 'gt_matching': False},
            'stages': ['RAW', 'P2_OR_BYPASS', 'P3_OR_BYPASS_FINAL'],
            'budget': {'wall_seconds': 7200, 'gpu_seconds': 0, 'resident_sample_pairs': 1},
            'implementation': None, 'implementation_review_complete': False,
            'execution_receipt_required': True,
            'forbidden': ['new_inference', 'raw_image_access', 'new_gt_scoring', 'parameter_sweep',
                          'sample_selector', 'competition_submission', 'selection_change', 'automatic_retry'],
        }
        proposal_path = 'v30_diagnostic_proposal_20260928.json'
        save_new(proposal_path, proposal)
        audit.update(status='PREPARATION_INPUT_IDENTITIES_VERIFIED',
                     completed_at_utc=datetime.now(timezone.utc).isoformat(),
                     release_checks=release_checks, source_files_verified=len(sources),
                     package_members_verified=len(manifest['files']), sample_pairs=199,
                     coordinate_files_verified=398, inference_records_verified=398,
                     focus_loss_count=len(losses), focus_union_count=len(proposal['focus_union']),
                     runtime_verified=runtime, proposal=identity(proposal_path),
                     preparation_script=identity('outputs/prepare_v30_diagnostic_20260928.py'))
        save_new('outputs/v30_preparation_20260928/input_audit.json', audit)
        print(json.dumps({k: audit[k] for k in ['status', 'sample_pairs', 'coordinate_files_verified', 'focus_loss_count', 'focus_union_count', 'source_files_verified']}))
    except Exception as exc:
        audit.update(status='PREPARATION_FAILED', error_type=type(exc).__name__, error=str(exc))
        save_new('outputs/v30_preparation_20260928/preparation_failure.json', audit)
        raise


if __name__ == '__main__':
    main()
