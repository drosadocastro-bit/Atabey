from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from atabey.tracking.commitment_shadow import audit_motion_mutual_commitment
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections
from run_v22_unet_detection_shadow import _load_public_predict_module
from run_v24_score_first_tracking import (
    _config_payload,
    _predict_config,
    _predict_once,
    _sha256,
    _validate_checkpoint,
)


DEFAULT_SAMPLES = ("6bba_2646afc7", "6bba_3c5691b6")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _signature_sha256(graph) -> str:
    return hashlib.sha256(repr(graph_signature(graph)).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the bounded V24.5 motion-commitment shadow probe."
    )
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--support-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "tests/fixtures/v24_score_first_tracking.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/v24_5_commitment_shadow_local_2",
    )
    parser.add_argument("--sample-ids", nargs="+", default=list(DEFAULT_SAMPLES))
    parser.add_argument("--max-timepoints", type=int, default=12)
    parser.add_argument("--unet-batch-size", type=int, default=1)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--horizon-frames", type=int, default=2)
    parser.add_argument("--max-counterfactual-edges", type=int, default=64)
    args = parser.parse_args()

    import torch

    if args.max_timepoints < 3:
        raise ValueError("--max-timepoints must be at least 3")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    checkpoint = _validate_checkpoint(args.weights, contract)
    predictor_path = args.support_repo / "scripts/predict_unet_transformer.py"
    if not predictor_path.exists():
        raise FileNotFoundError(f"Public predictor is missing: {predictor_path}")

    sample_ids = list(dict.fromkeys(args.sample_ids))
    for sample_id in sample_ids:
        sample_path = args.train_dir / f"{sample_id}.zarr"
        if not sample_path.exists():
            raise FileNotFoundError(f"Sample is missing: {sample_path}")

    output_dir = args.output_dir
    coordinate_dir = output_dir / "coordinates"
    record_dir = output_dir / "samples"
    coordinate_dir.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)

    public_module = _load_public_predict_module(args.support_repo)
    device = torch.device(args.device)
    model, window_size, downsample = public_module.load_model(args.weights, device)
    predict_config = _predict_config(public_module, contract)
    records: list[dict[str, Any]] = []

    for index, sample_id in enumerate(sample_ids, start=1):
        print(f"[{index}/{len(sample_ids)}] {sample_id}", flush=True)
        coordinate_path = coordinate_dir / f"{sample_id}.npy"
        inference_runtime = 0.0
        if coordinate_path.exists():
            coordinates = np.load(coordinate_path, allow_pickle=False)
            coordinate_source = "cache"
        else:
            coordinates, _, inference_runtime = _predict_once(
                public_module,
                model,
                args.train_dir / f"{sample_id}.zarr",
                device,
                predict_config,
                window_size,
                downsample,
                args.max_timepoints,
                args.unet_batch_size,
            )
            coordinates = np.asarray(coordinates)
            np.save(coordinate_path, coordinates, allow_pickle=False)
            coordinate_source = "inference"

        graph = relink_predictor_detections(sample_id, coordinates)
        signature_before = _signature_sha256(graph)
        shadow_started = time.perf_counter()
        shadow = audit_motion_mutual_commitment(
            graph,
            horizon_frames=args.horizon_frames,
            max_counterfactual_edges=args.max_counterfactual_edges,
        )
        shadow_runtime = time.perf_counter() - shadow_started
        signature_after = _signature_sha256(graph)
        if signature_before != signature_after:
            raise RuntimeError("Commitment shadow mutated the relinked graph")

        record = {
            "sample_id": sample_id,
            "coordinate_source": coordinate_source,
            "coordinate_count": len(coordinates),
            "coordinate_sha256": _sha256(coordinate_path),
            "inference_runtime_seconds": inference_runtime,
            "shadow_runtime_seconds": shadow_runtime,
            "graph_signature_sha256": signature_before,
            "graph_mutated": False,
            "shadow": asdict(shadow),
        }
        _atomic_json(record_dir / f"{sample_id}.json", record)
        records.append(record)
        print(
            f"  coordinates={len(coordinates)} eligible={shadow.eligible_edge_count} "
            f"tested={shadow.counterfactual_edge_count} "
            f"sensitive={shadow.commitment_sensitive_edge_count}",
            flush=True,
        )

    summary = {
        "status": "v24_5_commitment_shadow_local_smoke",
        "sample_ids": sample_ids,
        "sample_count": len(records),
        "selection_basis": {
            "6bba_2646afc7": "largest full-199 association-loss regression",
            "6bba_3c5691b6": "only held-out full-199 regression; precision tradeoff",
        },
        "runtime_contract": {
            "device": args.device,
            "max_timepoints": args.max_timepoints,
            "unet_batch_size": args.unet_batch_size,
            "horizon_frames": args.horizon_frames,
            "max_counterfactual_edges": args.max_counterfactual_edges,
        },
        "provenance": {
            "checkpoint_sha256": checkpoint["weights_sha256"],
            "predictor_sha256": _sha256(predictor_path),
            "predict_config": _config_payload(predict_config),
        },
        "assignment_enabled": False,
        "selector_enabled": False,
        "production_graph_mutation": False,
        "interpretation": "Descriptive stability telemetry only; divergence is not evidence of an incorrect link.",
        "records": records,
    }
    _atomic_json(output_dir / "summary.json", summary)


if __name__ == "__main__":
    main()