from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from atabey.evaluation.official_tracking_metric import evaluate_official_tracking
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.commitment_ilp_shadow import audit_commitment_ilp_funnel
from atabey.tracking.commitment_shadow import audit_motion_mutual_commitment
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments
from atabey.types import LineageEdge, LineageGraph
from run_v22_unet_detection_shadow import _load_public_predict_module
from run_v24_score_first_tracking import (
    _config_payload,
    _predict_config,
    _predict_once,
    _sha256,
    _validate_checkpoint,
)


EdgeKey = tuple[str, str]


def _canonical_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def apply_edge_proposal(
    graph: LineageGraph,
    *,
    removed_edges: Iterable[EdgeKey],
    added_edges: Iterable[EdgeKey],
) -> LineageGraph:
    """Apply a diagnostic edge proposal to a new graph and fail closed."""

    nodes = {node.node_id: node for node in graph.detections}
    baseline = {(edge.source_id, edge.target_id): edge for edge in graph.edges}
    removals = set(removed_edges)
    additions = set(added_edges)
    absent = sorted(removals - set(baseline))
    if absent:
        raise ValueError(f"Proposal removes an absent baseline edge: {absent}")
    for source_id, target_id in additions:
        source = nodes.get(source_id)
        target = nodes.get(target_id)
        if source is None or target is None:
            raise ValueError(f"Proposal adds an edge with an absent endpoint: {(source_id, target_id)}")
        if int(target.t) != int(source.t) + 1:
            raise ValueError(f"Proposal adds a non-adjacent edge: {(source_id, target_id)}")

    retained = [
        edge for edge in graph.edges if (edge.source_id, edge.target_id) not in removals
    ]
    final_keys = {(edge.source_id, edge.target_id) for edge in retained}
    if final_keys.intersection(additions):
        raise ValueError("Proposal adds an edge already present after removals")
    final_keys.update(additions)
    continuation = [
        key
        for key in final_keys
        if baseline.get(key, LineageEdge(*key)).relation == "continuation"
    ]
    sources = [source_id for source_id, _ in continuation]
    targets = [target_id for _, target_id in continuation]
    if len(sources) != len(set(sources)):
        raise ValueError("Proposal creates multiple continuation children")
    if len(targets) != len(set(targets)):
        raise ValueError("Proposal creates multiple continuation parents")

    proposed = LineageGraph(sample_id=graph.sample_id)
    proposed.detections.extend(graph.detections)
    proposed.edges.extend(retained)
    proposed.edges.extend(
        LineageEdge(source_id=source_id, target_id=target_id)
        for source_id, target_id in sorted(additions)
    )
    return proposed


def _validate_contract(contract: dict[str, Any]) -> tuple[list[str], set[str]]:
    cohort = contract["cohort"]
    sample_ids = list(cohort["sample_ids"])
    regressions = set(cohort["regression_sample_ids"])
    if len(sample_ids) != cohort["expected_samples"] or len(sample_ids) != len(set(sample_ids)):
        raise RuntimeError("Route-90 cohort count or uniqueness contract failed")
    if sample_ids != sorted(sample_ids) or not regressions < set(sample_ids):
        raise RuntimeError("Route-90 ordering or regression subset contract failed")
    route_path = ROOT / contract["sources"]["route_inventory"]
    forensic_path = ROOT / contract["sources"]["regression_forensics"]
    if _canonical_text_sha256(route_path) != contract["sources"]["route_inventory_sha256"]:
        raise RuntimeError("Route inventory hash mismatch")
    if _canonical_text_sha256(forensic_path) != contract["sources"]["regression_forensics_sha256"]:
        raise RuntimeError("Regression forensics hash mismatch")
    route_records = json.loads(route_path.read_text(encoding="utf-8"))["records"]
    derived = sorted(
        record["sample_id"]
        for record in route_records
        if record["family"] == "6bba"
        and record["detector"] == "components"
        and record["link_strategy"] == "greedy"
    )
    if derived != sample_ids:
        raise RuntimeError("Route-90 sample IDs differ from the tracked route inventory")
    return sample_ids, regressions


def _proposal_class(removed: tuple[EdgeKey, ...], added: tuple[EdgeKey, ...]) -> str:
    if removed and added:
        return "ownership_rewrite"
    if added:
        return "add_only"
    if removed:
        return "remove_only"
    return "exact_baseline"


def _metric_payload(result: object) -> dict[str, Any]:
    return asdict(result)


def _score_proposal(
    baseline: LineageGraph,
    ground_truth: object,
    baseline_metrics: dict[str, Any],
    *,
    removed_edges: tuple[EdgeKey, ...],
    added_edges: tuple[EdgeKey, ...],
) -> dict[str, Any]:
    proposal_class = _proposal_class(removed_edges, added_edges)
    if proposal_class == "exact_baseline":
        metrics = baseline_metrics
    else:
        proposed = apply_edge_proposal(
            baseline,
            removed_edges=removed_edges,
            added_edges=added_edges,
        )
        metrics = _metric_payload(evaluate_official_tracking(proposed, ground_truth))
    return {
        "proposal_class": proposal_class,
        "removed_edges": removed_edges,
        "added_edges": added_edges,
        "metrics": metrics,
        "adjusted_edge_jaccard_delta": (
            metrics["adjusted_edge_jaccard"] - baseline_metrics["adjusted_edge_jaccard"]
        ),
        "edge_jaccard_delta": metrics["edge_jaccard"] - baseline_metrics["edge_jaccard"],
    }


def _evaluate_sample(
    *,
    sample_id: str,
    is_regression: bool,
    train_dir: Path,
    public_module: object,
    model: object,
    device: object,
    predict_config: object,
    window_size: int,
    downsample: tuple[int, ...],
    unet_batch_size: int,
    shadow_contract: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    coordinates, _, inference_runtime = _predict_once(
        public_module,
        model,
        train_dir / f"{sample_id}.zarr",
        device,
        predict_config,
        window_size,
        downsample,
        None,
        unet_batch_size,
    )
    relink = relink_predictor_detections(sample_id, coordinates)
    v24_3 = prune_interior_short_fragments(prune_interior_isolated_detections(relink))
    before = graph_signature(relink)
    settings = shadow_contract["shadow"]
    commitment = audit_motion_mutual_commitment(
        relink,
        horizon_frames=settings["commitment_horizon_frames"],
        max_counterfactual_edges=settings["max_counterfactual_edges"],
    )
    funnel = audit_commitment_ilp_funnel(
        relink,
        commitment,
        baseline_change_penalty_um=settings["baseline_change_penalty_um"],
        minimum_improvement_um=settings["minimum_improvement_um"],
        max_ilp_windows=settings["max_ilp_windows"],
        max_variables=settings["max_variables"],
        time_limit_seconds=settings["time_limit_seconds"],
    )
    if graph_signature(relink) != before:
        raise RuntimeError("Combined shadow mutated the relinked graph")

    ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")
    baseline_metrics = _metric_payload(evaluate_official_tracking(v24_3, ground_truth))
    counterfactuals = []
    for record in funnel.records:
        primary = record.primary
        diagnostic = record.zero_penalty_diagnostic
        counterfactuals.append(
            {
                "source_id": record.source_id,
                "target_id": record.target_id,
                "reconverged": record.reconverged,
                "minimum_margin_um": record.minimum_margin_um,
                "primary": _score_proposal(
                    v24_3,
                    ground_truth,
                    baseline_metrics,
                    removed_edges=primary.proposed_removed_edges,
                    added_edges=primary.proposed_added_edges,
                ),
                "zero_penalty_diagnostic": _score_proposal(
                    v24_3,
                    ground_truth,
                    baseline_metrics,
                    removed_edges=diagnostic.proposed_removed_edges,
                    added_edges=diagnostic.proposed_added_edges,
                ),
            }
        )
    return {
        "sample_id": sample_id,
        "retrospective_v24_3_regression": is_regression,
        "coordinate_count": len(coordinates),
        "inference_runtime_seconds": inference_runtime,
        "total_runtime_seconds": time.perf_counter() - started,
        "relink_graph_signature_sha256": hashlib.sha256(
            repr(before).encode("utf-8")
        ).hexdigest(),
        "v24_3_baseline_metrics": baseline_metrics,
        "commitment": asdict(commitment),
        "funnel": asdict(funnel),
        "counterfactuals": counterfactuals,
        "graph_mutated": False,
    }


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    strata = {
        "regression_16": [record for record in records if record["retrospective_v24_3_regression"]],
        "route_control_74": [record for record in records if not record["retrospective_v24_3_regression"]],
        "route_90": records,
    }
    output: dict[str, Any] = {}
    for name, members in strata.items():
        windows = [item for record in members for item in record["counterfactuals"]]
        persistent = [item for item in windows if not item["reconverged"]]
        diagnostic_rewrites = [
            item
            for item in windows
            if item["zero_penalty_diagnostic"]["proposal_class"] == "ownership_rewrite"
        ]
        deltas = [
            item["zero_penalty_diagnostic"]["adjusted_edge_jaccard_delta"]
            for item in diagnostic_rewrites
        ]
        output[name] = {
            "sample_count": len(members),
            "root_changed_window_count": len(windows),
            "root_persistent_window_count": len(persistent),
            "primary_ownership_rewrite_count": sum(
                item["primary"]["proposal_class"] == "ownership_rewrite" for item in windows
            ),
            "zero_penalty_ownership_rewrite_count": len(diagnostic_rewrites),
            "zero_penalty_rewrite_improved_count": sum(delta > 0 for delta in deltas),
            "zero_penalty_rewrite_regressed_count": sum(delta < 0 for delta in deltas),
            "zero_penalty_rewrite_mean_adjusted_delta": statistics.fmean(deltas) if deltas else None,
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen V24.7 route-90 GPU shadow.")
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--support-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument(
        "--checkpoint-contract",
        type=Path,
        default=ROOT / "tests/fixtures/v24_score_first_tracking.json",
    )
    parser.add_argument(
        "--shadow-contract",
        type=Path,
        default=ROOT / "tests/fixtures/v24_7_route_90_shadow.json",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("v24_7_route_90_shadow"))
    parser.add_argument("--unet-batch-size", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify-determinism", action="store_true")
    args = parser.parse_args()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("The route-90 frozen predictor run requires a CUDA GPU")
    checkpoint_contract = json.loads(args.checkpoint_contract.read_text(encoding="utf-8"))
    shadow_contract = json.loads(args.shadow_contract.read_text(encoding="utf-8"))
    sample_ids, regressions = _validate_contract(shadow_contract)
    provenance = _validate_checkpoint(args.weights, checkpoint_contract)
    predictor_path = args.support_repo / "scripts/predict_unet_transformer.py"
    if _sha256(predictor_path) != shadow_contract["sources"]["predictor_sha256"]:
        raise RuntimeError("Predictor SHA-256 mismatch")

    public_module = _load_public_predict_module(args.support_repo)
    device = torch.device("cuda")
    model, window_size, downsample = public_module.load_model(args.weights, device)
    predict_config = _predict_config(public_module, checkpoint_contract)
    output_dir = args.output_dir
    sample_dir = output_dir / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    provenance.update(
        {
            "predictor_sha256": _sha256(predictor_path),
            "shadow_contract_sha256": _sha256(args.shadow_contract),
            "predict_config": _config_payload(predict_config),
            "unet_batch_size": args.unet_batch_size,
            "max_timepoints": None,
        }
    )
    provenance_path = output_dir / "provenance.json"
    if provenance_path.exists():
        if json.loads(provenance_path.read_text(encoding="utf-8")) != provenance:
            raise RuntimeError("Existing output provenance differs from this run")
    else:
        _atomic_json(provenance_path, provenance)

    records = []
    for index, sample_id in enumerate(sample_ids, start=1):
        path = sample_dir / f"{sample_id}.json"
        if args.resume and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            print(f"[{index}/90] {sample_id}: resumed", flush=True)
        else:
            print(f"[{index}/90] {sample_id}: running", flush=True)
            record = _evaluate_sample(
                sample_id=sample_id,
                is_regression=sample_id in regressions,
                train_dir=args.train_dir,
                public_module=public_module,
                model=model,
                device=device,
                predict_config=predict_config,
                window_size=window_size,
                downsample=downsample,
                unet_batch_size=args.unet_batch_size,
                shadow_contract=shadow_contract,
            )
            _atomic_json(path, record)
        records.append(record)
        print(
            f"  changed={record['funnel']['root_changed_window_count']} "
            f"persistent={record['funnel']['root_persistent_window_count']} "
            f"primary={record['funnel']['primary_alternative_count']} "
            f"diagnostic={record['funnel']['zero_penalty_alternative_count']}",
            flush=True,
        )

    determinism_verified = False
    if args.verify_determinism:
        repeated = _evaluate_sample(
            sample_id=sample_ids[0],
            is_regression=sample_ids[0] in regressions,
            train_dir=args.train_dir,
            public_module=public_module,
            model=model,
            device=device,
            predict_config=predict_config,
            window_size=window_size,
            downsample=downsample,
            unet_batch_size=args.unet_batch_size,
            shadow_contract=shadow_contract,
        )
        determinism_verified = (
            repeated["relink_graph_signature_sha256"]
            == records[0]["relink_graph_signature_sha256"]
            and repeated["commitment"] == records[0]["commitment"]
            and repeated["funnel"] == records[0]["funnel"]
            and repeated["counterfactuals"] == records[0]["counterfactuals"]
        )
        _atomic_json(
            output_dir / "determinism.json",
            {"sample_id": sample_ids[0], "verified": determinism_verified},
        )

    summary = {
        "status": "v24_7_route_90_shadow_complete",
        "sample_count": len(records),
        "expected_sample_count": shadow_contract["cohort"]["expected_samples"],
        "complete_cohort": len(records) == shadow_contract["cohort"]["expected_samples"],
        "determinism_verified": determinism_verified,
        **shadow_contract["boundaries"],
        "aggregate": _aggregate(records),
        "provenance": provenance,
    }
    _atomic_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()