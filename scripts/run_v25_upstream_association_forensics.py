from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from atabey.evaluation.official_association_forensics import (
    OfficialAssociationCorrespondence,
    extract_official_association_correspondence,
)
from atabey.io.geff_reader import read_geff_graph
from atabey.provenance import canonical_text_sha256
from atabey.tracking.association_forensics import (
    AssociationGraphAudit,
    association_graph_payload,
    audit_motion_mutual_graph,
    classify_regression_mechanism,
)
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v22_unet_detection_shadow import _load_public_predict_module
from run_v24_score_first_tracking import (
    _config_payload,
    _predict_config,
    _predict_once,
    _sha256,
    _validate_checkpoint,
)


def _matched_gt_edges(
    correspondence: OfficialAssociationCorrespondence,
) -> set[tuple[int, int]]:
    return {
        (edge.ground_truth_source_id, edge.ground_truth_target_id)
        for edge in correspondence.edges
        if edge.officially_matched
        and edge.ground_truth_source_id is not None
        and edge.ground_truth_target_id is not None
    }


def classify_v19_credited_losses(
    audit: AssociationGraphAudit,
    relink: OfficialAssociationCorrespondence,
    v19: OfficialAssociationCorrespondence,
    v24_3: OfficialAssociationCorrespondence,
    *,
    adjustment_only_effect: bool,
) -> list[dict[str, Any]]:
    """Classify GT edges credited to V19 but not frozen V24.3."""

    prediction_ids_by_gt: dict[int, set[str]] = {}
    for node in relink.nodes:
        if node.ground_truth_node_id is not None:
            prediction_ids_by_gt.setdefault(node.ground_truth_node_id, set()).add(
                node.prediction_node_id
            )
    candidates = [candidate for frame in audit.frames for candidate in frame.candidates]
    lost_edges = sorted(_matched_gt_edges(v19) - _matched_gt_edges(v24_3))
    records: list[dict[str, Any]] = []
    for gt_source_id, gt_target_id in lost_edges:
        sources = prediction_ids_by_gt.get(gt_source_id, set())
        targets = prediction_ids_by_gt.get(gt_target_id, set())
        matching_candidates = [
            candidate
            for candidate in candidates
            if candidate.source_id in sources and candidate.target_id in targets
        ]
        candidate_present = bool(matching_candidates)
        candidate_accepted = any(candidate.accepted for candidate in matching_candidates)
        accepted_survives = any(
            candidate.accepted and candidate.survives_pruning is True
            for candidate in matching_candidates
        )
        records.append(
            {
                "ground_truth_source_id": gt_source_id,
                "ground_truth_target_id": gt_target_id,
                "matched_e016_source_ids": sorted(sources),
                "matched_e016_target_ids": sorted(targets),
                "correct_candidate_present": candidate_present,
                "correct_candidate_accepted": candidate_accepted,
                "correct_edge_survives_pruning": (
                    accepted_survives if candidate_accepted else None
                ),
                "candidate_ranks": sorted(
                    candidate.rank for candidate in matching_candidates
                ),
                "failure_class": classify_regression_mechanism(
                    correct_source_detected=bool(sources),
                    correct_target_detected=bool(targets),
                    correct_candidate_present=candidate_present,
                    correct_candidate_accepted=candidate_accepted,
                    correct_edge_survives_pruning=(
                        accepted_survives if candidate_accepted else None
                    ),
                    adjustment_only_effect=adjustment_only_effect,
                ),
            }
        )
    return records


def _atomic_gzip_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary.write_bytes(gzip.compress(content, mtime=0))
    temporary.replace(path)


def _read_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _summary_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": record["sample_id"],
        "lost_edge_count": len(record["v19_credited_v24_3_lost_edges"]),
        "failure_class_counts": record["failure_class_counts"],
    }


def _graph_signature_sha256(graph: Any) -> str:
    return hashlib.sha256(repr(graph_signature(graph)).encode("utf-8")).hexdigest()


def _validate_contract(contract: dict[str, Any]) -> list[str]:
    sample_ids = contract["cohort"]["sample_ids"]
    if len(sample_ids) != 16 or len(set(sample_ids)) != 16:
        raise RuntimeError("V25 regression cohort must contain 16 unique samples")
    for path, expected_hash in contract["sources"].values():
        if canonical_text_sha256(ROOT / path) != expected_hash:
            raise RuntimeError(f"V25 source hash mismatch: {path}")
    return sample_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run read-only V25 upstream association forensics."
    )
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--support-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "tests/fixtures/v25_upstream_association_forensics.json",
    )
    parser.add_argument(
        "--checkpoint-contract",
        type=Path,
        default=ROOT / "tests/fixtures/v24_score_first_tracking.json",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("v25_upstream_forensics"))
    parser.add_argument("--unet-batch-size", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("V25 frozen E016 inference requires a CUDA GPU")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    sample_ids = _validate_contract(contract)
    checkpoint_contract = json.loads(
        args.checkpoint_contract.read_text(encoding="utf-8")
    )
    provenance = _validate_checkpoint(args.weights, checkpoint_contract)
    predictor_path = args.support_repo / "scripts/predict_unet_transformer.py"
    if _sha256(predictor_path) != contract["frozen_baseline"]["predictor_sha256"]:
        raise RuntimeError("Predictor SHA-256 mismatch")

    public_module = _load_public_predict_module(args.support_repo)
    device = torch.device("cuda")
    model, window_size, downsample = public_module.load_model(args.weights, device)
    predict_config = _predict_config(public_module, checkpoint_contract)
    provenance.update(
        {
            "contract_sha256": canonical_text_sha256(args.contract),
            "predictor_sha256": _sha256(predictor_path),
            "predict_config": _config_payload(predict_config),
            "unet_batch_size": args.unet_batch_size,
            "max_timepoints": None,
            "score_claim": False,
            "graph_mutation": False,
        }
    )
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = output_dir / "provenance.json"
    if provenance_path.exists():
        if json.loads(provenance_path.read_text(encoding="utf-8")) != provenance:
            raise RuntimeError("Existing V25 output provenance differs from this run")
    else:
        provenance_path.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    adjustment_only_ids = set(contract["initial_taxonomy"]["adjustment_only"])
    summaries: list[dict[str, Any]] = []
    for index, sample_id in enumerate(sample_ids, start=1):
        output_path = output_dir / "samples" / f"{sample_id}.json.gz"
        if args.resume and output_path.exists():
            record = _read_gzip_json(output_path)
            if record.get("sample_id") != sample_id:
                raise RuntimeError(f"Resumed artifact identity mismatch for {sample_id}")
            summaries.append(_summary_record(record))
            print(f"[{index}/16] {sample_id}: resumed", flush=True)
            continue
        print(f"[{index}/16] {sample_id}: running", flush=True)
        sample_path = args.train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        v19, detector, link_strategy = _build_v19_prefirewall_with_route(
            sample_path, None
        )
        if (detector, link_strategy) != ("components", "greedy"):
            raise RuntimeError(f"Frozen V19 route mismatch for {sample_id}")
        coordinates, _, inference_runtime = _predict_once(
            public_module,
            model,
            sample_path,
            device,
            predict_config,
            window_size,
            downsample,
            None,
            args.unet_batch_size,
        )
        relink = relink_predictor_detections(sample_id, coordinates)
        v24_2 = prune_interior_isolated_detections(relink)
        v24_3 = prune_interior_short_fragments(v24_2)
        before = graph_signature(relink)
        audit = audit_motion_mutual_graph(relink, post_pruning_graph=v24_3)
        correspondences = {
            "v19": extract_official_association_correspondence(v19, ground_truth),
            "relink": extract_official_association_correspondence(relink, ground_truth),
            "v24_3": extract_official_association_correspondence(v24_3, ground_truth),
        }
        if graph_signature(relink) != before or not audit.graph_unchanged:
            raise RuntimeError("V25 observer mutated the frozen relink graph")
        losses = classify_v19_credited_losses(
            audit,
            correspondences["relink"],
            correspondences["v19"],
            correspondences["v24_3"],
            adjustment_only_effect=sample_id in adjustment_only_ids,
        )
        class_counts = dict(sorted(Counter(row["failure_class"] for row in losses).items()))
        record = {
            "sample_id": sample_id,
            "v19_route": {"detector": detector, "linker": link_strategy},
            "inference_runtime_seconds": inference_runtime,
            "coordinate_count": len(coordinates),
            "graph_signatures": {
                "relink_sha256": _graph_signature_sha256(relink),
                "v24_2_sha256": _graph_signature_sha256(v24_2),
                "v24_3_sha256": _graph_signature_sha256(v24_3),
                "v19_sha256": _graph_signature_sha256(v19),
            },
            "association_audit": asdict(audit),
            "visualization": association_graph_payload(audit, relink, v24_3, v19),
            "official_correspondence": {
                name: asdict(value) for name, value in correspondences.items()
            },
            "v19_credited_v24_3_lost_edges": losses,
            "failure_class_counts": class_counts,
            "graph_mutated": False,
            "score_claim": False,
        }
        _atomic_gzip_json(output_path, record)
        summaries.append(_summary_record(record))

    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "status": "V25_OBSERVABILITY_COMPLETE",
                "completed_samples": len(summaries),
                "samples": summaries,
                "score_claim": False,
                "selector_claim": False,
                "graph_mutation": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()