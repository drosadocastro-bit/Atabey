"""Prepare a V27C candidate or evaluate saved graphs under exact human approval."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
import time
import tracemalloc
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from atabey.evaluation.frozen_graph_audit import (
    check, compare_records, decode_graph, digest, evaluate_graph, EvaluationFailure,
    interaction, metric_delta, summarize_records, verify_historical,
)
from atabey.io.geff_reader import read_geff_graph
from atabey.provenance import canonical_text_sha256, sha256_file

CONTRACT = 'tests/fixtures/v27c_official_graph_evaluation.json'
CONTRACT_SHA256 = 'b4b5a85f1b2186a0cb991a9912dd0f5c24ee8eb08ca0f9c6e50bc3deae71bcf9'
SCOPE = 'V27C_OFFICIAL_FROZEN_GRAPH_RETROSPECTIVE_EVALUATION'


def safe_path(root, relative):
    path = (root / relative).resolve()
    check(not Path(relative).is_absolute() and path.is_relative_to(root.resolve()), 'Path escapes repository')
    return path


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def write_compressed(path, value):
    with path.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as stream:
            stream.write(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def read_graph(path, item):
    expected = item['evaluation_input']
    check(path.stat().st_size == expected['bytes'] and sha256_file(path) == expected['sha256'],
          'Graph container changed before decoding')
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return decode_graph(json.load(stream), item['sample_id'], item['full_graph_sha256'])


def runtime_identity():
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'platform': platform.platform(),
            'packages': sorted({(d.metadata['Name'], d.version) for d in metadata.distributions()})}


def science_contract(root):
    check(sha256_file(root / CONTRACT) == CONTRACT_SHA256, 'V27C contract identity mismatch')
    c = read_json(root / CONTRACT)
    check(canonical_text_sha256(safe_path(root, c['protocol']['path'])) == c['protocol']['canonical_sha256'],
          'V27C protocol identity mismatch')
    return c


def required_sources(root, c):
    # Parent closure is explicit; do not rerun older dynamic source discovery.
    return (set(c['parent_source_canonical_sha256']) | set(c['reference_evaluation_source_canonical_sha256']) |
            {p.relative_to(root).as_posix() for p in (root / 'src/atabey').rglob('*.py')} |
            {CONTRACT, c['protocol']['path'], 'scripts/run_v27c_official_graph_evaluation.py',
             'tests/test_v27c_frozen_graph_audit.py', 'tests/test_v27c_runner.py'})


def host_identity(c):
    actual = {}
    for name, expected in c['host_evaluator'].items():
        dist = metadata.distribution(name)
        direct = json.loads(dist.read_text('direct_url.json'))
        base = Path(dist.locate_file(expected['module']))
        files = [{'path': p.relative_to(base).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
                 for p in sorted(base.rglob('*.py'))]
        value = {'module': expected['module'], 'version': dist.version, 'commit': direct['vcs_info']['commit_id'],
                 'direct_url': direct, 'source_files': files, 'source_tree_sha256': digest(files)}
        check(value == expected, f'Host source/version mismatch: {name}')
        actual[name] = value
    return actual


def verify_evidence(c, root):
    identities = {}

    def verify(item):
        path = safe_path(root, item['path'])
        value = {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        check(value == {k: item[k] for k in value}, f'Input identity mismatch: {item["path"]}')
        identities[item['path']] = value

    for item in [*c['inputs'].values(), *c['parent_pass_summaries']]:
        verify(item)
    parent = read_json(root / c['inputs']['v27b_contract']['path'])
    result = read_json(root / c['inputs']['v27b_result']['path'])
    check(c['inputs']['v27b_inventory']['sha256'] == result['artifact_inventory']['sha256'], 'Parent inventory chain')
    check(c['inputs']['v27b_freeze_copy']['sha256'] == c['inputs']['v27b_approved_manifest']['sha256'], 'Parent freeze copy')
    check(c['cohort'] == parent['cohort'], 'Parent cohort mismatch')
    inventory = {r['path']: r for r in read_json(root / c['inputs']['v27b_inventory']['path'])['files']}
    base = Path(c['inputs']['v27b_inventory']['path']).parent
    expected_matrix = [(s, a, t) for s in c['cohort']['sample_ids'] for a in c['arms'] for t in c['stages']]
    check([(g['sample_id'], g['arm'], g['stage']) for g in c['graph_inputs']] == expected_matrix, 'Incomplete input matrix')
    for item in c['parent_pass_summaries']:
        old = inventory[Path(item['path']).relative_to(base).as_posix()]
        check(all(old[k] == item[k] for k in ('bytes','sha256')), 'Parent summary inventory mismatch')
    for item in c['graph_inputs']:
        for copy in ('evaluation_input', 'parent_replay_copy'):
            file = item[copy]
            verify(file)
            old = inventory[Path(file['path']).relative_to(base).as_posix()]
            check(all(old[k] == file[k] for k in ('bytes', 'sha256')), 'Parent graph inventory mismatch')
            read_graph(root / file['path'], item)
            summary = read_json((root / file['path']).parent / 'summary.json')
            check(summary['graph_signatures'][item['arm']][item['stage']] ==
                  {'full_sha256': item['full_graph_sha256'], 'historical_sha256': item['historical_graph_sha256']},
                  'Parent graph signature mismatch')
        check(item['evaluation_input']['sha256'] == item['parent_replay_copy']['sha256'], 'Parent graph replay mismatch')
        anchors = parent['anchors']['samples'][item['sample_id']]
        if item['arm'] == 'H':
            check(item['historical_graph_sha256'] == anchors['r_h_graph_signatures'][item['stage']], 'H graph anchor mismatch')
        if item['arm'] == 'S1' and item['stage'] == 'P3':
            check(item['historical_graph_sha256'] == anchors['r_s1_p3_sha256'], 'S1 graph anchor mismatch')
    for gt in c['ground_truth']:
        base = safe_path(root, gt['path'])
        paths = sorted(p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file())
        check(paths == [r['path'] for r in gt['files']] and digest(gt['files']) == gt['tree_sha256'], 'GT tree mismatch')
        for item in gt['files']:
            verify(dict(item, path=gt['path'] + '/' + item['path']))
        geff = read_json(base / 'zarr.json')['attributes']['geff']
        check(geff['axes'] == gt['axes'] and [a['scale'] for a in geff['axes']] == [1,1.625,.40625,.40625],
              'GT axes mismatch')
        check(geff['extra']['estimated_number_of_nodes'] == gt['estimated_number_of_nodes'] > 0, 'GT estimate mismatch')
    for table in ('parent_source_canonical_sha256', 'reference_evaluation_source_canonical_sha256'):
        for path, expected in c[table].items():
            check(canonical_text_sha256(safe_path(root, path)) == expected, f'Parent/reference source mismatch: {path}')
    with zipfile.ZipFile(root / c['inputs']['v26a_archive']['path']) as archive:
        for anchor in c['historical_metric_anchors']['per_sample']:
            raw = archive.read(anchor['member'])
            import hashlib
            check(hashlib.sha256(raw).hexdigest() == anchor['member_sha256'], 'Historical member mismatch')
            old = json.loads(gzip.decompress(raw))
            check(old['sample_id'] == anchor['sample_id'] and old['baseline_metric'] == anchor['H_P3_metric']
                  and old['ablation_metric'] == anchor['S1_P3_metric'], 'Historical anchor payload mismatch')
        summary = json.loads(archive.read('summary.json'))
        check(summary['baseline_official_summary'] == c['historical_metric_anchors']['H_P3_summary'] and
              summary['ablation_official_summary'] == c['historical_metric_anchors']['S1_P3_summary'], 'Historical summary mismatch')
    return identities


def test_report_identity(path):
    tree = ET.parse(path).getroot()
    cases = list(tree.iter('testcase'))
    counts = {k: len(list(tree.iter(k))) for k in ('failure', 'error', 'skipped')}
    check(cases and not any(counts.values()), 'Passing tests with zero skips required')
    return {'sha256': sha256_file(path), 'tests': len(cases), **counts}


def prepare_candidate(root, report):
    c = science_contract(root)
    runtime = runtime_identity()
    check(digest(runtime) == digest(c['observed_runtime_reference']), 'Proposal runtime mismatch')
    payload = {'scope': SCOPE, 'builder': 'Codex', 'contract_path': CONTRACT,
               'canonical_sources': {p: canonical_text_sha256(safe_path(root, p)) for p in sorted(required_sources(root, c))},
               'inputs': verify_evidence(c, root), 'host_evaluator': host_identity(c), 'runtime': runtime,
               'test_report': {'path': report.resolve().relative_to(root.resolve()).as_posix(), **test_report_identity(report)}}
    return {'status': 'READY_FOR_HUMAN_REVIEW', 'payload': payload, 'payload_sha256': digest(payload),
            'review': None, 'human_execution_authorization': None}


def validate_freeze(manifest, root):
    check(manifest.get('status') == 'FROZEN', 'V27C freeze is not FROZEN')
    payload = manifest['payload']
    pin = digest(payload)
    check(manifest.get('payload_sha256') == pin and payload['scope'] == SCOPE and payload['contract_path'] == CONTRACT,
          'Freeze integrity/scope mismatch')
    review, authority = manifest.get('review'), manifest.get('human_execution_authorization')
    check(isinstance(review, dict) and isinstance(authority, dict), 'Missing human review/authorization')
    check(bool(review.get('reviewer')) and review['reviewer'] != payload['builder'] and bool(review.get('record'))
          and review.get('reviewed_payload_sha256') == pin, 'Distinct reviewer and exact payload required')
    check(bool(authority.get('authority')) and bool(authority.get('record')) and
          authority.get('scope') == SCOPE and authority.get('approved_payload_sha256') == pin,
          'Human authorization must cover exact V27C scope/payload')
    c = science_contract(root)
    check(set(payload['canonical_sources']) == required_sources(root, c), 'Freeze source closure mismatch')
    for path, expected in payload['canonical_sources'].items():
        check(canonical_text_sha256(safe_path(root, path)) == expected, f'Frozen source mismatch: {path}')
    check(digest(runtime_identity()) == digest(payload['runtime']) == digest(c['observed_runtime_reference']), 'Runtime mismatch')
    report = payload['test_report']
    check(test_report_identity(safe_path(root, report['path'])) == {k:v for k,v in report.items() if k != 'path'},
          'Test evidence mismatch')
    check(host_identity(c) == payload['host_evaluator'], 'Host identity mismatch')
    check(verify_evidence(c, root) == payload['inputs'], 'Input inventory mismatch')
    return c


def write_inventory(output):
    files = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
             for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'artifact_inventory.json']
    write_new(output / 'artifact_inventory.json', {'self_excluded': 'artifact_inventory.json', 'files': files})


def compact(record):
    return {k:v for k,v in record.items() if k not in ('edge_union','gained_gt_edges','lost_gt_edges','shared_gt_edges',
                                                    'shared_node_mapping_changes','deleted_node_ids','added_node_ids')}


def sample_comparisons(records, c, directory):
    comparisons = {}
    for stage in c['stages']:
        for contrast in c['paired_contrasts']:
            key = f'{contrast["id"]}.{stage}'
            ledger = compare_records(records[(contrast['before'],stage)], records[(contrast['after'],stage)])
            write_compressed(directory / f'{key}.ledger.json.gz', ledger)
            comparisons[key] = {'sha256': digest(ledger), **compact(ledger)}
    for arm in c['arms']:
        for before, after in c['pruning_contrasts']:
            key = f'{arm}.{before}_to_{after}'
            ledger = compare_records(records[(arm,before)], records[(arm,after)], pruning=True)
            write_compressed(directory / f'{key}.ledger.json.gz', ledger)
            comparisons[key] = {'sha256': digest(ledger), **compact(ledger)}
    interactions = {stage: interaction({arm: records[(arm,stage)]['metrics'] for arm in c['arms']}) for stage in c['stages']}
    return {'comparisons': comparisons, 'interactions': interactions}


def aggregate_pass(c, samples):
    count = c['cohort']['sample_count']
    check([s['sample_id'] for s in samples] == c['cohort']['sample_ids'], 'Incomplete pass samples')
    summaries = {f'{arm}.{stage}': summarize_records(
        [{'sample_id': s['sample_id'], 'metrics': s['metrics'][f'{arm}.{stage}']} for s in samples], count)
                 for arm in c['arms'] for stage in c['stages']}
    totals = {key: {field: sum(s['metrics'][key][field] for s in samples)
                    for field in ('edge_tp','edge_fp','edge_fn','division_tp','division_fp','division_fn',
                                  'predicted_nodes','estimated_total_nodes')}
              for key in summaries}
    comparisons = {}
    for key in samples[0]['comparisons']:
        counts, transitions = Counter(), Counter()
        for sample in samples:
            counts.update(sample['comparisons'][key]['counts'])
            transitions.update(sample['comparisons'][key]['category_transitions'])
        deltas = [s['comparisons'][key]['metric_delta'] for s in samples]
        ranges = {k: {'min': min(v) if v else None, 'max': max(v) if v else None,
                      'defined_sample_count': len(v)} for k in deltas[0]
                  for v in [[d[k] for d in deltas if d[k] is not None]]}
        comparisons[key] = {'counts': dict(sorted(counts.items())), 'category_transitions': dict(sorted(transitions.items())),
                            'per_sample_delta_range': ranges}
    for stage in c['stages']:
        for contrast in c['paired_contrasts']:
            comparisons[f'{contrast["id"]}.{stage}']['host_summary_delta'] = metric_delta(
                summaries[f'{contrast["before"]}.{stage}']['metrics'], summaries[f'{contrast["after"]}.{stage}']['metrics'])
    for arm in c['arms']:
        for before, after in c['pruning_contrasts']:
            comparisons[f'{arm}.{before}_to_{after}']['host_summary_delta'] = metric_delta(
                summaries[f'{arm}.{before}']['metrics'], summaries[f'{arm}.{after}']['metrics'])
    for arm in ('H','S1'):
        verify_historical(summaries[f'{arm}.P3']['metrics'], c['historical_metric_anchors'][f'{arm}_P3_summary'])
    return {'host_summaries': summaries, 'metric_count_totals': totals, 'comparisons': comparisons,
            'interactions': {stage: interaction({arm: summaries[f'{arm}.{stage}']['metrics'] for arm in c['arms']})
                             for stage in c['stages']}, 'samples': samples}


def render_report(result):
    def number(value):
        return 'undefined' if value is None else f'{value:.8g}'
    rows = ['# V27C retrospective evaluation', '', f'Status: **{result["status"]}**.', '',
            'All 240 saved graphs were evaluated twice with exact scientific replay. Historical metric',
            'anchors, complete-cohort accounting and post-run frozen identities passed.', '',
            '## Official host summaries', '',
            '| Arm / stage | Edge TP | Edge FP | Edge FN | Edge J | Adjusted edge J | Division J | Score |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    science = result['result']
    for key, entry in science['host_summaries'].items():
        m, counts = entry['metrics'], science['metric_count_totals'][key]
        values = [counts['edge_tp'],counts['edge_fp'],counts['edge_fn'],m['edge_jaccard'],
                  m['adjusted_edge_jaccard'],m['division_jaccard'],m['score']]
        rows.append(f'| {key} | ' + ' | '.join(number(v) for v in values) + ' |')
    rows += ['', '## Paired and pruning differences', '',
             'Deltas below are differences of official host summaries. Per-sample extrema refer to',
             'adjusted edge Jaccard changes and do not replace individual sample records.', '',
             '| Comparison | Adjusted edge J delta | Min sample delta | Max sample delta | Gained GT credits | Lost GT credits | Newly FP | Relieved FP |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key, entry in science['comparisons'].items():
        counts, extrema = entry['counts'], entry['per_sample_delta_range']['adjusted_edge_jaccard']
        values = [entry['host_summary_delta']['adjusted_edge_jaccard'],extrema['min'],extrema['max'],
                  counts['gained_GT_credit'],counts['lost_GT_credit'],counts['newly_penalized_FP'],counts['relieved_FP']]
        rows.append(f'| {key} | ' + ' | '.join(number(v) for v in values) + ' |')
    rows += ['', '## Interpretation boundary', '',
             'FP means penalized by the pinned official evaluator; unmatched edges outside sparse-GT',
             'evaluability and host-filtered edges are separately recorded. Pruning comparisons include',
             'rematching changes on survivors. Credit changes do not imply that pruning created edges.',
             'These selected, already opened samples do not establish independent generalization.',
             'V26A remains NO_GO. No model selection, production promotion or submission is authorized.', '',
             'Full per-cell metrics, node mappings, edge categories, warnings, per-sample contrasts and',
             'interaction arithmetic are in summary.json and the pass directories. Undefined values',
             'retain their reasons and denominators in cell records. See artifact_inventory.json for',
             'byte identities; telemetry is excluded from scientific digests.', '']
    return '\n'.join(rows)


def execute(freeze, approved_sha256, output, root=ROOT):
    # Directory creation is exclusive, including for rejected attempts.
    output.mkdir(parents=True, exist_ok=False)
    completed, telemetry, passes = [], [], []
    context = {'phase': 'approval_validation'}
    try:
        check(bool(approved_sha256) and sha256_file(freeze) == approved_sha256, 'Explicit approved freeze SHA required')
        manifest = read_json(freeze)
        c = validate_freeze(manifest, root)
        (output / 'freeze_used.json').write_bytes(freeze.read_bytes())
        write_new(output / 'input_checks.json', {'inputs': manifest['payload']['inputs'], 'contract_sha256': CONTRACT_SHA256})
        graph_items = {(g['sample_id'],g['arm'],g['stage']): g for g in c['graph_inputs']}
        gt_items = {g['sample_id']:g for g in c['ground_truth']}
        anchors = {a['sample_id']:a for a in c['historical_metric_anchors']['per_sample']}
        first_hashes = {}
        for pass_id in (1,2):
            pass_dir = output / f'pass{pass_id}'
            pass_dir.mkdir()
            samples = []
            for sid in c['cohort']['sample_ids']:
                directory = pass_dir / sid
                directory.mkdir()
                context = {'pass': pass_id, 'sample_id': sid, 'phase': 'GT_loading'}
                gt = read_geff_graph(safe_path(root, gt_items[sid]['path']))
                check(gt.estimated_number_of_nodes == gt_items[sid]['estimated_number_of_nodes'], 'Decoded GT estimate mismatch')
                records, cell_hashes = {}, {}
                for arm in c['arms']:
                    for stage in c['stages']:
                        context = {'pass': pass_id, 'sample_id': sid, 'arm': arm, 'stage': stage, 'phase': 'evaluation'}
                        print(f'V27C pass={pass_id} sample={sid} arm={arm} stage={stage}', flush=True)
                        item = graph_items[(sid,arm,stage)]
                        graph = read_graph(safe_path(root, item['evaluation_input']['path']), item)
                        started = time.perf_counter()
                        tracemalloc.start()
                        try:
                            record = evaluate_graph(graph, gt)
                        finally:
                            _, peak = tracemalloc.get_traced_memory()
                            tracemalloc.stop()
                            telemetry.append({**context, 'seconds': time.perf_counter()-started, 'peak_python_traced_bytes': peak})
                        write_compressed(directory / f'{arm}.{stage}.json.gz', record)
                        records[(arm,stage)] = record
                        cell_hashes[f'{arm}.{stage}'] = digest(record)
                        if stage == 'P3' and arm in ('H','S1'):
                            context['phase'] = 'historical_metric_anchor'
                            verify_historical(record['metrics'], anchors[sid][f'{arm}_P3_metric'])
                        key = (sid,arm,stage)
                        if pass_id == 1:
                            first_hashes[key] = digest(record)
                        else:
                            check(first_hashes[key] == digest(record), 'Cell replay mismatch')
                        completed.append({'pass': pass_id, 'sample_id': sid, 'arm': arm, 'stage': stage})
                context = {'pass': pass_id, 'sample_id': sid, 'phase': 'paired_ledgers'}
                sample = {'sample_id': sid, 'cell_digests': cell_hashes,
                          'metrics': {f'{a}.{t}': r['metrics'] for (a,t),r in records.items()},
                          **sample_comparisons(records, c, directory)}
                write_new(directory / 'summary.json', sample)
                samples.append(sample)
                del records, gt
            context = {'pass': pass_id, 'phase': 'aggregate_and_anchors'}
            summary = aggregate_pass(c, samples)
            write_new(pass_dir / 'summary.json', summary)
            passes.append(summary)
        check(len(completed) == c['evaluation']['expected_cell_evaluations'], 'Incomplete evaluation matrix')
        check(digest(passes[0]) == digest(passes[1]), 'Full scientific replay mismatch')
        context = {'phase': 'postflight'}
        validate_freeze(manifest, root)
        result = {'status': c['valid_result_status'], 'scope': SCOPE, 'sample_count': c['cohort']['sample_count'],
                  'distinct_graphs': len(graph_items), 'completed_evaluations': len(completed),
                  'approved_freeze_sha256': approved_sha256, 'scientific_sha256': digest(passes[0]),
                  'deterministic_replay': True, 'result': passes[0], 'v26a_decision_preserved': 'NO_GO',
                  'independent_validation': False, 'production_promotion': False, 'submission': False}
        write_new(output / 'telemetry.json', telemetry)
        write_new(output / 'summary.json', result)
        with (output / 'RESULTS.md').open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(render_report(result))
        write_inventory(output)
        return result
    except Exception as exc:
        failure = {'status': 'INVALID_EXECUTION', 'scope': SCOPE, 'active_context': context,
                   'error_type': type(exc).__name__, 'error': str(exc), 'completed_cells': completed, 'telemetry': telemetry}
        if isinstance(exc, EvaluationFailure):
            write_compressed(output / 'failing_cell.json.gz', exc.evidence)
            failure['cell_evidence'] = 'failing_cell.json.gz'
        write_new(output / 'invalid_execution.json', failure)
        write_inventory(output)
        raise


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
        check(not args.output.exists(), 'Preserve existing candidate')
        candidate = prepare_candidate(ROOT, args.test_report)
        write_new(args.output, candidate)
        print(f'READY_FOR_HUMAN_REVIEW payload={candidate["payload_sha256"]}')
    else:
        execute(args.freeze, args.approved_freeze_sha256, args.output_dir)


if __name__ == '__main__':
    main()
