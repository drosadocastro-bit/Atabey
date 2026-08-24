from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, fields, is_dataclass, replace
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from atabey.evaluation.official_tracking_metric import (
    OfficialTrackingResult,
    evaluate_official_tracking,
    summarize_official_tracking,
)
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.unet_graph import (
    graph_signature,
    native_graph_from_predictor_output,
    relink_predictor_detections,
)
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v22_unet_detection_shadow import _load_public_predict_module


ARM_V19 = "v19_frozen_reference"
ARM_RELINK = "e016_atabey_relink"
ARM_NATIVE = "e016_native_graph"
ARM_V24_2 = "e016_atabey_relink_v24_2_shadow"
ARMS = (ARM_V19, ARM_RELINK, ARM_NATIVE, ARM_V24_2)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _official_result(payload: dict[str, Any]) -> OfficialTrackingResult:
    allowed = {field.name for field in fields(OfficialTrackingResult)}
    return OfficialTrackingResult(**{key: payload[key] for key in allowed})


def _folds(sample_ids: list[str], seed: str) -> dict[str, int]:
    assignments: dict[str, int] = {}
    families = sorted({sample_id.split("_", 1)[0] for sample_id in sample_ids})
    for family in families:
        members = [sample_id for sample_id in sample_ids if sample_id.startswith(family + "_")]
        ordered = sorted(
            members,
            key=lambda sample_id: hashlib.sha256(
                f"{seed}|{sample_id}".encode("ascii")
            ).hexdigest(),
        )
        for index, sample_id in enumerate(ordered):
            assignments[sample_id] = index % 3 + 1
    return assignments


def _config_payload(config: object) -> dict[str, Any]:
    if is_dataclass(config):
        return asdict(config)
    if hasattr(config, "__dict__"):
        return dict(vars(config))
    return {"repr": repr(config)}


def _predict_config(public_module, contract: dict[str, Any]):
    config = public_module.PredictConfig()
    required = {"det_threshold", "pool_kernel_um", "det_tta"}
    available = set(_config_payload(config))
    missing = required - available
    if missing:
        raise RuntimeError(f"Public PredictConfig lacks required fields: {sorted(missing)}")
    overrides = {
        "det_threshold": float(contract["checkpoint"]["detection_threshold"]),
        "pool_kernel_um": float(contract["checkpoint"]["pool_kernel_um"]),
        "det_tta": False,
    }
    if is_dataclass(config):
        return replace(config, **overrides)
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _validate_checkpoint(weights: Path, contract: dict[str, Any]) -> dict[str, Any]:
    expected_hash = contract["checkpoint"]["sha256"]
    actual_hash = _sha256(weights)
    if actual_hash != expected_hash:
        raise RuntimeError(f"Checkpoint SHA-256 mismatch: {actual_hash} != {expected_hash}")
    config_path = weights.parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Checkpoint config is missing: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected = contract["checkpoint"]
    checks = {
        "window_size": int(config.get("window_size", -1)) == expected["window_size"],
        "downsample": list(config.get("downsample", [])) == expected["downsample"],
        "unet_out_channels": int(config.get("unet_out_channels", -1))
        == expected["unet_out_channels"],
        "pool_kernel_um": float(config.get("pool_kernel_um", -1.0))
        == expected["pool_kernel_um"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"Checkpoint config contract failed: {checks}")
    return {
        "weights_sha256": actual_hash,
        "config_sha256": _sha256(config_path),
        "config": config,
    }


def _predict_once(
    public_module,
    model,
    sample_path: Path,
    device,
    predict_config,
    window_size: int,
    downsample: tuple[int, ...],
    max_timepoints: int | None,
    unet_batch_size: int,
):
    started = time.perf_counter()
    coordinates, native_edges = public_module.predict_video(
        model,
        sample_path,
        device,
        predict_config,
        window_size=window_size,
        max_frames=max_timepoints,
        unet_batch_size=unet_batch_size,
        downsample=downsample,
    )
    return coordinates, native_edges, time.perf_counter() - started


def _evaluate_sample(
    *,
    sample_id: str,
    train_dir: Path,
    public_module,
    model,
    device,
    predict_config,
    window_size: int,
    downsample: tuple[int, ...],
    max_timepoints: int | None,
    unet_batch_size: int,
    fold: int,
) -> dict[str, Any]:
    import torch

    sample_path = train_dir / f"{sample_id}.zarr"
    ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")

    v19_started = time.perf_counter()
    v19, detector, link_strategy = _build_v19_prefirewall_with_route(
        sample_path,
        max_timepoints,
    )
    v19_runtime = time.perf_counter() - v19_started

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    coordinates, native_edges, inference_runtime = _predict_once(
        public_module,
        model,
        sample_path,
        device,
        predict_config,
        window_size,
        downsample,
        max_timepoints,
        unet_batch_size,
    )
    peak_memory = (
        int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else None
    )

    relink_started = time.perf_counter()
    relink = relink_predictor_detections(sample_id, coordinates)
    relink_runtime = time.perf_counter() - relink_started
    native_started = time.perf_counter()
    native = native_graph_from_predictor_output(sample_id, coordinates, native_edges)
    native_runtime = time.perf_counter() - native_started
    shadow = relink
    shadow_removed_nodes = 0
    shadow_edge_set_preserved = True
    if detector == "components" and sample_id.startswith("6bba_"):
        shadow = prune_interior_isolated_detections(relink)
        shadow_removed_nodes = len(relink.detections) - len(shadow.detections)
        shadow_edge_set_preserved = {
            (edge.source_id, edge.target_id, edge.relation) for edge in relink.edges
        } == {
            (edge.source_id, edge.target_id, edge.relation) for edge in shadow.edges
        }

    graphs = {
        ARM_V19: v19,
        ARM_RELINK: relink,
        ARM_NATIVE: native,
        ARM_V24_2: shadow,
    }
    runtimes = {
        ARM_V19: v19_runtime,
        ARM_RELINK: inference_runtime + relink_runtime,
        ARM_NATIVE: inference_runtime + native_runtime,
        ARM_V24_2: inference_runtime + relink_runtime,
    }
    arm_rows: dict[str, Any] = {}
    for arm, graph in graphs.items():
        metric_started = time.perf_counter()
        metrics = evaluate_official_tracking(graph, ground_truth)
        arm_rows[arm] = {
            "metrics": asdict(metrics),
            "predicted_edges": len(graph.edges),
            "runtime_seconds": runtimes[arm],
            "metric_runtime_seconds": time.perf_counter() - metric_started,
            "peak_gpu_memory_bytes": peak_memory if arm != ARM_V19 else None,
            "graph_signature_sha256": hashlib.sha256(
                repr(graph_signature(graph)).encode("utf-8")
            ).hexdigest(),
            "shadow_removed_nodes": shadow_removed_nodes if arm == ARM_V24_2 else 0,
            "shadow_edge_set_preserved": (
                shadow_edge_set_preserved if arm == ARM_V24_2 else None
            ),
        }

    return {
        "sample_id": sample_id,
        "family": sample_id.split("_", 1)[0],
        "fold": fold,
        "v19_reference_detector": detector,
        "v19_reference_link_strategy": link_strategy,
        "predictor_coordinates": len(coordinates),
        "predictor_native_edges": len(native_edges),
        "arms": arm_rows,
    }


def _summaries(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return asdict(
            summarize_official_tracking(
                [_official_result(row["arms"][arm]["metrics"]) for row in rows]
            )
        )

    overall = summarize(records)
    by_family = {
        family: summarize([row for row in records if row["family"] == family])
        for family in sorted({row["family"] for row in records})
    }
    by_fold = {
        str(fold): summarize([row for row in records if row["fold"] == fold])
        for fold in sorted({row["fold"] for row in records})
    }
    by_route = {
        route: summarize(
            [row for row in records if row["v19_reference_detector"] == route]
        )
        for route in sorted({row["v19_reference_detector"] for row in records})
    }
    return {
        "overall": overall,
        "by_family": by_family,
        "by_fold": by_fold,
        "by_v19_reference_route": by_route,
    }


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return float(after) - float(before)


def _decision(
    records: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    contract: dict[str, Any],
    determinism_verified: bool,
) -> dict[str, Any]:
    gates = contract["go_gates"]
    reference = summaries[ARM_V19]
    outcomes: dict[str, Any] = {}
    passing: list[str] = []
    for arm in (ARM_RELINK, ARM_NATIVE, ARM_V24_2):
        challenger = summaries[arm]
        pooled_delta = _delta(
            challenger["overall"]["adjusted_edge_jaccard"],
            reference["overall"]["adjusted_edge_jaccard"],
        )
        score_delta = _delta(
            challenger["overall"]["score"], reference["overall"]["score"]
        )
        family_deltas = {
            family: _delta(
                challenger["by_family"][family]["adjusted_edge_jaccard"],
                reference["by_family"][family]["adjusted_edge_jaccard"],
            )
            for family in reference["by_family"]
        }
        fold_deltas = {
            fold: _delta(
                challenger["by_fold"][fold]["adjusted_edge_jaccard"],
                reference["by_fold"][fold]["adjusted_edge_jaccard"],
            )
            for fold in reference["by_fold"]
        }
        sample_deltas = [
            _delta(
                row["arms"][arm]["metrics"]["adjusted_edge_jaccard"],
                row["arms"][ARM_V19]["metrics"]["adjusted_edge_jaccard"],
            )
            for row in records
        ]
        finite_deltas = [value for value in sample_deltas if value is not None]
        tolerance = float(contract["evaluation"]["delta_tolerance"])
        improved = sum(value > tolerance for value in finite_deltas)
        regressed = sum(value < -tolerance for value in finite_deltas)
        flat = len(finite_deltas) - improved - regressed
        node_ratios = [
            row["arms"][arm]["metrics"]["predicted_nodes"]
            / max(row["arms"][ARM_V19]["metrics"]["predicted_nodes"], 1)
            for row in records
        ]
        checks = {
            "pooled_adjusted_edge_delta": pooled_delta is not None
            and pooled_delta >= gates["pooled_adjusted_edge_delta_min"],
            "pooled_total_score_delta": score_delta is not None
            and score_delta >= gates["pooled_total_score_delta_min"],
            "each_family": all(
                value is not None
                and value >= gates["each_family_adjusted_edge_delta_min"]
                for value in family_deltas.values()
            ),
            "each_fold": all(
                value is not None
                and value >= gates["each_fold_adjusted_edge_delta_min"]
                for value in fold_deltas.values()
            ),
            "improved_exceeds_regressed": improved > regressed,
            "catastrophic_regressions": sum(
                value < gates["catastrophic_regression_threshold"]
                for value in finite_deltas
            )
            <= gates["catastrophic_regression_count_max"],
            "median_node_ratio": statistics.median(node_ratios)
            <= gates["median_node_ratio_max"],
            "p90_node_ratio": float(np.quantile(node_ratios, 0.9))
            <= gates["p90_node_ratio_max"],
            "completed_samples": len(records) == gates["completed_samples_required"],
            "determinism": determinism_verified,
        }
        passed = all(checks.values())
        if passed:
            passing.append(arm)
        outcomes[arm] = {
            "passed": passed,
            "pooled_adjusted_edge_delta": pooled_delta,
            "pooled_total_score_delta": score_delta,
            "family_deltas": family_deltas,
            "fold_deltas": fold_deltas,
            "improved": improved,
            "flat": flat,
            "regressed": regressed,
            "median_node_ratio": statistics.median(node_ratios),
            "p90_node_ratio": float(np.quantile(node_ratios, 0.9)),
            "checks": checks,
        }
    if passing:
        decision = "GO_TO_FULL_199_SCORE_VALIDATION"
    elif any(
        result["pooled_adjusted_edge_delta"] is not None
        and result["pooled_adjusted_edge_delta"]
        >= gates["pooled_adjusted_edge_delta_min"]
        for result in outcomes.values()
    ):
        decision = "HOLD_SCORE_GAIN_WITH_STRATUM_OR_INFLATION_CONCERN"
    else:
        decision = "NO_GO_V24_CHALLENGERS"
    return {"decision": decision, "passing_arms": passing, "arms": outcomes}


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for record in records:
        row = {key: value for key, value in record.items() if key != "arms"}
        for arm in ARMS:
            arm_row = record["arms"][arm]
            row.update({f"{arm}_{key}": value for key, value in arm_row["metrics"].items()})
            row[f"{arm}_predicted_edges"] = arm_row["predicted_edges"]
            row[f"{arm}_runtime_seconds"] = arm_row["runtime_seconds"]
            row[f"{arm}_shadow_removed_nodes"] = arm_row["shadow_removed_nodes"]
            row[f"{arm}_shadow_edge_set_preserved"] = arm_row[
                "shadow_edge_set_preserved"
            ]
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered V24 score-first audit.")
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--support-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=ROOT / "tests/fixtures/v24_score_first_tracking.json")
    parser.add_argument("--output-dir", type=Path, default=Path("v24_score_first_tracking"))
    parser.add_argument("--sample-ids", nargs="+", default=["smoke"])
    parser.add_argument("--max-timepoints", type=int, default=None)
    parser.add_argument("--unet-batch-size", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify-determinism", action="store_true")
    args = parser.parse_args()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("V24 learned arms require a CUDA GPU")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    provenance = _validate_checkpoint(args.weights, contract)
    predictor_path = args.support_repo / "scripts/predict_unet_transformer.py"
    if not predictor_path.exists():
        raise FileNotFoundError(f"Public predictor is missing: {predictor_path}")
    provenance.update(
        {
            "predictor_path": str(predictor_path),
            "predictor_sha256": _sha256(predictor_path),
            "support_pack": contract["sources"]["support_pack"],
        }
    )

    public_module = _load_public_predict_module(args.support_repo)
    device = torch.device("cuda")
    model, window_size, downsample = public_module.load_model(args.weights, device)
    predict_config = _predict_config(public_module, contract)
    if window_size != contract["checkpoint"]["window_size"]:
        raise RuntimeError("Loaded window size differs from the frozen contract")
    if list(downsample) != contract["checkpoint"]["downsample"]:
        raise RuntimeError("Loaded downsample differs from the frozen contract")
    provenance["predict_config"] = _config_payload(predict_config)
    provenance["runtime_contract"] = {
        "max_timepoints": args.max_timepoints,
        "unet_batch_size": args.unet_batch_size,
    }

    requested = args.sample_ids
    if requested == ["all"]:
        sample_ids = list(contract["cohort"]["sample_ids"])
    elif requested == ["smoke"]:
        sample_ids = list(contract["smoke_samples"])
    else:
        unknown = sorted(set(requested) - set(contract["cohort"]["sample_ids"]))
        if unknown:
            raise ValueError(f"Samples outside the frozen cohort: {unknown}")
        sample_ids = list(dict.fromkeys(requested))

    output_dir = args.output_dir
    sample_dir = output_dir / "samples"
    output_dir.mkdir(parents=True, exist_ok=True)
    folds = _folds(list(contract["cohort"]["sample_ids"]), contract["evaluation"]["deterministic_fold_seed"])
    provenance_path = output_dir / "provenance.json"
    if provenance_path.exists():
        existing_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if existing_provenance != provenance:
            raise RuntimeError(
                "Output directory provenance differs from the current run; "
                "use a new output directory instead of mixing shards"
            )
    else:
        _atomic_json(provenance_path, provenance)

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
                max_timepoints=args.max_timepoints,
                unet_batch_size=args.unet_batch_size,
                fold=folds[sample_id],
            )
            _atomic_json(output_path, record)
        records.append(record)
        print(
            "  " + " | ".join(
                f"{arm}:adj={record['arms'][arm]['metrics']['adjusted_edge_jaccard']} nodes={record['arms'][arm]['metrics']['predicted_nodes']}"
                for arm in ARMS
            ),
            flush=True,
        )

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
            max_timepoints=args.max_timepoints,
            unet_batch_size=args.unet_batch_size,
            fold=folds[sample_id],
        )
        original = records[0]
        determinism_verified = all(
            original["arms"][arm]["graph_signature_sha256"]
            == repeated["arms"][arm]["graph_signature_sha256"]
            for arm in ARMS
        )
        _atomic_json(
            output_dir / "determinism.json",
            {"sample_id": sample_id, "verified": determinism_verified},
        )
    elif (output_dir / "determinism.json").exists():
        determinism_verified = bool(
            json.loads((output_dir / "determinism.json").read_text())["verified"]
        )

    arm_summaries = {arm: _summaries(records, arm) for arm in ARMS}
    complete_cohort = (
        set(sample_ids) == set(contract["cohort"]["sample_ids"])
        and args.max_timepoints is None
    )
    decision = (
        _decision(records, arm_summaries, contract, determinism_verified)
        if complete_cohort
        else {"decision": "SMOKE_OR_PARTIAL_COMPLETE", "passing_arms": []}
    )
    summary = {
        "status": "v24_score_first_tracking_result",
        **decision,
        "sample_count": len(records),
        "complete_cohort": complete_cohort,
        "determinism_verified": determinism_verified,
        "assignment_enabled": False,
        "hybrid_enabled": False,
        "production_graph_mutation": False,
        "full_199_authorized": decision["decision"] == "GO_TO_FULL_199_SCORE_VALIDATION",
        "summaries": arm_summaries,
        "provenance": provenance,
    }
    _atomic_json(output_dir / "summary.json", summary)
    _write_csv(output_dir / "per_sample.csv", records)
    print(json.dumps({key: summary[key] for key in ("decision", "sample_count", "complete_cohort", "determinism_verified", "full_199_authorized")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
