from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from run_v24_score_first_tracking import (
    ARMS,
    ARM_V19,
    ARM_V24_3,
    _atomic_json,
    _config_payload,
    _evaluate_sample,
    _folds,
    _predict_config,
    _sha256,
    _summaries,
    _validate_checkpoint,
    _write_csv,
)
from run_v22_unet_detection_shadow import _load_public_predict_module


SHARD_COMPLETE = "FULL_199_SCORE_VALIDATION_SHARD_COMPLETE"
INCOMPLETE = "FULL_199_SCORE_VALIDATION_INCOMPLETE"


def _normalized_text_sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def discover_paired_samples(train_dir: Path, expected_count: int) -> list[str]:
    zarr_ids = {path.name.removesuffix(".zarr") for path in train_dir.glob("*.zarr")}
    geff_ids = {path.name.removesuffix(".geff") for path in train_dir.glob("*.geff")}
    if zarr_ids != geff_ids:
        raise RuntimeError(
            "paired sample mismatch: "
            f"zarr_only={sorted(zarr_ids - geff_ids)} "
            f"geff_only={sorted(geff_ids - zarr_ids)}"
        )
    if len(zarr_ids) != expected_count:
        raise RuntimeError(
            f"expected exactly {expected_count} paired samples, found {len(zarr_ids)}"
        )
    return sorted(zarr_ids)


def validate_full_27_authorization(
    report_path: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    expected = contract["authorization"]
    actual_hash = _sha256(report_path)
    if actual_hash != expected["report_sha256"]:
        raise RuntimeError(
            f"authorization report SHA-256 mismatch: {actual_hash} != "
            f"{expected['report_sha256']}"
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    boundary_ok = (
        report.get("decision") == "GO_TO_FULL_199_SCORE_VALIDATION"
        and report.get("evaluation_commit") == expected["evaluation_commit"]
        and report.get("evaluated_arm") == expected["evaluated_arm"]
        and report.get("determinism_verified") is True
        and report.get("cohort", {}).get("complete") is True
        and report.get("cohort", {}).get("observed_samples") == 27
        and report.get("authorization", {}).get("full_199_score_validation") is True
        and report.get("authorization", {}).get("production_graph_mutation") is False
        and report.get("authorization", {}).get("submission") is False
    )
    if not boundary_ok:
        raise RuntimeError("full-27 authorization boundary check failed")
    return report


def validate_frozen_sources(contract: dict[str, Any]) -> None:
    for source in contract["sources"]:
        path = ROOT / source["path"]
        actual_hash = _normalized_text_sha256(path)
        if actual_hash != source["sha256"]:
            raise RuntimeError(
                f"frozen source mismatch for {source['path']}: "
                f"{actual_hash} != {source['sha256']}"
            )


def _comparison(records: list[dict[str, Any]], challenger: str) -> dict[str, Any]:
    deltas: list[float] = []
    node_ratios: list[float] = []
    for record in records:
        arms = record["arms"]
        deltas.append(
            arms[challenger]["metrics"]["adjusted_edge_jaccard"]
            - arms[ARM_V19]["metrics"]["adjusted_edge_jaccard"]
        )
        node_ratios.append(
            arms[challenger]["metrics"]["predicted_nodes"]
            / max(arms[ARM_V19]["metrics"]["predicted_nodes"], 1)
        )
    tolerance = 1e-6
    return {
        "sample_count": len(records),
        "improved": sum(delta > tolerance for delta in deltas),
        "flat": sum(abs(delta) <= tolerance for delta in deltas),
        "regressed": sum(delta < -tolerance for delta in deltas),
        "catastrophic_regressions": sum(delta < -0.10 for delta in deltas),
        "median_node_ratio": statistics.median(node_ratios),
        "p90_node_ratio": float(np.quantile(node_ratios, 0.9)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run frozen V24.3 full-199 score-validation shards."
    )
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--support-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "tests/fixtures/v24_3_full_199_score_validation.json",
    )
    parser.add_argument(
        "--authorization-report",
        type=Path,
        default=ROOT / "v24_3_short_fragment_shadow_full_27_report.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=2)
    parser.add_argument("--unet-batch-size", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify-determinism", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if args.shard_count != contract["population"]["shard_count"]:
        raise RuntimeError("shard count differs from the frozen full-199 contract")
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("shard index must be within the frozen shard count")

    validate_frozen_sources(contract)
    authorization = validate_full_27_authorization(args.authorization_report, contract)
    base_contract_path = ROOT / contract["frozen_v24_contract"]["path"]
    if _sha256(base_contract_path) != contract["frozen_v24_contract"]["sha256"]:
        raise RuntimeError("frozen V24 contract SHA-256 mismatch")
    base_contract = json.loads(base_contract_path.read_text(encoding="utf-8"))

    all_sample_ids = discover_paired_samples(
        args.train_dir, contract["population"]["expected_samples"]
    )
    held_out_ids = set(base_contract["cohort"]["sample_ids"])
    if not held_out_ids < set(all_sample_ids):
        raise RuntimeError("held-out 27 cohort is not a strict subset of the population")
    training_ids = set(all_sample_ids) - held_out_ids
    if len(training_ids) != contract["population"]["checkpoint_training_samples"]:
        raise RuntimeError("checkpoint-training population count mismatch")
    sample_ids = all_sample_ids[args.shard_index :: args.shard_count]

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("V24.3 full-199 validation requires a CUDA GPU")
    provenance = _validate_checkpoint(args.weights, base_contract)
    predictor_path = args.support_repo / "scripts/predict_unet_transformer.py"
    if not predictor_path.exists():
        raise FileNotFoundError(f"Public predictor is missing: {predictor_path}")
    provenance.update(
        {
            "predictor_path": str(predictor_path),
            "predictor_sha256": _sha256(predictor_path),
            "support_pack": base_contract["sources"]["support_pack"],
            "authorization_report_sha256": _sha256(args.authorization_report),
            "authorization_evaluation_commit": authorization["evaluation_commit"],
            "population_sample_ids_sha256": hashlib.sha256(
                "\n".join(all_sample_ids).encode("utf-8")
            ).hexdigest(),
            "shard_index": args.shard_index,
            "shard_count": args.shard_count,
        }
    )

    public_module = _load_public_predict_module(args.support_repo)
    device = torch.device("cuda")
    model, window_size, downsample = public_module.load_model(args.weights, device)
    predict_config = _predict_config(public_module, base_contract)
    if window_size != base_contract["checkpoint"]["window_size"]:
        raise RuntimeError("loaded window size differs from the frozen contract")
    if list(downsample) != base_contract["checkpoint"]["downsample"]:
        raise RuntimeError("loaded downsample differs from the frozen contract")
    provenance["predict_config"] = _config_payload(predict_config)
    provenance["runtime_contract"] = {
        "max_timepoints": None,
        "unet_batch_size": args.unet_batch_size,
    }

    sample_dir = args.output_dir / "samples"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = args.output_dir / "provenance.json"
    if provenance_path.exists():
        existing = json.loads(provenance_path.read_text(encoding="utf-8"))
        if existing != provenance:
            raise RuntimeError("output provenance differs; use a new shard directory")
    else:
        _atomic_json(provenance_path, provenance)

    folds = _folds(all_sample_ids, base_contract["evaluation"]["deterministic_fold_seed"])
    records: list[dict[str, Any]] = []
    for index, sample_id in enumerate(sample_ids, start=1):
        output_path = sample_dir / f"{sample_id}.json"
        if args.resume and output_path.exists():
            record = json.loads(output_path.read_text(encoding="utf-8"))
            print(f"[{index}/{len(sample_ids)}] {sample_id}: resumed", flush=True)
        else:
            print(f"[{index}/{len(sample_ids)}] {sample_id}: running", flush=True)
            record = _evaluate_sample(
                sample_id=sample_id,
                train_dir=args.train_dir,
                public_module=public_module,
                model=model,
                device=device,
                predict_config=predict_config,
                window_size=window_size,
                downsample=downsample,
                max_timepoints=None,
                unet_batch_size=args.unet_batch_size,
                fold=folds[sample_id],
            )
            record["checkpoint_usage"] = (
                "held_out_27" if sample_id in held_out_ids else "checkpoint_training_172"
            )
            _atomic_json(output_path, record)
        records.append(record)

    determinism_verified = False
    if args.verify_determinism:
        sample_id = sample_ids[0]
        repeated = _evaluate_sample(
            sample_id=sample_id,
            train_dir=args.train_dir,
            public_module=public_module,
            model=model,
            device=device,
            predict_config=predict_config,
            window_size=window_size,
            downsample=downsample,
            max_timepoints=None,
            unet_batch_size=args.unet_batch_size,
            fold=folds[sample_id],
        )
        determinism_verified = all(
            records[0]["arms"][arm]["graph_signature_sha256"]
            == repeated["arms"][arm]["graph_signature_sha256"]
            for arm in ARMS
        )
        _atomic_json(
            args.output_dir / "determinism.json",
            {"sample_id": sample_id, "verified": determinism_verified},
        )

    summaries = {arm: _summaries(records, arm) for arm in ARMS}
    expected_shard_ids = all_sample_ids[args.shard_index :: args.shard_count]
    complete_shard = set(record["sample_id"] for record in records) == set(
        expected_shard_ids
    )
    summary = {
        "status": "v24_3_full_199_score_validation_shard",
        "decision": SHARD_COMPLETE if complete_shard and determinism_verified else INCOMPLETE,
        "complete_shard": complete_shard,
        "sample_count": len(records),
        "expected_sample_count": len(expected_shard_ids),
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "determinism_verified": determinism_verified,
        "summaries": summaries,
        "v24_3_vs_v19": _comparison(records, ARM_V24_3),
        "checkpoint_usage_counts": {
            "held_out_27": sum(record["sample_id"] in held_out_ids for record in records),
            "checkpoint_training_172": sum(
                record["sample_id"] in training_ids for record in records
            ),
        },
        "population_interpretation": (
            "The 172 checkpoint-training samples are population score context, not "
            "independent generalization evidence."
        ),
        "assignment_enabled": False,
        "hybrid_enabled": False,
        "production_graph_mutation": False,
        "submission_authorized": False,
        "provenance": provenance,
    }
    _atomic_json(args.output_dir / "summary.json", summary)
    _write_csv(args.output_dir / "per_sample.csv", records)
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "decision",
                    "sample_count",
                    "complete_shard",
                    "determinism_verified",
                    "submission_authorized",
                )
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
