"""Offline V24.3 delivery and bounded no-label validation entry point."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')


def validate_receipt(receipt, manifest_hash, mode):
    check(receipt.get('status') == 'APPROVED', 'Execution has not been approved')
    check(receipt.get('package_manifest_sha256') == manifest_hash, 'Approval refers to another package')
    check(receipt.get('scope') == 'V28_' + mode.upper(), 'Approval scope mismatch')
    check(receipt.get('authority') == 'Danny' and receipt.get('reviewer') == 'Danny', 'Human authority/reviewer required')
    check(receipt.get('builder') == 'Codex' and bool(receipt.get('record')), 'Approval record required')


def verify_files(base: Path, identities: dict):
    for relative, expected in identities.items():
        p = (base / relative).resolve()
        check(p.is_relative_to(base.resolve()), 'Manifest path escapes package')
        check(p.is_file() and sha_file(p) == expected, f'File identity mismatch: {relative}')


def verify_package(root, support, weights):
    manifest = json.loads((root / 'package_manifest.json').read_text())
    verify_files(root, manifest['files'])
    verify_files(support, manifest['support_files'])
    check(sha_file(weights) == manifest['candidate']['checkpoint_sha256'], 'Checkpoint mismatch')
    check(sha_file(weights.parent / 'config.json') == manifest['candidate']['runtime_config_sha256'], 'Config mismatch')
    return manifest


def load_predictor(support: Path, weights: Path, candidate: dict):
    import torch

    check(torch.cuda.is_available(), 'CUDA GPU is required for the reviewed V28 runtime')
    sys.path[:0] = [str(support / 'repo/scripts'), str(support / 'repo/src')]
    p = support / 'repo/scripts/predict_unet_transformer.py'
    spec = importlib.util.spec_from_file_location('biohub_public_predict_unet_transformer', p)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    config = module.PredictConfig(**candidate['predict_config'])
    check(asdict(config) == candidate['predict_config'], 'Predictor configuration drift')
    device = torch.device('cuda')
    model, window, downsample = module.load_model(weights, device)
    check(window == 2 and tuple(downsample) == (1,4,4), 'Unexpected model geometry')

    def predict(path):
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        coords, native_edges = module.predict_video(model, path, device, config, window_size=2, max_frames=None, unet_batch_size=4, downsample=(1,4,4))
        torch.cuda.synchronize()
        telemetry = {'inference_seconds': time.perf_counter()-start, 'native_edges_discarded': len(native_edges), 'peak_gpu_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_gpu_reserved_bytes': torch.cuda.max_memory_reserved()}
        return coords, telemetry

    return predict


def runtime_info():
    import torch
    import resource

    return {'python': sys.version, 'platform': platform.platform(), 'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda, 'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, 'packages': dict(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions() if d.metadata['Name']))}


def process_sample(path, predict):
    from atabey.submission.v28 import inspect_sample, route_for_sample, build_graph

    meta = inspect_sample(path)
    route = route_for_sample(path)
    coords, telemetry = predict(path)
    graph, stages = build_graph(path.stem, coords, route['apply_pruning'])
    return graph, {**meta, 'route': route, **telemetry, **stages}


def write_test_submission(test_dir, output, predict):
    from atabey.submission.v28 import discover_samples, export_graph, validate_csv
    from atabey.submission.writer import KAGGLE_SUBMISSION_COLUMNS

    samples = discover_samples(test_dir)
    check(not (output/'submission.csv').exists(), 'Refusing to replace an existing submission')
    partial = output / 'submission.partial.csv'
    start = time.perf_counter()
    records, offset = [], 0
    with partial.open('x', encoding='utf-8', newline='') as stream:
        stream.write(','.join(KAGGLE_SUBMISSION_COLUMNS)+'\n')
        for path in samples:
            sample_start = time.perf_counter()
            graph, record = process_sample(path, predict)
            export_start = time.perf_counter()
            text, exported = export_graph(graph, record['shape'], offset)
            stream.write(text)
            stream.flush()
            record.update(exported)
            record['export_seconds'] = time.perf_counter()-export_start
            record['total_sample_seconds'] = time.perf_counter()-sample_start
            offset += record['rows']
            records.append(record)
            save(output / f'{path.stem}.record.json', record)
            print(json.dumps({'sample':path.stem, 'rows':record['rows'], 'seconds':record['total_sample_seconds']}), flush=True)
            del graph, text
    validation_start = time.perf_counter()
    validated = validate_csv(partial, records)
    return {'samples': records, 'csv_validation': validated, 'csv_validation_seconds': time.perf_counter()-validation_start, 'test_wall_seconds': time.perf_counter()-start, 'csv_sha256': sha_file(partial)}


def validate_training_images(train_dir, references, output, predict):
    """Implementation parity only: no GEFF reads, labels or new metrics."""
    from atabey.submission.v28 import discover_samples, inspect_sample, route_for_sample, export_graph, signature

    paths = discover_samples(train_dir)
    check([p.stem for p in paths] == sorted(references['samples']), 'Parity cohort identity mismatch')
    route_rows = []
    for path in paths:
        meta = inspect_sample(path)
        route = route_for_sample(path)
        expected = references['samples'][path.stem]['pruning_eligible']
        row = {'sample_id': path.stem, 'shape': meta['shape'], **route, 'expected_pruning': expected, 'match': route['apply_pruning'] == expected}
        route_rows.append(row)
        # Preserve the first mismatch as evidence before stopping.
        save(output / 'route_parity.json', route_rows)
        check(row['match'], f'Route mismatch: {path.stem}')
    parity = []
    for sid in references['inference_ids']:
        graph, record = process_sample(train_dir / (sid+'.zarr'), predict)
        actual = signature(graph)
        expected = references['samples'][sid]['graph_signature_sha256']
        export_start = time.perf_counter()
        _, exported = export_graph(graph, record['shape'], 0)
        record['export_seconds'] = time.perf_counter()-export_start
        row = {**record, **exported, 'expected_graph_signature_sha256': expected, 'match': actual == expected}
        parity.append(row)
        save(output / 'inference_parity.json', parity)
        check(row['match'], f'Historical inference/graph parity failed: {sid}')
        del graph
    sid = references['inference_ids'][0]
    graph, _ = process_sample(train_dir / (sid+'.zarr'), predict)
    repeat = {'sample_id': sid, 'graph_signature_sha256': signature(graph), 'match': signature(graph) == parity[0]['graph_signature_sha256']}
    save(output / 'repeat_parity.json', repeat)
    check(repeat['match'], 'Repeated inference differs')
    return {'route_samples': len(route_rows), 'inference_samples': len(parity), 'repeat': repeat, 'inference_records': parity, 'route_records': route_rows}


def runtime_projection(parity, visible, initialization_seconds):
    # Explicit assumption: hidden workload <= the measured 199 training shapes.
    # Use worst measured normalized complete processing cost, plus 2x workload.
    records = parity['inference_records'] + visible['samples']
    per_voxel = []
    for r in records:
        voxel_frames = math_product(r['shape'])
        seconds = r['route']['seconds'] + r['inference_seconds'] + r['linking_seconds'] + r['pruning_seconds']
        seconds += r.get('export_seconds', max(x['export_seconds'] for x in visible['samples']))
        per_voxel.append(seconds / voxel_frames)
    workload = sum(math_product(r['shape']) for r in parity['route_records'])
    # Include observed setup, final CSV validation, and an additional 10 minutes
    # for filesystem/model startup variation. This is not a hidden-size bound.
    seconds = initialization_seconds + 600 + 2 * (max(per_voxel)*workload + visible['csv_validation_seconds']*199/max(1,len(visible['samples'])))
    return {'assumption': 'hidden_voxel_frames_at_most_observed_199_training_voxel_frames', 'assumed_voxel_frames':workload, 'measured_samples':len(records), 'measured_work_multiplier':2, 'startup_and_io_reserve_seconds':600, 'projected_seconds':seconds, 'gate_seconds':36000, 'passes':seconds<=36000, 'hidden_runtime_verified':False, 'limitations':['node_density_and_filesystem_cost_may_scale_non_linearly','hardware_is_specific_to_this_job','hidden_shapes_and_sample_count_are_unknown']}


def math_product(values):
    result = 1
    for v in values:
        result *= v
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--package-root', type=Path, default=ROOT)
    p.add_argument('--support-root', type=Path, required=True)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--mode', choices=['validation','submission'], required=True)
    p.add_argument('--setup-seconds', type=float, default=0.0)
    a = p.parse_args()
    # Exclusive ownership: preserve previous runs, including failed ones.
    a.output_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        manifest_hash = sha_file(a.package_root/'package_manifest.json')
        receipt = json.loads(a.receipt.read_text())
        validate_receipt(receipt, manifest_hash, a.mode)
        manifest = verify_package(a.package_root,a.support_root,a.weights)
        sys.path.insert(0,str(a.package_root/'src'))
        predict = load_predictor(a.support_root,a.weights,manifest['candidate'])
        check(0 <= a.setup_seconds < 43200, 'Invalid setup telemetry')
        initialization = time.perf_counter()-started+a.setup_seconds
        result = {'mode':a.mode, 'package_manifest_sha256':manifest_hash, 'receipt':receipt, 'initialization_seconds':initialization}
        if a.mode == 'validation':
            refs = json.loads((a.package_root/'validation_reference.json').read_text())
            result['parity'] = validate_training_images(a.data_root/'train',refs,a.output_dir,predict)
        result['visible_or_hidden_test'] = write_test_submission(a.data_root/'test',a.output_dir,predict)
        if a.mode == 'validation':
            result['runtime_projection'] = runtime_projection(result['parity'],result['visible_or_hidden_test'],initialization)
            save(a.output_dir/'runtime_projection.json',result['runtime_projection'])
            check(result['runtime_projection']['passes'],'Conservative runtime gate failed')
        result['runtime'] = runtime_info()
        result['wall_seconds'] = time.perf_counter()-started+a.setup_seconds
        result['disk_free_bytes'] = shutil.disk_usage(a.output_dir).free
        result['output_bytes_before_summary'] = sum(p.stat().st_size for p in a.output_dir.iterdir() if p.is_file())
        result['status'] = 'VALIDATION_COMPLETE' if a.mode == 'validation' else 'SUBMISSION_CSV_COMPLETE'
        result['kaggle_submission_performed'] = False
        save(a.output_dir/'summary.json',result)
        # A validation artifact has a different filename and cannot be mistaken
        # for an approved competition submission by automatic output selection.
        name = 'validation_submission.csv' if a.mode == 'validation' else 'submission.csv'
        (a.output_dir/'submission.partial.csv').replace(a.output_dir/name)
    except BaseException as exc:
        save(a.output_dir/'FAILURE.json',{'status':'FAILED','type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),'elapsed_seconds':time.perf_counter()-started})
        raise


if __name__ == '__main__':
    main()
