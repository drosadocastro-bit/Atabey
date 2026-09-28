"""Fresh paired official evaluation of completed V29A research output."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from importlib import metadata
import json
import platform
from pathlib import Path
import sys
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from atabey.submission.v29a import digest, metric_parity, quality_decision, require, sha, tree_identity, validate_receipt
from atabey.submission.v28 import build_graph, export_graph, signature
from run_v28_submission import save


def host_identity(expected):
    found = {}
    for name, reference in expected.items():
        dist = metadata.distribution(name)
        direct = json.loads(dist.read_text('direct_url.json'))
        base = Path(dist.locate_file(reference['module']))
        files = [{'path': p.relative_to(base).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                 for p in sorted(base.rglob('*.py'))]
        identity = {'module': reference['module'], 'version': dist.version,
                    'commit': direct['vcs_info']['commit_id'], 'direct_url': direct,
                    'source_files': files, 'source_tree_sha256': digest(files)}
        require(identity == reference, f'Official evaluator changed: {name}')
        found[name] = identity
    return found


def local_runtime_identity(names):
    return {'python': platform.python_version(), 'system': platform.system(), 'machine': platform.machine(),
            'packages': {name: metadata.version(name) for name in names}}


def verify_inference(output, summary, contract, manifest_sha, receipt):
    require(summary['status'] == 'INFERENCE_COMPLETE', 'Completed timing-approved inference required')
    require(summary['package_manifest_sha256'] == manifest_sha and summary['receipt'] == receipt, 'Run lineage mismatch')
    require(summary['candidate_ids'] == sorted(contract['samples']), 'Incomplete candidate cohort')
    require(summary['baseline_ids'] == sorted(contract['samples']), 'Incomplete baseline cohort')
    require(summary['timing_projection']['passes'] and summary['full_cohort_projection']['passes'], 'Runtime gate failed')
    from run_v28_submission import runtime_projection
    from atabey.submission.v28 import validate_csv
    records = []
    for item in summary['files']:
        path = (output / item['path']).resolve()
        require(path.is_relative_to(output.resolve()), 'Output path escapes run')
        require(path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'Output identity mismatch')
    for sid in sorted(contract['samples']):
        record = json.loads((output / 'records' / (sid + '.json')).read_text())
        require(record['sample_id'] == sid and record['shape'] == contract['samples'][sid]['image_metadata']['shape'], 'Record/cohort mismatch')
        require(record['route']['apply_pruning'] == contract['samples'][sid]['pruning_eligible'], 'Route mismatch')
        records.append(record)
        baseline_record = json.loads((output / 'baseline/records' / (sid + '.json')).read_text())
        require(baseline_record['sample_id'] == sid and baseline_record['graph_signature_sha256'] == contract['samples'][sid]['baseline_graph_sha256'], 'Baseline record mismatch')
    for sid in contract['repeat_ids']:
        repeat = json.loads((output / 'repeats' / (sid + '.json')).read_text())
        require(repeat['graph_signature_sha256'] == next(r['graph_signature_sha256'] for r in records if r['sample_id'] == sid), 'Repeat mismatch')
    for sid in contract['timing_ids']:
        control = json.loads((output / 'controls' / (sid + '.json')).read_text())
        require(control['graph_signature_sha256'] == contract['samples'][sid]['baseline_graph_sha256'], 'Control mismatch')
    visible = summary['visible']
    require([r['sample_id'] for r in visible['samples']] == contract['visible_ids'], 'Visible scope mismatch')
    csv = output / 'visible/v29a_preview.csv'
    require(sha(csv) == visible['csv_sha256'] and validate_csv(csv, visible['samples']) == visible['csv_validation'], 'Preview CSV invalid')
    route_records = [r['image_metadata'] for r in contract['samples'].values()]
    for field, subset in [('timing_projection', [r for r in records if r['sample_id'] in contract['timing_ids']]),
                          ('full_cohort_projection', records)]:
        actual = runtime_projection({'inference_records': subset, 'route_records': route_records}, visible, summary['initialization_seconds'])
        require(actual == summary[field], 'Runtime projection mismatch')
    return records


def main():
    p = argparse.ArgumentParser()
    for name in ('package-dir', 'inference-dir', 'output-dir', 'receipt'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    rows = []
    try:
        manifest_path = a.package_dir / 'package_manifest.json'
        manifest_sha = sha(manifest_path)
        manifest = json.loads(manifest_path.read_text())
        receipt = json.loads(a.receipt.read_text())
        validate_receipt(receipt, manifest_sha)
        with zipfile.ZipFile(a.package_dir / 'v29a_source_bundle.zip') as bundle:
            require(bundle.read('package_manifest.json') == manifest_path.read_bytes(), 'Bundle/manifest mismatch')
            for name, expected in manifest['files'].items():
                data = bundle.read(name)
                import hashlib
                require(hashlib.sha256(data).hexdigest() == expected, 'Bundle member mismatch')
                if name.startswith(('src/', 'scripts/')):
                    require((ROOT / name).read_bytes().replace(b'\r\n', b'\n') == data, 'Local scientific source changed')
            contract = json.loads(bundle.read('v29a_contract.json'))
        summary = json.loads((a.inference_dir / 'summary.json').read_text())
        require(summary['contract_sha256'] == manifest['files']['v29a_contract.json'], 'Contract lineage mismatch')
        records = verify_inference(a.inference_dir, summary, contract, manifest_sha, receipt)
        require(local_runtime_identity(contract['local_runtime']['packages']) == contract['local_runtime'], 'Local evaluation runtime changed')
        official_runtime = host_identity(contract['host_evaluator'])
        save(a.output_dir / 'provenance.json', {'package_manifest_sha256': manifest_sha,
             'inference_summary_sha256': sha(a.inference_dir / 'summary.json'), 'receipt': receipt,
             'host_evaluator': official_runtime})
        archive_path = ROOT / contract['historical_archive']['path']
        require(sha(archive_path) == contract['historical_archive']['sha256'], 'Historical archive changed')
        for sid, info in contract['samples'].items():
            require(tree_identity(ROOT / 'train' / (sid + '.geff')) == info['gt_tree'], 'Ground truth changed')
        import numpy as np
        from atabey.io.geff_reader import read_geff_graph
        from atabey.evaluation.official_tracking_metric import evaluate_official_tracking, summarize_official_tracking, OfficialTrackingResult
        with zipfile.ZipFile(archive_path) as archive:
            for record in records:
                require(time.perf_counter() - start < contract['budgets']['local_scoring_seconds'], 'Scoring budget exhausted')
                sid = record['sample_id']
                info = contract['samples'][sid]
                source = json.loads(archive.read('samples/' + sid + '.json'))
                baseline_record = json.loads((a.inference_dir / 'baseline/records' / (sid + '.json')).read_text())
                baseline_path = (a.inference_dir / 'baseline' / baseline_record['coordinates']['path']).resolve()
                require(baseline_path.is_relative_to((a.inference_dir / 'baseline').resolve()), 'Baseline path escapes run')
                require(sha(baseline_path) == baseline_record['coordinates']['sha256'], 'Baseline coordinates changed')
                baseline, _ = build_graph(sid, np.load(baseline_path, allow_pickle=False), info['pruning_eligible'])
                require(signature(baseline) == info['baseline_graph_sha256'], 'Baseline replay mismatch')
                coordinate_path = (a.inference_dir / record['coordinates']['path']).resolve()
                require(coordinate_path.is_relative_to(a.inference_dir.resolve()), 'Coordinate path escapes run')
                require(sha(coordinate_path) == record['coordinates']['sha256'], 'Coordinates changed')
                coords = np.load(coordinate_path, allow_pickle=False)
                candidate, _ = build_graph(sid, coords, info['pruning_eligible'])
                require(signature(candidate) == record['graph_signature_sha256'], 'TTA graph reconstruction mismatch')
                _, exported = export_graph(candidate, record['shape'], 0)
                require(all(exported[k] == record[k] for k in exported), 'Export reconstruction mismatch')
                gt_path = ROOT / 'train' / (sid + '.geff')
                require(tree_identity(gt_path) == info['gt_tree'], 'GT changed before evaluation')
                gt = read_geff_graph(gt_path)
                baseline_metrics = asdict(evaluate_official_tracking(baseline, gt))
                row = {'sample_id': sid, 'baseline': baseline_metrics}
                save(a.output_dir / (sid + '.json'), row)
                metric_parity(baseline_metrics, source['arms'][contract['baseline_arm']]['metrics'], contract['metric_absolute_tolerance'])
                row['tta'] = asdict(evaluate_official_tracking(candidate, gt))
                if sid == contract['repeat_ids'][0]:
                    repeated = asdict(evaluate_official_tracking(candidate, gt))
                    save(a.output_dir / 'official_repeat.json', repeated)
                    metric_parity(repeated, row['tta'], contract['metric_absolute_tolerance'])
                require(tree_identity(gt_path) == info['gt_tree'], 'GT changed during evaluation')
                save(a.output_dir / (sid + '.json'), row)
                rows.append(row)
                print(json.dumps({'scored': len(rows), 'sample': sid}), flush=True)
        def aggregate(subset):
            return {arm: asdict(summarize_official_tracking([OfficialTrackingResult(**r[arm]) for r in subset]))
                    for arm in ('baseline', 'tta')}
        summaries = aggregate(rows)
        strata = {key: aggregate([r for r in rows if r['sample_id'] in ids]) for key, ids in contract['strata'].items()}
        decision = quality_decision(rows, summaries, strata, contract['quality_gates'], contract['catastrophic_ids'])
        host_identity(contract['host_evaluator'])
        require(local_runtime_identity(contract['local_runtime']['packages']) == contract['local_runtime'], 'Local evaluation runtime changed during run')
        result = {'decision': decision, 'summaries': summaries, 'strata': strata, 'rows': rows,
                  'package_manifest_sha256': manifest_sha, 'inference_summary_sha256': sha(a.inference_dir / 'summary.json'),
                  'wall_seconds': time.perf_counter() - start, 'submission_authorized': False}
        save(a.output_dir / 'result.json', result)
        print(json.dumps(decision), flush=True)
    except BaseException as exc:
        save(a.output_dir / 'FAILURE.json', {'status': 'INVALID_EXECUTION', 'message': str(exc),
             'traceback': traceback.format_exc(), 'completed_samples': len(rows), 'wall_seconds': time.perf_counter() - start})
        raise


if __name__ == '__main__':
    main()
