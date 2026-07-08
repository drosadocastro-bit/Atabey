from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from atabey.io.geff_reader import GroundTruthNode, read_geff_graph
from atabey.tracking.kinematic_recovery import KinematicRecoverySettings

try:
    from run_hybrid_submission import build_graph_cfar_sidelobe
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_hybrid_submission import build_graph_cfar_sidelobe

try:
    from run_v16_kinematic_validation import load_cfar_validation_cohorts, validate_expected_cohort_sizes
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_v16_kinematic_validation import load_cfar_validation_cohorts, validate_expected_cohort_sizes


STRICT_RADIUS_UM = 7.0
RELAXED_RADIUS_UM = 14.0


@dataclass(frozen=True)
class GTSearchSummary:
    nearest_same_frame_distance_um: float | None
    same_frame_within_strict: int
    same_frame_within_relaxed: int
    nearest_adjacent_frame_distance_um: float | None
    adjacent_frame_within_strict: int
    nearby_gt_ids_strict: list[int]


@dataclass(frozen=True)
class ForensicRecord:
    sample_id: str
    source_id: str
    frame_t: int
    category: str
    detail: str
    source_present_in_graph: bool
    expected_gt_target_id: int | None
    expected_target_from: str | None
    source_neighbors_within_radius: int
    greedy_target_id: str | None
    global_target_id: str | None
    changed_decision: bool
    source_search: GTSearchSummary | None
    greedy_search: GTSearchSummary | None
    global_search: GTSearchSummary | None
    source_gt_outgoing_count: int | None
    source_gt_incoming_count: int | None
    sample_build_seconds: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V18 coverage forensics for unmapped/unevaluable disagreement records.")
    parser.add_argument("--train-dir", default="train")
    parser.add_argument("--scan-json", default="submissions/cfar_bounded_scan_fulltrain.json")
    parser.add_argument("--v17-validate-json", default="submissions/v17_hard_exclusion_validate.json")
    parser.add_argument("--disagreement-json", default="submissions/v18_disagreement_subset_validate.json")
    parser.add_argument("--disagreement-jsonl", default="submissions/v18_disagreement_subset_records.jsonl")
    parser.add_argument("--output-json", default="submissions/v18_coverage_forensics.json")
    return parser.parse_args()


def _distance_um_position(position_left: tuple[float, float, float], position_right: tuple[float, float, float]) -> float:
    return float(np.linalg.norm(np.array(position_left, dtype=float) - np.array(position_right, dtype=float)))


def _search_gt(node: Any | None, gt_nodes_by_t: dict[int, list[GroundTruthNode]]) -> GTSearchSummary | None:
    if node is None:
        return None

    same_nodes = gt_nodes_by_t.get(int(node.t), [])
    adjacent_nodes = gt_nodes_by_t.get(int(node.t) + 1, [])
    if not same_nodes and not adjacent_nodes:
        return GTSearchSummary(
            nearest_same_frame_distance_um=None,
            same_frame_within_strict=0,
            same_frame_within_relaxed=0,
            nearest_adjacent_frame_distance_um=None,
            adjacent_frame_within_strict=0,
            nearby_gt_ids_strict=[],
        )

    same_distances = [
        (_distance_um_position(node.position_um, gt_node.position_um), int(gt_node.node_id))
        for gt_node in same_nodes
    ]
    adjacent_distances = [
        (_distance_um_position(node.position_um, gt_node.position_um), int(gt_node.node_id))
        for gt_node in adjacent_nodes
    ]

    same_strict_ids = [gt_id for dist, gt_id in same_distances if dist <= STRICT_RADIUS_UM]
    nearest_same = min((dist for dist, _gt_id in same_distances), default=None)
    nearest_adjacent = min((dist for dist, _gt_id in adjacent_distances), default=None)
    return GTSearchSummary(
        nearest_same_frame_distance_um=float(nearest_same) if nearest_same is not None else None,
        same_frame_within_strict=len(same_strict_ids),
        same_frame_within_relaxed=sum(1 for dist, _gt_id in same_distances if dist <= RELAXED_RADIUS_UM),
        nearest_adjacent_frame_distance_um=float(nearest_adjacent) if nearest_adjacent is not None else None,
        adjacent_frame_within_strict=sum(1 for dist, _gt_id in adjacent_distances if dist <= STRICT_RADIUS_UM),
        nearby_gt_ids_strict=same_strict_ids[:10],
    )


def _build_graph_support(
    *,
    train_dir: Path,
    sample_id: str,
    metadata: dict[str, Any],
    settings: KinematicRecoverySettings,
) -> tuple[Any, dict[str, Any], dict[int, list[GroundTruthNode]], dict[int, int], dict[int, int], float]:
    sample_path = train_dir / f"{sample_id}.zarr"
    gt_graph = read_geff_graph(train_dir / f"{sample_id}.geff")
    build_start = time.perf_counter()
    graph, _fallbacks, _telemetry = build_graph_cfar_sidelobe(
        sample_path=sample_path,
        threshold=float(metadata["cfar_threshold"]),
        cfar_training_radius_voxels=tuple(metadata["cfar_training_radius_voxels"]),
        cfar_guard_radius_voxels=tuple(metadata["cfar_guard_radius_voxels"]),
        cfar_k_sigma=float(metadata["cfar_k_sigma"]),
        sidelobe_radius_voxels=tuple(metadata["sidelobe_radius_voxels"]),
        sidelobe_floor_ratio=float(metadata["sidelobe_floor_ratio"]),
        max_detections_per_timepoint=(
            int(metadata["max_detections_per_timepoint"]) if metadata["max_detections_per_timepoint"] is not None else None
        ),
        link_strategy=str(metadata["cfar_link_strategy"]),
        max_link_distance_um=float(metadata["cfar_max_link_distance_um"]),
        max_timepoints=int(metadata["max_timepoints"]),
        kinematic_recovery_enabled=True,
        kinematic_recovery_settings=settings,
        return_kinematic_telemetry=True,
    )
    build_seconds = float(time.perf_counter() - build_start)

    detection_by_id = {detection.node_id: detection for detection in graph.detections}
    gt_nodes_by_t: dict[int, list[GroundTruthNode]] = {}
    gt_outgoing_count: dict[int, int] = {}
    gt_incoming_count: dict[int, int] = {}
    for node in gt_graph.nodes:
        gt_nodes_by_t.setdefault(int(node.t), []).append(node)
    for src_id, tgt_id in gt_graph.edges:
        gt_outgoing_count[int(src_id)] = gt_outgoing_count.get(int(src_id), 0) + 1
        gt_incoming_count[int(tgt_id)] = gt_incoming_count.get(int(tgt_id), 0) + 1
    return detection_by_id, gt_nodes_by_t, gt_outgoing_count, gt_incoming_count, build_seconds


def _classify_record(
    *,
    row: dict[str, Any],
    source_node: Any | None,
    greedy_node: Any | None,
    global_node: Any | None,
    source_search: GTSearchSummary | None,
    greedy_search: GTSearchSummary | None,
    global_search: GTSearchSummary | None,
    source_gt_outgoing_count: int | None,
    source_gt_incoming_count: int | None,
) -> tuple[str, str]:
    if not bool(row.get("source_present_in_graph", False)) or source_node is None:
        return "structural_incomplete", "source_missing_from_graph"

    if row.get("expected_gt_target_id") is not None:
        return "mapped_but_target_unclaimed", "expected_gt_target_present_but_candidate_unmapped"

    if source_search is None:
        return "structural_incomplete", "source_search_missing"

    same_strict = int(source_search.same_frame_within_strict)
    same_relaxed = int(source_search.same_frame_within_relaxed)
    adjacent_strict = int(source_search.adjacent_frame_within_strict)

    candidate_strict_hits = 0
    candidate_relaxed_only = 0
    candidate_adjacent_hits = 0
    candidate_ambiguous_hits = 0
    for search in [greedy_search, global_search]:
        if search is None:
            continue
        if int(search.same_frame_within_strict) > 0:
            candidate_strict_hits += 1
        elif int(search.same_frame_within_relaxed) > 0:
            candidate_relaxed_only += 1
        if int(search.adjacent_frame_within_strict) > 0:
            candidate_adjacent_hits += 1
        if int(search.same_frame_within_strict) > 1:
            candidate_ambiguous_hits += 1

    if same_strict == 0 and candidate_strict_hits == 0 and same_relaxed == 0 and candidate_relaxed_only == 0 and adjacent_strict == 0 and candidate_adjacent_hits == 0:
        return "no_gt_nearby", "no_gt_within_relaxed_radius_same_or_adjacent_frame"

    if same_strict > 1 or candidate_ambiguous_hits > 0:
        return "ambiguous_identity_region", "multiple_gt_nodes_within_strict_radius"

    if (source_gt_outgoing_count or 0) > 1 or (source_gt_incoming_count or 0) > 1:
        return "ambiguous_identity_region", "gt_branching_or_merging_structure"

    if same_strict > 0 or candidate_strict_hits > 0:
        return "matching_lookup_failed_nearby_gt", "nearby_gt_within_strict_radius_not_mapped_by_current_lookup"

    if same_relaxed > 0 or candidate_relaxed_only > 0:
        return "matching_lookup_failed_nearby_gt", "nearby_gt_only_within_relaxed_radius_radius_mismatch_candidate"

    if adjacent_strict > 0 or candidate_adjacent_hits > 0:
        return "matching_lookup_failed_nearby_gt", "nearby_gt_only_in_adjacent_frame_frame_alignment_candidate"

    return "structural_incomplete", "fell_through_classifier"


def main() -> None:
    args = _parse_args()
    train_dir = Path(args.train_dir)
    scan_json = Path(args.scan_json)
    v17_validate_json = Path(args.v17_validate_json)
    disagreement_json = Path(args.disagreement_json)
    disagreement_jsonl = Path(args.disagreement_jsonl)
    output_json = Path(args.output_json)

    cohorts = load_cfar_validation_cohorts(scan_json)
    validate_expected_cohort_sizes(cohorts)

    v17_payload = json.loads(v17_validate_json.read_text(encoding="utf-8"))
    disagreement_payload = json.loads(disagreement_json.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in disagreement_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]

    unevaluable_rows = [row for row in rows if row.get("shadow_outcome") == "unmapped_or_unevaluable"]
    sample_ids = sorted({str(row["sample_id"]) for row in unevaluable_rows})

    metadata = dict(v17_payload["metadata"])
    kinematic_settings = KinematicRecoverySettings(**metadata["kinematic_recovery_settings"])

    support_by_sample: dict[str, tuple[dict[str, Any], dict[int, list[GroundTruthNode]], dict[int, int], dict[int, int], float]] = {}
    for idx, sample_id in enumerate(sample_ids, start=1):
        print(f"[forensics {idx}/{len(sample_ids)}] sample={sample_id}", flush=True)
        support_by_sample[sample_id] = _build_graph_support(
            train_dir=train_dir,
            sample_id=sample_id,
            metadata=metadata,
            settings=kinematic_settings,
        )

    forensic_records: list[ForensicRecord] = []
    by_category: dict[str, list[ForensicRecord]] = {}

    for row in unevaluable_rows:
        sample_id = str(row["sample_id"])
        detection_by_id, gt_nodes_by_t, gt_outgoing_count, gt_incoming_count, build_seconds = support_by_sample[sample_id]
        source_node = detection_by_id.get(str(row["source_id"]))
        greedy_node = detection_by_id.get(str(row["greedy_target_id"])) if row.get("greedy_target_id") is not None else None
        global_node = detection_by_id.get(str(row["global_target_id"])) if row.get("global_target_id") is not None else None

        source_search = _search_gt(source_node, gt_nodes_by_t)
        greedy_search = _search_gt(greedy_node, gt_nodes_by_t)
        global_search = _search_gt(global_node, gt_nodes_by_t)

        source_gt_id = row.get("source_gt_id")
        outgoing_count = gt_outgoing_count.get(int(source_gt_id), 0) if source_gt_id is not None else None
        incoming_count = gt_incoming_count.get(int(source_gt_id), 0) if source_gt_id is not None else None

        category, detail = _classify_record(
            row=row,
            source_node=source_node,
            greedy_node=greedy_node,
            global_node=global_node,
            source_search=source_search,
            greedy_search=greedy_search,
            global_search=global_search,
            source_gt_outgoing_count=outgoing_count,
            source_gt_incoming_count=incoming_count,
        )

        record = ForensicRecord(
            sample_id=sample_id,
            source_id=str(row["source_id"]),
            frame_t=int(row["frame_t"]),
            category=category,
            detail=detail,
            source_present_in_graph=bool(row.get("source_present_in_graph", False)),
            expected_gt_target_id=(int(row["expected_gt_target_id"]) if row.get("expected_gt_target_id") is not None else None),
            expected_target_from=row.get("expected_target_from"),
            source_neighbors_within_radius=int(row.get("source_neighbors_within_radius", 0)),
            greedy_target_id=row.get("greedy_target_id"),
            global_target_id=row.get("global_target_id"),
            changed_decision=bool(row.get("changed_decision", False)),
            source_search=source_search,
            greedy_search=greedy_search,
            global_search=global_search,
            source_gt_outgoing_count=outgoing_count,
            source_gt_incoming_count=incoming_count,
            sample_build_seconds=build_seconds,
        )
        forensic_records.append(record)
        by_category.setdefault(category, []).append(record)

    total = len(forensic_records)
    category_summary = {
        category: {
            "count": len(items),
            "percentage": (float(len(items)) / float(total)) if total else 0.0,
            "detail_counts": {
                detail: sum(1 for item in items if item.detail == detail)
                for detail in sorted({item.detail for item in items})
            },
        }
        for category, items in sorted(by_category.items())
    }

    examples = {
        category: [asdict(item) for item in items[:10]]
        for category, items in sorted(by_category.items())
    }

    recommendation = ""
    if category_summary.get("no_gt_nearby", {}).get("count", 0) >= max(category_summary.get("matching_lookup_failed_nearby_gt", {}).get("count", 0), category_summary.get("ambiguous_identity_region", {}).get("count", 0)):
        recommendation = "Sparse GT / coverage limitation dominates; V18 has likely reached its evidentiary ceiling on this dataset and should remain shadow-only."
    else:
        recommendation = "Matching / lookup failure is non-trivial; a targeted coverage-fix pass is justified before closing V18."

    output_payload = {
        "metadata": {
            "experiment": "v18_coverage_forensics",
            "objective": "classify why disagreement-first V18 records are unmapped_or_unevaluable",
            "strict_match_radius_um": STRICT_RADIUS_UM,
            "relaxed_match_radius_um": RELAXED_RADIUS_UM,
            "input_unevaluable_records": total,
            "input_disagreement_summary": disagreement_payload.get("decision_summary", {}),
            "samples_profiled": sample_ids,
            "cohort": disagreement_payload.get("metadata", {}).get("cohort"),
        },
        "category_summary": category_summary,
        "examples": examples,
        "runtime": {
            "mean_graph_rebuild_seconds": float(mean(item.sample_build_seconds for item in forensic_records)) if forensic_records else 0.0,
            "samples_rebuilt": len(sample_ids),
        },
        "recommendation": recommendation,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(json.dumps({"output_json": str(output_json), "unevaluable_records": total, "category_summary": category_summary}, indent=2), flush=True)


if __name__ == "__main__":
    main()
