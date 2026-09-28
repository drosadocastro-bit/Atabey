"""Bounded image-only V29A GPU experiment; never scores or submits."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from atabey.submission.v29a import candidate_config, require, sha, validate_receipt
from atabey.submission.v28 import build_graph, discover_samples, export_graph, inspect_sample, route_for_sample, signature
from run_v28_submission import load_predictor, runtime_info, runtime_projection, save, verify_package, write_test_submission


def infer(path, predict, expected, directory=None):
    import numpy as np
    meta = inspect_sample(path)
    require(meta == expected['image_metadata'], 'Image metadata differs from contract')
    route = route_for_sample(path)
    require(route['apply_pruning'] == expected['pruning_eligible'], 'Route differs from V28')
    coordinates, telemetry = predict(path)
    graph, stages = build_graph(path.stem, coordinates, route['apply_pruning'])
    started = time.perf_counter()
    _, exported = export_graph(graph, meta['shape'], 0)
    record = {**meta, 'route': route, **telemetry, **stages, **exported,
              'export_seconds': time.perf_counter() - started}
    if directory is not None:
        target = directory / 'coordinates' / (path.stem + '.npy')
        require(not target.exists(), 'Do not overwrite coordinate evidence')
        np.save(target, np.asarray(coordinates), allow_pickle=False)
        record['coordinates'] = {'path': target.relative_to(directory).as_posix(),
                                 'sha256': sha(target), 'bytes': target.stat().st_size}
        save(directory / 'records' / (path.stem + '.json'), record)
    return record


def main():
    p = argparse.ArgumentParser()
    for name in ('package-root', 'support-root', 'weights', 'data-root', 'output-dir', 'receipt'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--setup-seconds', type=float, default=0)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    result = {'status': 'STARTED', 'new_scoring': False, 'competition_submission_performed': False}
    try:
        manifest_sha = sha(a.package_root / 'package_manifest.json')
        receipt = json.loads(a.receipt.read_text())
        validate_receipt(receipt, manifest_sha)
        manifest = verify_package(a.package_root, a.support_root, a.weights)
        contract = json.loads((a.package_root / 'v29a_contract.json').read_text())
        require(sha(a.package_root / 'v29a_contract.json') == manifest['files']['v29a_contract.json'], 'Contract mismatch')
        require(0 <= a.setup_seconds < contract['budgets']['gpu_seconds'], 'Invalid setup timing')
        result.update(package_manifest_sha256=manifest_sha, contract_sha256=sha(a.package_root / 'v29a_contract.json'), receipt=receipt)
        paths = discover_samples(a.data_root / 'train')
        require([x.stem for x in paths] == sorted(contract['samples']), 'Exact 199-sample cohort required')
        require([x.stem for x in discover_samples(a.data_root / 'test')] == contract['visible_ids'], 'Visible sample scope changed')
        route_records = []
        for path in paths:
            meta = inspect_sample(path)
            require(meta == contract['samples'][path.stem]['image_metadata'], 'Cohort metadata changed')
            route_records.append(meta)
        baseline = load_predictor(a.support_root, a.weights, manifest['candidate'])
        tta = load_predictor(a.support_root, a.weights, candidate_config(manifest['candidate']))
        initialization = time.perf_counter() - started + a.setup_seconds
        for name in ('coordinates', 'records', 'controls', 'repeats', 'visible'):
            (a.output_dir / name).mkdir()
        for name in ('coordinates', 'records'):
            (a.output_dir / 'baseline' / name).mkdir(parents=True)
        controls, candidates, baseline_records = [], {}, {}
        for sid in contract['timing_ids']:
            path = a.data_root / 'train' / (sid + '.zarr')
            record = infer(path, baseline, contract['samples'][sid], a.output_dir / 'baseline')
            save(a.output_dir / 'controls' / (sid + '.json'), record)
            require(record['graph_signature_sha256'] == contract['samples'][sid]['baseline_graph_sha256'], 'Historical control mismatch')
            controls.append(record)
            baseline_records[sid] = record
            candidates[sid] = infer(path, tta, contract['samples'][sid], a.output_dir)
        for sid in contract['repeat_ids']:
            record = infer(a.data_root / 'train' / (sid + '.zarr'), tta, contract['samples'][sid])
            save(a.output_dir / 'repeats' / (sid + '.json'), record)
            require(record['graph_signature_sha256'] == candidates[sid]['graph_signature_sha256'], 'TTA repeat mismatch')
        visible = write_test_submission(a.data_root / 'test', a.output_dir / 'visible', tta)
        (a.output_dir / 'visible/submission.partial.csv').rename(a.output_dir / 'visible/v29a_preview.csv')
        result.update(controls=controls, repeats=contract['repeat_ids'], visible=visible, initialization_seconds=initialization,
                      runtime=runtime_info())
        import torch
        result['runtime']['gpu_device_count'] = torch.cuda.device_count()
        result['runtime']['cpu_description'] = Path('/proc/cpuinfo').read_text().split('model name', 1)[-1].splitlines()[0].strip(' :\t')
        def projection():
            return runtime_projection({'inference_records': list(candidates.values()), 'route_records': route_records}, visible, initialization)
        result['timing_projection'] = projection()
        save(a.output_dir / 'timing_gate.json', result['timing_projection'])
        if not result['timing_projection']['passes']:
            result['status'] = 'NO_GO_RUNTIME'
        else:
            for path in paths:
                require(time.perf_counter() - started + a.setup_seconds < contract['budgets']['gpu_seconds'], 'GPU budget exhausted')
                if path.stem not in baseline_records:
                    control = infer(path, baseline, contract['samples'][path.stem], a.output_dir / 'baseline')
                    require(control['graph_signature_sha256'] == contract['samples'][path.stem]['baseline_graph_sha256'], 'Full-cohort control mismatch')
                    baseline_records[path.stem] = control
                if path.stem not in candidates:
                    candidates[path.stem] = infer(path, tta, contract['samples'][path.stem], a.output_dir)
                print(json.dumps({'completed': len(candidates), 'sample': path.stem}), flush=True)
            result['full_cohort_projection'] = projection()
            result['status'] = 'INFERENCE_COMPLETE' if result['full_cohort_projection']['passes'] else 'NO_GO_RUNTIME'
        result['candidate_ids'] = sorted(candidates)
        result['baseline_ids'] = sorted(baseline_records)
        result['wall_seconds'] = time.perf_counter() - started + a.setup_seconds
        result['files'] = [{'path': p.relative_to(a.output_dir).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                           for p in sorted(a.output_dir.rglob('*')) if p.is_file()]
        save(a.output_dir / 'summary.json', result)
        print(json.dumps({'status': result['status'], 'wall_seconds': result['wall_seconds']}), flush=True)
    except BaseException as exc:
        save(a.output_dir / 'FAILURE.json', {'status': 'INVALID_EXECUTION', 'type': type(exc).__name__,
             'message': str(exc), 'traceback': traceback.format_exc(), 'wall_seconds': time.perf_counter() - started})
        raise


if __name__ == '__main__':
    main()
