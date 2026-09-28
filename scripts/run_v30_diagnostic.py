"""One approved CPU diagnostic, or identity-only preflight. No inference/scoring."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
from importlib import metadata
import io
import json
import multiprocessing
from pathlib import Path
import platform
import sys
import time
import traceback
import zipfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from atabey.submission.v29a import digest, require, sha

PROPOSAL = 'v30_diagnostic_proposal_20260928.json'
SCOPE = 'ONE_CPU_SAVED_COORDINATE_DIAGNOSTIC_NO_SCORING'
PROTOCOL = 'V30_SAVED_COORDINATE_DIAGNOSTIC_V1'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data):
    """Exclusive output; an interrupted serialization remains inspectable."""
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, sort_keys=True, allow_nan=False, separators=(',', ':'))
        stream.write('\n')


def artifact(root, item):
    path = (root / item['path']).resolve()
    require(path.is_relative_to(root.resolve()), 'Input escapes repository')
    require(path.is_file() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256'],
            'Input identity mismatch: ' + item['path'])
    return path


def identity(root, path):
    path = Path(path)
    return {'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def verify_candidate(root, path):
    candidate = load(path)
    require(candidate['protocol'] == PROTOCOL and candidate['status'] == 'IMPLEMENTED_AWAITING_REVIEW', 'Wrong implementation candidate')
    require(candidate['execution_authorized'] is False, 'Candidate must not self-authorize')
    paths = [x['path'] for x in candidate['artifacts']]
    require(len(paths) == len(set(paths)), 'Duplicate candidate artifacts')
    required = {PROPOSAL, 'V30_DIAGNOSTIC_CONTRACT.md', 'V30_IMPLEMENTATION_REVIEW.md',
                'src/atabey/tracking/v30_diagnostic.py', 'scripts/run_v30_diagnostic.py',
                'tests/test_v30_diagnostic.py', 'outputs/v30_implementation_20260928/tests_release.xml'}
    require(required <= set(paths), 'Incomplete implementation binding')
    for item in candidate['artifacts']:
        artifact(root, item)
    return candidate


def validate_receipt(receipt, candidate_path, output):
    require(receipt.get('status') == 'APPROVED_FROZEN' and receipt.get('authority') == 'Danny', 'Explicit approval required')
    require(receipt.get('scope') == SCOPE and receipt.get('protocol') == PROTOCOL, 'Wrong approval scope')
    require(receipt.get('candidate_sha256') == sha(candidate_path), 'Approval/candidate mismatch')
    require(isinstance(receipt.get('approval_record'), str) and bool(receipt['approval_record'].strip()), 'Missing human approval record')
    require(receipt.get('execution_id') == output.name and Path(receipt.get('output_directory', '')).is_absolute()
            and Path(receipt['output_directory']).resolve() == output.resolve(), 'Approval/output mismatch')
    require(receipt.get('submission_authorized') is False and receipt.get('new_scoring_authorized') is False, 'Approval exceeds diagnostic scope')


def preflight(root, proposal, checkpoint=lambda: None):
    require(proposal['protocol'] == PROTOCOL and proposal['execution_authorized'] is False, 'Wrong proposal')
    ids = proposal['sample_order']
    require(ids == sorted(proposal['samples']) and len(ids) == 199, 'Cohort changed')
    require(proposal['budget'] == {'gpu_seconds': 0, 'resident_sample_pairs': 1, 'wall_seconds': 7200}, 'Budget changed')
    require(proposal['geometry']['near_radius_um'] == 2.0 and proposal['geometry']['scale_zyx_um'] == [1.625, .40625, .40625], 'Geometry changed')
    inventory = list(proposal['references']) + list(proposal['scientific_sources'])
    for info in proposal['samples'].values():
        for arm in ('baseline', 'tta'):
            inventory.extend((info['arms'][arm]['record'], info['arms'][arm]['coordinates']))
    for item in inventory:
        checkpoint()
        artifact(root, item)
    releases = {}
    for name in ('v28_release_freeze_20260928.json', 'v29a_release_freeze_20260928.json'):
        freeze = load(root / name)
        require(digest(freeze['payload']) == freeze['payload_sha256'], 'Release payload changed')
        for item in freeze['payload']['artifacts']:
            checkpoint()
            artifact(root, item)
        releases[name] = len(freeze['payload']['artifacts'])
    package = root / 'outputs/v29a_preparation_20260928/package_r1'
    manifest = load(package / 'package_manifest.json')
    with zipfile.ZipFile(package / 'v29a_source_bundle.zip') as bundle:
        require(bundle.read('package_manifest.json') == (package / 'package_manifest.json').read_bytes(), 'Embedded manifest changed')
        for name, expected in manifest['files'].items():
            checkpoint()
            data = bundle.read(name)
            require(hashlib.sha256(data).hexdigest() == expected, 'Bundle member changed')
            if name.startswith(('src/', 'scripts/')):
                require((root / name).read_bytes().replace(b'\r\n', b'\n') == data, 'Frozen source changed')
    runtime = {'python': platform.python_version(), 'system': platform.system(), 'machine': platform.machine(),
               'packages': {name: metadata.version(name) for name in proposal['runtime']['packages']}}
    require(runtime == proposal['runtime'], 'Pinned runtime changed')
    run = root / 'outputs/v29a_execution_20260928/downloaded/v29a_run'
    parent = load(root / 'tests/fixtures/v29a_tta.json')
    result = load(root / 'outputs/v29a_execution_20260928/local_evaluation/result.json')
    summary = load(run / 'summary.json')
    files = {r['path']: r for r in summary['files']}
    require(len(files) == len(summary['files']), 'Duplicate manifest entries')
    require(summary['candidate_ids'] == ids == summary['baseline_ids'] == sorted(parent['samples']), 'Parent cohort mismatch')
    require(sorted(r['sample_id'] for r in result['rows']) == ids, 'Official row coverage mismatch')
    require(result['inference_summary_sha256'] == sha(run / 'summary.json'), 'Result lineage mismatch')
    require(result['package_manifest_sha256'] == summary['package_manifest_sha256'] == sha(package / 'package_manifest.json'), 'Package lineage mismatch')
    require(proposal['existing_strata'] == parent['strata'], 'Strata changed')
    require(proposal['protected_ids'] == sorted(parent['catastrophic_ids']), 'Protected IDs changed')
    require(proposal['focus_loss_ids'] == sorted(s for s, d in result['decision']['score_deltas'].items() if d < -.020), 'Focus changed')
    require(proposal['focus_union'] == sorted(set(proposal['protected_ids']) | set(proposal['focus_loss_ids'])), 'Focus union mismatch')
    for arm, prefix in [('baseline', 'baseline'), ('tta', '')]:
        base = run / prefix
        for folder, suffix in [('coordinates', '.npy'), ('records', '.json')]:
            require(sorted(p.stem for p in (base / folder).glob('*' + suffix)) == ids, 'Unexpected/missing cohort files')
        for sid in ids:
            checkpoint()
            info = proposal['samples'][sid]
            expected = info['arms'][arm]
            record = load(root / expected['record']['path'])
            require(record['sample_id'] == sid and record['shape'] == info['shape_tzyx'] == parent['samples'][sid]['image_metadata']['shape'], 'Sample metadata mismatch')
            require(record['route']['apply_pruning'] == info['pruning_enabled'] == parent['samples'][sid]['pruning_eligible'], 'Route mismatch')
            require(record['scale'] == [1.0, 1.625, .40625, .40625], 'Scale mismatch')
            require(record['graph_signature_sha256'] == expected['expected_final_signature'], 'Signature reference mismatch')
            if arm == 'baseline':
                require(record['graph_signature_sha256'] == parent['samples'][sid]['baseline_graph_sha256'], 'Historical graph mismatch')
            require((base / record['coordinates']['path']).resolve() == (root / expected['coordinates']['path']).resolve(), 'Coordinate path mismatch')
            for field in ('bytes', 'sha256'):
                require(record['coordinates'][field] == expected['coordinates'][field], 'Record coordinate identity mismatch')
            for kind in ('record', 'coordinates'):
                relative = (root / expected[kind]['path']).relative_to(run).as_posix()
                require(all(files[relative][k] == expected[kind][k] for k in ('bytes', 'sha256')), 'Manifest lineage mismatch')
    require(proposal['new_route_groups'] == {str(flag).lower(): [s for s in ids if proposal['samples'][s]['pruning_enabled'] == flag] for flag in (False, True)}, 'Route groups changed')
    return {'status': 'INPUT_IDENTITIES_VERIFIED', 'files_verified': len(inventory),
            'releases': releases, 'runtime': runtime, 'graph_replay_performed': False}, result


def write_compressed(path, data):
    with path.open('xb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding='utf-8', newline='\n') as text:
                json.dump(data, text, sort_keys=True, allow_nan=False, separators=(',', ':'))
                text.write('\n')


def summarize_groups(rows, groups):
    by_id = {r['sample_id']: r for r in rows}
    require(len(by_id) == len(rows), 'Duplicate diagnostic sample rows')
    result = {}
    for name, ids in groups.items():
        require(len(set(ids)) == len(ids) and set(ids) <= set(by_id), 'Invalid group membership')
        group = {'sample_ids': ids, 'count': len(ids), 'coordinate_counts': {}, 'coordinate_fractions': {},
                 'coordinate_denominators': {}, 'views': {}}
        for arm in ('baseline', 'tta'):
            counts = Counter()
            for sid in ids:
                counts.update(by_id[sid]['coordinate_counts'][arm])
            denominator = sum(counts.values())
            group['coordinate_counts'][arm] = dict(sorted(counts.items()))
            group['coordinate_denominators'][arm] = denominator
            group['coordinate_fractions'][arm] = {k: v / denominator if denominator else None for k, v in counts.items()}
        for view in ('EXACT_ONLY', 'EXACT_PLUS_NEAR'):
            edges, history = {}, Counter()
            for stage in ('RAW', 'P2', 'P3'):
                counts = Counter()
                maximum = 0.0
                for sid in ids:
                    row = by_id[sid]['views'][view]['edges'][stage]
                    counts.update({k: v for k, v in row.items() if k != 'max_absolute_confidence_difference'})
                    maximum = max(maximum, row['max_absolute_confidence_difference'])
                edges[stage] = {**dict(counts), 'max_absolute_confidence_difference': maximum}
            for sid in ids:
                for r in by_id[sid]['views'][view]['history_cross_tab']:
                    history[(r['outgoing'], r['immediate_history'], r['recursive_history'])] += r['count']
            group['views'][view] = {'edges': edges, 'history_cross_tab': [
                {'outgoing': k[0], 'immediate_history': k[1], 'recursive_history': k[2], 'count': v}
                for k, v in sorted(history.items())]}
        result[name] = group
    return result


def worker(root_string, candidate_string, receipt_string, output_string, deadline):
    root, candidate_path, receipt_path, out = map(Path, (root_string, candidate_string, receipt_string, output_string))
    completed = []
    initial_bindings = {'candidate_sha256': sha(candidate_path), 'receipt_sha256': sha(receipt_path)}
    def check():
        if time.monotonic() >= deadline:
            raise TimeoutError('Two-hour wall budget exhausted')
    try:
        check()
        verify_candidate(root, candidate_path)
        validate_receipt(load(receipt_path), candidate_path, out)
        proposal = load(root / PROPOSAL)
        audit, official = preflight(root, proposal, check)
        save(out / 'preflight.json', audit)
        # Scientific imports occur only after the approved-input preflight.
        import numpy as np
        from atabey.tracking.v30_diagnostic import diagnose_pair
        by_id = {row['sample_id']: row for row in official['rows']}
        rows = []
        (out / 'samples').mkdir()
        (out / 'rows').mkdir()
        for sid in proposal['sample_order']:
            check()
            info = proposal['samples'][sid]
            arrays, records = {}, {}
            for arm in ('baseline', 'tta'):
                item = info['arms'][arm]
                records[arm] = load(artifact(root, item['record']))
                arrays[arm] = np.load(artifact(root, item['coordinates']), allow_pickle=False)
            detail, row = diagnose_pair(sid, arrays, info, records, by_id[sid], check)
            check()
            detail_path = out / 'samples' / (sid + '.json.gz')
            write_compressed(detail_path, detail)
            row['detail'] = identity(out, detail_path)
            save(out / 'rows' / (sid + '.json'), row)
            rows.append(row)
            completed.append(sid)
            del arrays, records, detail, row
        check()
        closure, _ = preflight(root, proposal, check)
        verify_candidate(root, candidate_path)
        validate_receipt(load(receipt_path), candidate_path, out)
        require(initial_bindings == {'candidate_sha256': sha(candidate_path), 'receipt_sha256': sha(receipt_path)}, 'Execution bindings changed during run')
        require(sum(r['final_graph_export_parities'] for r in rows) == 398, 'Incomplete replay parity')
        for row in rows:
            check()
            artifact(out, row['detail'])
            require(load(out / 'rows' / (row['sample_id'] + '.json')) == row, 'Diagnostic row changed during run')
        groups = dict(proposal['existing_strata'])
        groups.update({'pruning_' + k: v for k, v in proposal['new_route_groups'].items()})
        groups.update(focus=proposal['focus_union'], protected=proposal['protected_ids'], strong_losses=proposal['focus_loss_ids'])
        result = {'status': 'COMPLETE_DESCRIPTIVE_DIAGNOSTIC', 'completed_ids': completed, 'rows': rows,
                  'groups': summarize_groups(rows, groups),
                  'existing_official_aggregates': official['summaries'], 'existing_official_strata': official['strata'],
                  'v29a_decision_unchanged': official['decision'], 'closure': closure,
                  'candidate_sha256': sha(candidate_path), 'receipt_sha256': sha(receipt_path),
                  'independent_validation': False, 'new_scoring_performed': False,
                  'causal_attribution': False, 'submission_authorized': False}
        check()
        save(out / 'completed_payload.json', result)
    except Exception as exc:
        save(out / 'worker_failure.json', {'status': 'BUDGET_EXHAUSTED_INCOMPLETE' if isinstance(exc, TimeoutError) else 'INVALID_INCOMPLETE',
                                          'completed_ids': completed, 'error_type': type(exc).__name__,
                                          'error': str(exc), 'traceback': traceback.format_exc()})
        raise


def bounded_worker(target, args, seconds):
    """A parent-enforced bound also interrupts a long C-extension operation."""
    require(seconds > 0, 'No execution time remaining')
    process = multiprocessing.get_context('spawn').Process(target=target, args=args)
    process.start()
    process.join(seconds)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
    return timed_out, process.exitcode


def report(result):
    lines = ['# V30 descriptive diagnostic', '', 'Status: COMPLETE_DESCRIPTIVE_DIAGNOSTIC.', '',
             '199 paired samples; 398 final graph/export parities. No new official scoring.',
             'All data were previously opened. Correspondence is geometric, not biological identity.',
             'V29A remains NO_GO. Tie/order/eligibility causal mechanisms were not measured.', '',
             '## Coverage', '', '| Group | Samples |', '| --- | ---: |']
    lines.extend(f'| {name} | {group["count"]} |' for name, group in result['groups'].items())
    lines += ['', 'Groups overlap. Official aggregate scores are copied in result.json, not averaged from samples.', '',
              '## All samples', '', '| Sample | Existing score delta | Exact pairs | Near pairs | Evidence |', '| --- | ---: | ---: | ---: | --- |']
    for row in result['rows']:
        exact = row['views']['EXACT_ONLY']['mapped_pairs']
        near = row['views']['EXACT_PLUS_NEAR']['mapped_pairs'] - exact
        lines.append(f'| {row["sample_id"]} | {row["official_metrics"]["delta"]["score"]:.9f} | {exact} | {near} | [detail]({row["detail"]["path"]}) |')
    lines += ['', '## Frozen focus', '']
    for sid in result['groups']['focus']['sample_ids']:
        lines.append(f'- [{sid} summary](rows/{sid}.json); [full tables](samples/{sid}.json.gz).')
    lines += ['', '## Interpretation boundary', '',
              'Stage removals, association changes and history differences describe where outputs differ.',
              'Co-occurrence with opened score losses does not identify their causal contribution.',
              'Inspect exact-only coverage before interpreting supplementary near correspondences.',
              'The next step is evidence review and a separately specified intervention if justified.', '']
    return '\n'.join(lines)


def main():
    start = time.monotonic()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--receipt', type=Path)
    p.add_argument('--preflight-only', action='store_true')
    args = p.parse_args()
    candidate_path, out = args.candidate.resolve(), args.output_dir.resolve()
    verify_candidate(ROOT, candidate_path)
    if not args.preflight_only:
        require(args.receipt is not None, 'Execution requires a separate frozen approval receipt')
        validate_receipt(load(args.receipt), candidate_path, out)
    require(out.is_relative_to((ROOT / 'outputs').resolve()), 'Output must be under repository outputs')
    out.mkdir(parents=True, exist_ok=False)
    if args.preflight_only:
        try:
            audit, _ = preflight(ROOT, load(ROOT / PROPOSAL))
            audit.update(candidate_sha256=sha(candidate_path), scientific_execution_performed=False)
            save(out / 'preflight.json', audit)
        except Exception as exc:
            save(out / 'failure.json', {'status': 'PREFLIGHT_FAILED', 'error': str(exc)})
            raise
        return
    receipt_path = args.receipt.resolve()
    save(out / 'execution.json', {'started_at_utc': datetime.now(timezone.utc).isoformat(),
                                'candidate_sha256': sha(candidate_path), 'receipt': load(receipt_path),
                                'receipt_sha256': sha(receipt_path), 'wall_limit_seconds': 7200})
    try:
        timed_out, code = bounded_worker(worker, (str(ROOT), str(candidate_path), str(receipt_path), str(out), start + 7200),
                                         7200 - (time.monotonic() - start))
        if timed_out or time.monotonic() - start >= 7200:
            raise TimeoutError('Two-hour wall budget exhausted; worker stopped')
        require(code == 0, f'Worker failed with exit code {code}; inspect worker_failure.json')
        result = load(out / 'completed_payload.json')
        execution = load(out / 'execution.json')
        require(result['candidate_sha256'] == execution['candidate_sha256'] == sha(candidate_path), 'Candidate binding changed')
        require(result['receipt_sha256'] == execution['receipt_sha256'] == sha(receipt_path), 'Receipt binding changed')
        result['wall_seconds'] = time.monotonic() - start
        save(out / 'result.json', result)
        with (out / 'REPORT.md').open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(report(result))
        if time.monotonic() - start >= 7200:
            raise TimeoutError('Two-hour wall budget exhausted during final serialization')
        save(out / 'finished.json', {'status': 'COMPLETE_DESCRIPTIVE_DIAGNOSTIC',
                                    'wall_seconds': time.monotonic() - start,
                                    'result': identity(out, out / 'result.json'),
                                    'report': identity(out, out / 'REPORT.md')})
    except Exception as exc:
        completed = sorted(path.stem for path in (out / 'rows').glob('*.json')) if (out / 'rows').exists() else []
        failure = {'status': 'BUDGET_EXHAUSTED_INCOMPLETE' if isinstance(exc, TimeoutError) else 'INVALID_INCOMPLETE',
                   'error': str(exc), 'completed_ids': completed, 'wall_seconds': time.monotonic() - start,
                   'partial_payload_is_not_completion': True}
        save(out / 'failure.json', failure)
        raise


if __name__ == '__main__':
    main()
