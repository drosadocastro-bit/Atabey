from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import tracemalloc
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.evaluation.official_association_forensics import (
    OfficialAssociationCorrespondence,
    extract_official_association_correspondence,
)
from atabey.evaluation.official_tracking_metric import (
    OfficialTrackingResult,
    evaluate_official_tracking,
    summarize_official_tracking,
)
from atabey.io.geff_reader import read_geff_graph
from atabey.provenance import canonical_text_sha256
from atabey.tracking.nearest_neighbor import _predicted_position
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments
from atabey.tracking.v26_a_forward_ranking_shadow import (
    relink_detections_step_ranked,
)
from atabey.types import Detection, LineageEdge, LineageGraph
from run_v25_upstream_association_forensics import _atomic_gzip_json


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _graph_signature_sha256(graph: LineageGraph) -> str:
    return hashlib.sha256(repr(graph_signature(graph)).encode("utf-8")).hexdigest()


def _reconstruct_frozen_relink(record: dict[str, Any]) -> LineageGraph:
    sample_id = str(record["sample_id"])
    node_rows: dict[str, tuple[int, tuple[float, float, float]]] = {}
    for frame in record["visualization"]["frames"]:
        for row in frame["nodes"]:
            node_id = str(row["node_id"])
            value = (
                int(row["t"]),
                tuple(float(item) for item in row["position_um"]),
            )
            if len(value[1]) != 3 or not all(math.isfinite(item) for item in value[1]):
                raise RuntimeError(f"Invalid V25 physical position for {node_id}")
            if node_id in node_rows and node_rows[node_id] != value:
                raise RuntimeError(f"Conflicting V25 node evidence for {node_id}")
            node_rows[node_id] = value
    if len(node_rows) != int(record["coordinate_count"]):
        raise RuntimeError(f"Incomplete V25 node evidence for {sample_id}")

    coordinates: list[list[float]] = []
    for index, (node_id, (t, position_um)) in enumerate(sorted(node_rows.items())):
        expected_node_id = f"unet:{sample_id}:n{index:08d}"
        if node_id != expected_node_id:
            raise RuntimeError(
                f"Unexpected V25 node order: {node_id} != {expected_node_id}"
            )
        z_um, y_um, x_um = position_um
        coordinates.append(
            [
                float(t),
                z_um / DEFAULT_VOXEL_SCALE_UM.z,
                y_um / DEFAULT_VOXEL_SCALE_UM.y,
                x_um / DEFAULT_VOXEL_SCALE_UM.x,
            ]
        )
    return relink_predictor_detections(sample_id, coordinates)


def _matched_gt_edges(
    correspondence: OfficialAssociationCorrespondence,
) -> set[tuple[int, int]]:
    return {
        (int(edge.ground_truth_source_id), int(edge.ground_truth_target_id))
        for edge in correspondence.edges
        if edge.officially_matched
        and edge.ground_truth_source_id is not None
        and edge.ground_truth_target_id is not None
    }


def _unmatched_prediction_edges(
    correspondence: OfficialAssociationCorrespondence,
) -> set[tuple[str, str]]:
    return {
        (edge.prediction_source_id, edge.prediction_target_id)
        for edge in correspondence.edges
        if not edge.officially_matched
    }


def build_transition_ledger(
    v19: OfficialAssociationCorrespondence,
    baseline: OfficialAssociationCorrespondence,
    ablation: OfficialAssociationCorrespondence,
    baseline_graph: LineageGraph,
    ablation_graph: LineageGraph,
) -> dict[str, Any]:
    v19_matched = _matched_gt_edges(v19)
    baseline_matched = _matched_gt_edges(baseline)
    ablation_matched = _matched_gt_edges(ablation)
    baseline_edge_ids = {
        (edge.source_id, edge.target_id) for edge in baseline_graph.edges
    }
    ablation_edge_ids = {
        (edge.source_id, edge.target_id) for edge in ablation_graph.edges
    }
    recovered = (v19_matched - baseline_matched) & ablation_matched
    displaced = baseline_matched - ablation_matched
    newly_credited = ablation_matched - baseline_matched
    newly_incorrect = (
        _unmatched_prediction_edges(ablation)
        & (ablation_edge_ids - baseline_edge_ids)
    )
    removed_incorrect = (
        _unmatched_prediction_edges(baseline)
        & (baseline_edge_ids - ablation_edge_ids)
    )
    return {
        "recovered_v19_credited_edges": [list(edge) for edge in sorted(recovered)],
        "displaced_v24_3_credited_edges": [list(edge) for edge in sorted(displaced)],
        "newly_credited_edges": [list(edge) for edge in sorted(newly_credited)],
        "newly_incorrect_edges": [list(edge) for edge in sorted(newly_incorrect)],
        "removed_incorrect_edges": [list(edge) for edge in sorted(removed_incorrect)],
        "added_prediction_edges": [
            list(edge) for edge in sorted(ablation_edge_ids - baseline_edge_ids)
        ],
        "removed_prediction_edges": [
            list(edge) for edge in sorted(baseline_edge_ids - ablation_edge_ids)
        ],
        "net_association_delta": len(newly_credited) - len(displaced),
        "net_incorrect_edge_delta": len(newly_incorrect) - len(removed_incorrect),
    }


def _correspondence_from_payload(payload: dict[str, Any]) -> OfficialAssociationCorrespondence:
    from atabey.evaluation.official_association_forensics import (
        OfficialEdgeCorrespondence,
        OfficialNodeCorrespondence,
    )

    return OfficialAssociationCorrespondence(
        nodes=tuple(OfficialNodeCorrespondence(**row) for row in payload["nodes"]),
        edges=tuple(OfficialEdgeCorrespondence(**row) for row in payload["edges"]),
    )


def _selection_subtypes(
    record: dict[str, Any],
    relink: LineageGraph,
) -> dict[tuple[int, int], str]:
    try:
        from scipy.spatial import cKDTree
    except ImportError as exc:
        raise RuntimeError("V26A requires the pinned SciPy cKDTree runtime") from exc

    nodes = {node.node_id: node for node in relink.detections}
    by_time: dict[int, list[Detection]] = {}
    for node in relink.detections:
        by_time.setdefault(node.t, []).append(node)
    for frame_nodes in by_time.values():
        frame_nodes.sort(key=lambda node: node.node_id)
    predecessor_by_node_id = {
        edge.target_id: nodes[edge.source_id] for edge in relink.edges
    }

    subtypes: dict[tuple[int, int], str] = {}
    for loss in record["v19_credited_v24_3_lost_edges"]:
        if loss["failure_class"] != "candidate_selection_ranking_failure":
            continue
        correct_targets = set(loss["matched_e016_target_ids"])
        forward_selected_correct = False
        for source_id in loss["matched_e016_source_ids"]:
            source = nodes[source_id]
            current = by_time.get(source.t + 1, [])
            if not current:
                continue
            predicted = _predicted_position(
                source, predecessor_by_node_id.get(source.node_id)
            )
            _, target_idx = cKDTree(
                [target.position_um for target in current]
            ).query(predicted, k=1)
            if current[int(target_idx)].node_id in correct_targets:
                forward_selected_correct = True
                break
        edge_id = (
            int(loss["ground_truth_source_id"]),
            int(loss["ground_truth_target_id"]),
        )
        subtypes[edge_id] = (
            "reverse_mutuality_conflict"
            if forward_selected_correct
            else "forward_prediction_ranking_loss"
        )
    return subtypes


def _metric_delta(
    baseline: OfficialTrackingResult,
    ablation: OfficialTrackingResult,
) -> dict[str, float | int | None]:
    fields = (
        "edge_tp",
        "edge_fp",
        "edge_fn",
        "edge_jaccard",
        "adjusted_edge_jaccard",
        "node_recall",
        "predicted_nodes",
        "total_node_ratio",
    )
    result: dict[str, float | int | None] = {}
    for field in fields:
        baseline_value = getattr(baseline, field)
        ablation_value = getattr(ablation, field)
        result[field] = (
            None
            if baseline_value is None or ablation_value is None
            else ablation_value - baseline_value
        )
    return result


def _loss_mechanisms(
    record: dict[str, Any],
    selection_subtypes: dict[tuple[int, int], str],
) -> dict[tuple[int, int], str]:
    mechanisms: dict[tuple[int, int], str] = {}
    for loss in record["v19_credited_v24_3_lost_edges"]:
        edge_id = (
            int(loss["ground_truth_source_id"]),
            int(loss["ground_truth_target_id"]),
        )
        mechanisms[edge_id] = selection_subtypes.get(
            edge_id, str(loss["failure_class"])
        )
    return mechanisms


def _pruning_behavior(
    relink: LineageGraph,
    v24_2: LineageGraph,
    v24_3: LineageGraph,
) -> dict[str, int]:
    return {
        "v24_2_removed_nodes": len(relink.detections) - len(v24_2.detections),
        "v24_2_removed_edges": len(relink.edges) - len(v24_2.edges),
        "v24_3_removed_nodes": len(v24_2.detections) - len(v24_3.detections),
        "v24_3_removed_edges": len(v24_2.edges) - len(v24_3.edges),
    }


def evaluate_interest_gate(
    sample_results: list[dict[str, Any]],
    aggregate_counts: Counter[str],
    gate: dict[str, Any],
) -> dict[str, Any]:
    forward_recoveries = aggregate_counts["forward_prediction_ranking_loss"]
    newly_incorrect = aggregate_counts["newly_incorrect_edges"]
    net_association_delta = sum(
        sample["transition_ledger"]["net_association_delta"]
        for sample in sample_results
    )
    net_incorrect_delta = sum(
        sample["transition_ledger"]["net_incorrect_edge_delta"]
        for sample in sample_results
    )
    adjusted_deltas = [
        sample["official_metric_delta"]["adjusted_edge_jaccard"]
        for sample in sample_results
        if sample["official_metric_delta"]["adjusted_edge_jaccard"] is not None
    ]
    worst_adjusted_delta = min(adjusted_deltas, default=None)
    collateral_ratio = (
        newly_incorrect / forward_recoveries
        if forward_recoveries
        else None
    )
    checks = {
        "minimum_forward_ranking_recoveries": (
            forward_recoveries >= gate["minimum_forward_ranking_recoveries"]
        ),
        "positive_net_association_delta": (
            net_association_delta > 0
            if gate["require_positive_net_association_delta"]
            else True
        ),
        "bounded_net_incorrect_edge_delta": (
            net_incorrect_delta <= gate["maximum_net_incorrect_edge_delta"]
        ),
        "bounded_new_incorrect_edge_ratio": (
            collateral_ratio is not None
            and collateral_ratio
            <= gate["maximum_new_incorrect_edges_per_forward_recovery"]
        ),
        "bounded_per_sample_adjusted_edge_regression": (
            worst_adjusted_delta is not None
            and worst_adjusted_delta
            >= -gate["maximum_per_sample_adjusted_edge_jaccard_regression"]
        ),
        "deterministic_replay": (
            all(sample["deterministic_replay"] for sample in sample_results)
            if gate["require_deterministic_replay"]
            else True
        ),
    }
    return {
        "checks": checks,
        "observed": {
            "forward_ranking_recoveries": forward_recoveries,
            "net_association_delta": net_association_delta,
            "net_incorrect_edge_delta": net_incorrect_delta,
            "new_incorrect_edges_per_forward_recovery": collateral_ratio,
            "worst_per_sample_adjusted_edge_jaccard_delta": worst_adjusted_delta,
        },
        "passed": all(checks.values()),
        "decision": (
            "INTERESTING_FOR_PREREGISTERED_INDEPENDENT_FOLLOWUP"
            if all(checks.values())
            else "NO_GO"
        ),
        "production_tuning_authorized": False,
    }


def _validate_contract(contract: dict[str, Any], archive_path: Path) -> list[str]:
    sample_ids = contract["cohort"]["sample_ids"]
    if len(sample_ids) != 16 or len(set(sample_ids)) != 16:
        raise RuntimeError("V26A cohort must contain 16 unique samples")
    archive = contract["frozen_v25_archive"]
    if archive_path.stat().st_size != archive["bytes"] or _sha256(archive_path) != archive["sha256"]:
        raise RuntimeError("V26A frozen V25 archive mismatch")
    for path, expected_hash in contract["sources"].values():
        if canonical_text_sha256(ROOT / path) != expected_hash:
            raise RuntimeError(f"V26A source hash mismatch: {path}")
    return sample_ids


def _read_record(archive: zipfile.ZipFile, sample_id: str) -> dict[str, Any]:
    name = f"run/samples/{sample_id}.json.gz"
    try:
        return json.loads(gzip.decompress(archive.read(name)))
    except KeyError as exc:
        raise RuntimeError(f"Missing V25 sample artifact: {sample_id}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the preregistered V26A forward step-ranking ablation."
    )
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument(
        "--v25-archive",
        type=Path,
        default=ROOT / "v25_upstream_forensics_outputs.zip",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "tests/fixtures/v26_a_forward_ranking_ablation.json",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("v26_a_forward_ranking"))
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    sample_ids = _validate_contract(contract, args.v25_archive)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_metrics: list[OfficialTrackingResult] = []
    ablation_metrics: list[OfficialTrackingResult] = []
    summaries: list[dict[str, Any]] = []

    with zipfile.ZipFile(args.v25_archive) as archive:
        for index, sample_id in enumerate(sample_ids, start=1):
            print(f"[{index}/16] {sample_id}: replaying", flush=True)
            record = _read_record(archive, sample_id)
            if record.get("sample_id") != sample_id:
                raise RuntimeError(f"V25 artifact identity mismatch for {sample_id}")
            relink = _reconstruct_frozen_relink(record)
            v24_2 = prune_interior_isolated_detections(relink)
            baseline = prune_interior_short_fragments(v24_2)
            for name, graph in (("relink", relink), ("v24_2", v24_2), ("v24_3", baseline)):
                expected = record["graph_signatures"][f"{name}_sha256"]
                if _graph_signature_sha256(graph) != expected:
                    raise RuntimeError(f"Frozen {name} replay mismatch for {sample_id}")

            frozen_detections = tuple(relink.detections)
            tracemalloc.start()
            started = time.perf_counter()
            ablation_relink = relink_detections_step_ranked(sample_id, frozen_detections)
            runtime_seconds = time.perf_counter() - started
            _, peak_python_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            replay = relink_detections_step_ranked(sample_id, frozen_detections)
            if tuple(relink.detections) != frozen_detections:
                raise RuntimeError(f"V26A mutated frozen detections for {sample_id}")
            if graph_signature(ablation_relink) != graph_signature(replay):
                raise RuntimeError(f"V26A replay is nondeterministic for {sample_id}")

            ablation_v24_2 = prune_interior_isolated_detections(ablation_relink)
            ablation = prune_interior_short_fragments(ablation_v24_2)
            ground_truth = read_geff_graph(args.train_dir / f"{sample_id}.geff")
            baseline_correspondence = _correspondence_from_payload(
                record["official_correspondence"]["v24_3"]
            )
            v19_correspondence = _correspondence_from_payload(
                record["official_correspondence"]["v19"]
            )
            ablation_correspondence = extract_official_association_correspondence(
                ablation, ground_truth
            )
            ledger = build_transition_ledger(
                v19_correspondence,
                baseline_correspondence,
                ablation_correspondence,
                baseline,
                ablation,
            )
            subtypes = _selection_subtypes(record, relink)
            recovered = {
                tuple(edge) for edge in ledger["recovered_v19_credited_edges"]
            }
            loss_mechanisms = _loss_mechanisms(record, subtypes)
            recovered_mechanisms = dict(
                sorted(
                    Counter(
                        loss_mechanisms[edge]
                        for edge in recovered
                        if edge in loss_mechanisms
                    ).items()
                )
            )
            baseline_metric = evaluate_official_tracking(baseline, ground_truth)
            ablation_metric = evaluate_official_tracking(ablation, ground_truth)
            baseline_metrics.append(baseline_metric)
            ablation_metrics.append(ablation_metric)
            sample_result = {
                "sample_id": sample_id,
                "transition_ledger": ledger,
                "recovered_mechanisms": recovered_mechanisms,
                "pruning_behavior": {
                    "baseline": _pruning_behavior(relink, v24_2, baseline),
                    "ablation": _pruning_behavior(
                        ablation_relink, ablation_v24_2, ablation
                    ),
                },
                "baseline_metric": asdict(baseline_metric),
                "ablation_metric": asdict(ablation_metric),
                "official_metric_delta": _metric_delta(baseline_metric, ablation_metric),
                "graph_signatures": {
                    "baseline_v24_3_sha256": _graph_signature_sha256(baseline),
                    "ablation_v24_3_sha256": _graph_signature_sha256(ablation),
                },
                "runtime_seconds": runtime_seconds,
                "peak_python_tracemalloc_bytes": peak_python_bytes,
                "deterministic_replay": True,
                "frozen_detection_count": len(frozen_detections),
                "production_tuning_authorized": False,
            }
            _atomic_gzip_json(
                args.output_dir / "samples" / f"{sample_id}.json.gz",
                sample_result,
            )
            summaries.append(sample_result)

    aggregate_counts = Counter()
    for sample in summaries:
        ledger = sample["transition_ledger"]
        for field in (
            "recovered_v19_credited_edges",
            "displaced_v24_3_credited_edges",
            "newly_credited_edges",
            "newly_incorrect_edges",
            "removed_incorrect_edges",
        ):
            aggregate_counts[field] += len(ledger[field])
        aggregate_counts.update(sample["recovered_mechanisms"])
    baseline_summary = summarize_official_tracking(baseline_metrics)
    ablation_summary = summarize_official_tracking(ablation_metrics)
    interest_gate = evaluate_interest_gate(
        summaries,
        aggregate_counts,
        contract["interest_gate"],
    )
    output = {
        "status": "V26A_INTERVENTION_SENSITIVITY_COMPLETE",
        "intervention": "forward_step_distance_ranking",
        "sample_count": len(summaries),
        "aggregate_edge_transitions": dict(sorted(aggregate_counts.items())),
        "baseline_official_summary": asdict(baseline_summary),
        "ablation_official_summary": asdict(ablation_summary),
        "sample_results": [
            {
                "sample_id": sample["sample_id"],
                "transition_counts": {
                    key: len(value)
                    for key, value in sample["transition_ledger"].items()
                    if isinstance(value, list)
                },
                "recovered_mechanisms": sample["recovered_mechanisms"],
                "pruning_behavior": sample["pruning_behavior"],
                "official_metric_delta": sample["official_metric_delta"],
                "runtime_seconds": sample["runtime_seconds"],
                "peak_python_tracemalloc_bytes": sample["peak_python_tracemalloc_bytes"],
            }
            for sample in summaries
        ],
        "deterministic_replay": all(sample["deterministic_replay"] for sample in summaries),
        "interest_gate": interest_gate,
        "production_tuning_authorized": False,
        "submission_authorized": False,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()