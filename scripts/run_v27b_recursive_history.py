"""V27B frozen execution boundary; no scoring, tuning, or production dispatch."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import time
import tracemalloc
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]

import run_v27a1_association_decomposition as parent
from atabey.provenance import canonical_text_sha256, sha256_file
from atabey.tracking.association_factorial_audit import scientific_digest
from atabey.tracking.recursive_history_audit import (
    ARM_IDS, STAGES, graph_digest, recursive_graphs, pruning_stages,
)

CONTRACT = 'tests/fixtures/v27b_recursive_history.json'
SCOPE = 'V27B_RECURSIVE_HISTORY_AND_PRUNING_RESPONSE'
# The reviewed proposal is an input, not a mutable configuration surface.
CONTRACT_SHA256 = 'ef100eb744dae0fea201bfbf72194d03b3e5970d3e35100054d270c73f2c6064'
write_json_new = parent.write_json_new
runtime_identity = parent.runtime_identity
test_report_identity = parent.test_report_identity


def science_contract(root):
    if sha256_file(root / CONTRACT) != CONTRACT_SHA256:
        raise RuntimeError('Reviewed V27B contract identity mismatch')
    contract = json.loads((root / CONTRACT).read_text(encoding='utf-8'))
    protocol = contract['protocol']
    if canonical_text_sha256(parent._safe_path(root, protocol['path'])) != protocol['canonical_sha256']:
        raise RuntimeError('Reviewed V27B protocol identity mismatch')
    return contract


def required_source_paths(root):
    contract = science_contract(root)
    return parent.required_source_paths(root) | set(contract['reference_source_canonical_sha256']) | {
        CONTRACT, contract['protocol']['path'], 'scripts/run_v27b_recursive_history.py',
        'tests/test_v27b_recursive_history.py', 'tests/test_v27b_runner.py',
    }


def verify_evidence(contract, root):
    identities = {}
    for item in [*contract['inputs'].values(), *contract['reference_raw_artifacts']]:
        path = parent._safe_path(root, item['path'])
        value = {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        if value != {k: item[k] for k in ('bytes', 'sha256')}:
            raise RuntimeError(f'Frozen input mismatch: {item["path"]}')
        identities[item['path']] = value
    for path, digest in contract['reference_source_canonical_sha256'].items():
        if canonical_text_sha256(parent._safe_path(root, path)) != digest:
            raise RuntimeError(f'Parent frozen source mismatch: {path}')
    return identities


def prepare_candidate(root, test_report):
    contract = science_contract(root)
    report = test_report.resolve().relative_to(root.resolve()).as_posix()
    payload = {'scope': SCOPE, 'builder': 'Codex', 'contract_path': CONTRACT,
               'canonical_sources': {p: canonical_text_sha256(root / p) for p in sorted(required_source_paths(root))},
               'inputs': verify_evidence(contract, root), 'runtime': runtime_identity(),
               'test_report': {'path': report, **test_report_identity(test_report)}}
    return {'status': 'READY_FOR_HUMAN_REVIEW', 'payload': payload,
            'payload_sha256': scientific_digest(payload), 'review': None,
            'human_execution_authorization': None}


def validate_freeze(manifest, root):
    if manifest.get('status') != 'FROZEN':
        raise RuntimeError('V27B freeze is not FROZEN')
    payload = manifest['payload']
    digest = scientific_digest(payload)
    if (manifest.get('payload_sha256') != digest or payload['scope'] != SCOPE or
            payload['contract_path'] != CONTRACT):
        raise RuntimeError('Freeze payload integrity/scope mismatch')
    review, authorization = manifest.get('review'), manifest.get('human_execution_authorization')
    if not isinstance(review, dict) or not isinstance(authorization, dict):
        raise RuntimeError('Missing human review or authorization')
    if (not review.get('reviewer') or review['reviewer'] == payload['builder'] or
            review.get('reviewed_payload_sha256') != digest or not review.get('record')):
        raise RuntimeError('Review must identify a reviewer distinct from builder and exact payload')
    if (not authorization.get('authority') or not authorization.get('record') or
            authorization.get('approved_payload_sha256') != digest or authorization.get('scope') != SCOPE):
        raise RuntimeError('Human authorization does not cover this exact V27B payload')
    contract = science_contract(root)
    if not required_source_paths(root).issubset(payload['canonical_sources']):
        raise RuntimeError('Freeze omits required scientific sources')
    for path, digest in payload['canonical_sources'].items():
        if canonical_text_sha256(parent._safe_path(root, path)) != digest:
            raise RuntimeError(f'Frozen source mismatch: {path}')
    if scientific_digest(payload['runtime']) != scientific_digest(runtime_identity()):
        raise RuntimeError('Frozen runtime mismatch')
    report = payload['test_report']
    if test_report_identity(parent._safe_path(root, report['path'])) != {k: v for k, v in report.items() if k != 'path'}:
        raise RuntimeError('Frozen test evidence mismatch')
    if verify_evidence(contract, root) != payload['inputs']:
        raise RuntimeError('Frozen input inventory mismatch')
    return contract


@contextmanager
def scientific_stream(path):
    with path.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            def emit(record):
                compressed.write((json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode())
            yield emit


def read_frames(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            yield json.loads(line)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_sample_pass(record, baseline, anchors, output):
    """Fresh pass directory; verified local reference is never built into an F graph."""
    output.mkdir(exist_ok=False)
    fpath = output / 'frozen.jsonl.gz'
    fresult = parent.replay_sample(record, baseline, fpath)
    check(fresult['frame_stream_sha256'] == anchors['f_frame_stream_sha256'], 'Frozen frame stream mismatch')
    check(fresult['counts'] == anchors['f_counts'], 'Frozen count dictionary mismatch')
    with scientific_stream(output / 'recursive.jsonl.gz') as emit:
        graphs, result = recursive_graphs(baseline, read_frames(fpath), emit)
    with scientific_stream(output / 'pruning.jsonl.gz') as emit:
        stages, stage_counts = pruning_stages(graphs, emit)
    signatures = {}
    for arm in ARM_IDS:
        signatures[arm] = {}
        for name in STAGES:
            graph = stages[arm][name]
            signature = parent._graph_signature_sha256(graph)
            signatures[arm][name] = {'historical_sha256': signature, 'full_sha256': graph_digest(graph)}
            # Save the graph before testing archived anchors, so failed outputs remain reviewable.
            with scientific_stream(output / f'{arm}.{name}.json.gz') as emit:
                emit(asdict(graph))
            if arm == 'H':
                check(signature == anchors['r_h_graph_signatures'][name], f'H {name} historical graph mismatch')
            if arm == 'S1' and name == 'P3':
                check(signature == anchors['r_s1_p3_sha256'], 'S1 P3 historical V26A graph mismatch')
    result.update(f_counts=fresult['counts'], stage_counts=stage_counts, graph_signatures=signatures)
    # Relative names are pass-independent, so inventories can be compared exactly.
    result['scientific_artifacts'] = [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
                                      for p in sorted(output.iterdir()) if p.is_file()]
    write_json_new(output / 'summary.json', result)
    return result


def validate_archives(v25, v26, samples):
    for archive, prefix, count in ((v25, 'run/samples/', 27), (v26, 'samples/', 19)):
        names = archive.namelist()
        actual = {n for n in names if n.startswith(prefix) and n.endswith('.json.gz')}
        check(len(names) == count and len(names) == len(set(names)) and
              actual == {f'{prefix}{sid}.json.gz' for sid in samples}, 'Archive entry/cohort mismatch')


def execute(manifest_path, approved_sha256, output, root=ROOT):
    output.mkdir(parents=True, exist_ok=False)
    completed, telemetry = [], []
    active_context = {'stage': 'preflight'}
    try:
        check(bool(approved_sha256) and sha256_file(manifest_path) == approved_sha256,
              'Explicit approved freeze SHA-256 mismatch')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        contract = validate_freeze(manifest, root)
        write_json_new(output / 'freeze_used.json', manifest)
        samples = contract['cohort']['sample_ids']
        with zipfile.ZipFile(root / contract['inputs']['v25_archive']['path']) as v25, \
                zipfile.ZipFile(root / contract['inputs']['v26a_archive']['path']) as v26:
            validate_archives(v25, v26, samples)
            for index, sid in enumerate(samples, 1):
                active_context = {'sample_id': sid, 'stage': 'baseline_reconstruction'}
                print(f'[{index}/16] {sid}: V27B recursive-history replay', flush=True)
                record = parent._read_record(v25, sid)
                old = json.loads(gzip.decompress(v26.read(f'samples/{sid}.json.gz')))
                check(record['sample_id'] == sid == old['sample_id'], 'Sample identity mismatch')
                baseline = parent._reconstruct_frozen_relink(record)
                anchors = contract['anchors']['samples'][sid]
                for stage, key in (('RAW', 'relink_sha256'), ('P2', 'v24_2_sha256'), ('P3', 'v24_3_sha256')):
                    check(record['graph_signatures'][key] == anchors['r_h_graph_signatures'][stage], 'V25 anchor mismatch')
                check(old['graph_signatures']['ablation_v24_3_sha256'] == anchors['r_s1_p3_sha256'] and
                      old['graph_signatures']['baseline_v24_3_sha256'] == anchors['r_h_graph_signatures']['P3'],
                      'V26A archive anchor mismatch')
                passes = []
                for number in (1, 2):
                    active_context = {'sample_id': sid, 'pass': number, 'stage': 'scientific_pass'}
                    started = time.perf_counter()
                    tracemalloc.start()
                    try:
                        passes.append(run_sample_pass(record, baseline, anchors, output / f'{sid}.pass{number}'))
                    finally:
                        _, peak = tracemalloc.get_traced_memory()
                        tracemalloc.stop()
                        telemetry.append({**active_context, 'seconds': time.perf_counter() - started,
                                          'peak_python_tracemalloc_bytes': peak})
                check(passes[0] == passes[1], f'Nondeterministic replay: {sid}')
                sample = {'sample_id': sid, **passes[0], 'deterministic_replay': True}
                write_json_new(output / f'{sid}.summary.json', sample)
                completed.append(sample)
        counts, fcounts, pruning = Counter(), Counter(), Counter()
        for sample in completed:
            counts.update(sample['counts']); fcounts.update(sample['f_counts']); pruning.update(sample['stage_counts'])
        check(dict(fcounts) == contract['anchors']['f_aggregate_counts'], 'Frozen aggregate count mismatch')
        check(counts['sources'] == 99167 and counts['frames'] == 1584 and len(completed) == 16,
              'Incomplete recursive source/frame/sample census')
        active_context = {'stage': 'postflight'}
        validate_freeze(manifest, root)
        result = {'status': 'VALID_RECURSIVE_MECHANISM_RESULT', 'scope': SCOPE,
                  'sample_count': len(completed), 'graph_stages_per_pass': 240,
                  'counts': dict(sorted(counts.items())), 'f_counts': dict(sorted(fcounts.items())),
                  'stage_counts': dict(sorted(pruning.items())), 'samples': completed,
                  'approved_freeze_sha256': approved_sha256, 'production_tuning_authorized': False,
                  'submission_authorized': False, 'new_official_matching_or_scoring': False,
                  'v26a_decision_preserved': 'NO_GO'}
        write_json_new(output / 'telemetry.json', {'passes': telemetry})
        write_json_new(output / 'summary.json', result)
        write_inventory(output)
        return result
    except Exception as exc:
        write_json_new(output / 'invalid_execution.json', {'status': 'INVALID_EXECUTION',
                       'scope': SCOPE, 'error_type': type(exc).__name__, 'error': str(exc),
                       'active_context': active_context, 'completed_sample_ids': [s['sample_id'] for s in completed],
                       'telemetry': telemetry, 'production_tuning_authorized': False,
                       'submission_authorized': False, 'v26a_decision_preserved': 'NO_GO'})
        write_inventory(output)
        raise


def write_inventory(output):
    write_json_new(output / 'artifact_inventory.json', {
        'self_excluded': 'artifact_inventory.json',
        'files': [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
                  for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'artifact_inventory.json']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare-freeze')
    prepare.add_argument('--test-report', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('run')
    run.add_argument('--freeze', type=Path, required=True)
    run.add_argument('--approved-freeze-sha256', required=True)
    run.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare-freeze':
        if args.output.exists():
            raise FileExistsError('Preserve existing freeze candidate')
        candidate = prepare_candidate(ROOT, args.test_report)
        write_json_new(args.output, candidate)
        print(f'READY_FOR_HUMAN_REVIEW payload={candidate["payload_sha256"]}')
    else:
        execute(args.freeze, args.approved_freeze_sha256, args.output_dir)


if __name__ == '__main__':
    main()
