from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median

import numpy as np

from atabey.evaluation.sparse_ground_truth import match_sparse_centroids
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.kinematic_recovery import KinematicRecoverySettings
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints

try:
    from run_hybrid_submission import (
        DEFAULT_GUARDRAIL_SETTINGS,
        _cfar_background_stats_box,
        _should_use_cfar_route,
        _sample_id_from_path,
        choose_settings_for_sample,
        threshold_local_maxima,
        threshold_local_maxima_cfar_sidelobe,
        build_graph_cfar_sidelobe,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_hybrid_submission import (
        DEFAULT_GUARDRAIL_SETTINGS,
        _cfar_background_stats_box,
        _should_use_cfar_route,
        _sample_id_from_path,
        choose_settings_for_sample,
        threshold_local_maxima,
        threshold_local_maxima_cfar_sidelobe,
        build_graph_cfar_sidelobe,
    )

try:
    from run_v16_kinematic_validation import load_cfar_validation_cohorts
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_v16_kinematic_validation import load_cfar_validation_cohorts


OUTCOME_RANK = {
    "regressed": 0,
    "unchanged": 1,
    "fixed": 2,
    "unmapped": -1,
}


@dataclass(frozen=True)
class GateTraceRecord:
    sample_id: str
    source_id: str
    frame_t: int
    singleton_has_direct_candidate: bool
    full_context_has_direct_candidate: bool
    disagrees: bool
    track_length_edges: int
    has_predecessor: bool
    nearest_source_distance_um: float | None
    second_source_distance_um: float | None
    source_neighbors_within_radius: int


@dataclass(frozen=True)
class DisagreementOutcomeRecord:
    sample_id: str
    source_id: str
    frame_t: int
    singleton_has_direct_candidate: bool
    full_context_has_direct_candidate: bool
    gt_source_id: int | None
    gt_target_id: int | None
    mapped_from_v16_regression: bool
    outcome_v17: str
    outcome_v17_1: str
    preferred_check: str
    nearest_source_distance_um: float | None
    second_source_distance_um: float | None
    source_neighbors_within_radius: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Per-source gate decision trace audit for V17 singleton vs full-context checks.")
    parser.add_argument("--train-dir", default="train", help="Train directory containing .zarr/.geff pairs.")
    parser.add_argument("--scan-json", default="submissions/cfar_bounded_scan_fulltrain.json", help="Scan JSON with routed CFAR cohort.")
    parser.add_argument("--v17-json", default="submissions/v17_hard_exclusion_validate.json", help="V17 validation artifact.")
    parser.add_argument("--v17-1-json", default="submissions/v17_1_criteria_alignment_validate.json", help="V17.1 validation artifact.")
    parser.add_argument("--v16-diagnostic-json", default="submissions/v16_diagnostic_root_cause.json", help="V16 diagnostic root-cause artifact.")
    parser.add_argument("--output-json", default="submissions/v17_gate_trace_audit.json", help="Audit output JSON path.")
    parser.add_argument("--output-jsonl", default="submissions/v17_gate_trace_records.jsonl", help="Per-source trace JSONL path.")
    return parser.parse_args()


def _candidate_stats(source_position: np.ndarray, current_positions: np.ndarray, max_link_distance_um: float) -> tuple[float | None, float | None, int]:
    if current_positions.size == 0:
        return None, None, 0
    distances = np.linalg.norm(current_positions - source_position, axis=1)
    distances.sort()
    nearest = float(distances[0]) if distances.size >= 1 else None
    second = float(distances[1]) if distances.size >= 2 else None
    count = int(np.count_nonzero(distances <= float(max_link_distance_um)))
    return nearest, second, count


def _edge_outcome(
    *,
    gt_source_id: int,
    gt_target_id: int,
    off_match: dict[int, str],
    off_edges: set[tuple[str, str]],
    run_match: dict[int, str],
    run_edges: set[tuple[str, str]],
) -> str:
    off_src = off_match.get(int(gt_source_id))
    off_tgt = off_match.get(int(gt_target_id))
    run_src = run_match.get(int(gt_source_id))
    run_tgt = run_match.get(int(gt_target_id))

    off_present = off_src is not None and off_tgt is not None and (off_src, off_tgt) in off_edges
    run_present = run_src is not None and run_tgt is not None and (run_src, run_tgt) in run_edges

    if (not off_present) and run_present:
        return "fixed"
    if off_present and (not run_present):
        return "regressed"
    return "unchanged"


def _resolve_gt_edge(
    *,
    sample_id: str,
    source_id: str,
    frame_t: int,
    v16_by_source: dict[str, dict[str, list[dict[str, object]]]],
    off_pred_to_gt: dict[str, int],
    gt_outgoing_edges: dict[str, dict[int, list[tuple[int, int]]]],
) -> tuple[int | None, int | None, bool]:
    candidates = v16_by_source.get(sample_id, {}).get(source_id, [])
    if candidates:
        frame_candidates = [row for row in candidates if int(row["source_t"]) == int(frame_t)]
        chosen = frame_candidates[0] if frame_candidates else candidates[0]
        return int(chosen["gt_source_id"]), int(chosen["gt_target_id"]), True

    gt_source = off_pred_to_gt.get(source_id)
    if gt_source is None:
        return None, None, False
    outgoing = gt_outgoing_edges.get(sample_id, {}).get(int(gt_source), [])
    if not outgoing:
        return None, None, False

    # Prefer adjacent gt edge at t -> t+1, then fallback to first outgoing.
    adjacent = [edge for edge in outgoing if int(edge[0]) == int(frame_t) + 1]
    if adjacent:
        return int(gt_source), int(adjacent[0][1]), False
    return int(gt_source), int(outgoing[0][1]), False


def _build_gt_outgoing_index(train_dir: Path, sample_ids: list[str]) -> dict[str, dict[int, list[tuple[int, int]]]]:
    index: dict[str, dict[int, list[tuple[int, int]]]] = {}
    for sample_id in sample_ids:
        gt_graph = read_geff_graph(train_dir / f"{sample_id}.geff")
        t_by_node = {int(node.node_id): int(node.t) for node in gt_graph.nodes}
        outgoing: dict[int, list[tuple[int, int]]] = {}
        for source_id_raw, target_id_raw in gt_graph.edges:
            source_id = int(source_id_raw)
            target_id = int(target_id_raw)
            outgoing.setdefault(source_id, []).append((t_by_node.get(target_id, -1), target_id))
        index[sample_id] = outgoing
    return index


def _build_v16_source_index(v16_diagnostic_payload: dict[str, object]) -> dict[str, dict[str, list[dict[str, object]]]]:
    by_source: dict[str, dict[str, list[dict[str, object]]]] = {}
    for sample_id, payload in v16_diagnostic_payload["per_sample"].items():
        sample_index: dict[str, list[dict[str, object]]] = {}
        for row in payload.get("regressed_edges", []):
            pred_source_off = str(row.get("pred_source_off"))
            sample_index.setdefault(pred_source_off, []).append(row)
        by_source[str(sample_id)] = sample_index
    return by_source


def _build_graph_and_match(
    *,
    sample_path: Path,
    gt_graph,
    metadata: dict[str, object],
    kinematic_enabled: bool,
) -> tuple[set[tuple[str, str]], dict[int, str], dict[str, int]]:
    graph, _ = build_graph_cfar_sidelobe(
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
        kinematic_recovery_enabled=bool(kinematic_enabled),
        kinematic_recovery_settings=KinematicRecoverySettings(**metadata["kinematic_recovery_settings"]),
    )
    edge_set = {(edge.source_id, edge.target_id) for edge in graph.edges}
    match_rows = [
        row
        for row in match_sparse_centroids(graph, gt_graph, radius_um=7.0)
        if row.matched and row.prediction_node_id is not None
    ]
    gt_to_pred = {int(row.ground_truth_node_id): str(row.prediction_node_id) for row in match_rows}
    pred_to_gt = {str(row.prediction_node_id): int(row.ground_truth_node_id) for row in match_rows}
    return edge_set, gt_to_pred, pred_to_gt


def main() -> None:
    args = _parse_args()
    train_dir = Path(args.train_dir)
    scan_json = Path(args.scan_json)
    v17_json = Path(args.v17_json)
    v17_1_json = Path(args.v17_1_json)
    v16_diagnostic_json = Path(args.v16_diagnostic_json)
    output_json = Path(args.output_json)
    output_jsonl = Path(args.output_jsonl)

    cohorts = load_cfar_validation_cohorts(scan_json)
    sample_ids = list(cohorts.routed_cfar_66)

    v17_report = json.loads(v17_json.read_text(encoding="utf-8"))
    v17_1_report = json.loads(v17_1_json.read_text(encoding="utf-8"))
    v16_diag = json.loads(v16_diagnostic_json.read_text(encoding="utf-8"))

    v17_meta = v17_report["metadata"]
    v17_1_meta = v17_1_report["metadata"]

    max_timepoints = int(v17_meta["max_timepoints"])
    cfar_threshold = float(v17_meta["cfar_threshold"])
    cfar_training_radius = tuple(v17_meta["cfar_training_radius_voxels"])
    cfar_guard_radius = tuple(v17_meta["cfar_guard_radius_voxels"])
    cfar_k_sigma = float(v17_meta["cfar_k_sigma"])
    sidelobe_radius = tuple(v17_meta["sidelobe_radius_voxels"])
    sidelobe_floor = float(v17_meta["sidelobe_floor_ratio"])
    max_detections_per_timepoint = (
        int(v17_meta["max_detections_per_timepoint"]) if v17_meta["max_detections_per_timepoint"] is not None else None
    )
    link_strategy = str(v17_meta["cfar_link_strategy"])
    max_link_distance_um = float(v17_meta["cfar_max_link_distance_um"])
    cfar_route_policy = str(v17_meta["cfar_route_policy"])
    guardrail_spike_multiplier = float(DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier)
    guardrail_min_history = int(DEFAULT_GUARDRAIL_SETTINGS.min_history)
    guardrail_history_window = int(DEFAULT_GUARDRAIL_SETTINGS.history_window)
    guardrail_min_absolute_count = int(DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count)
    guardrail_fallback_threshold = float(DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold)
    guardrail_fallback_max_detections = max_detections_per_timepoint

    v16_by_source = _build_v16_source_index(v16_diag)
    gt_outgoing_edges = _build_gt_outgoing_index(train_dir, sample_ids)

    trace_records: list[GateTraceRecord] = []

    for idx, sample_id in enumerate(sample_ids, start=1):
        print(f"[trace {idx}/{len(sample_ids)}] sample={sample_id}", flush=True)
        sample_path = train_dir / f"{sample_id}.zarr"
        profile, adaptive_settings = choose_settings_for_sample(sample_path)
        if not _should_use_cfar_route(profile=profile, adaptive_detector=adaptive_settings.detector, cfar_route_policy=cfar_route_policy):
            continue

        array = open_competition_array(sample_path)
        total_timepoints = min(int(array.shape[0]), max_timepoints)
        previous = []
        detections_by_node_id = {}
        predecessor_by_node_id = {}
        track_length_by_node_id = {}
        recent_counts: list[int] = []

        for t in range(total_timepoints):
            volume = read_timepoint(array, t)
            current = threshold_local_maxima_cfar_sidelobe(
                _sample_id_from_path(sample_path),
                t,
                volume,
                threshold=cfar_threshold,
                min_distance_voxels=(1, 5, 5),
                max_detections=max_detections_per_timepoint,
                cfar_training_radius_voxels=cfar_training_radius,
                cfar_guard_radius_voxels=cfar_guard_radius,
                cfar_k_sigma=cfar_k_sigma,
                sidelobe_radius_voxels=sidelobe_radius,
                sidelobe_floor_ratio=sidelobe_floor,
            )

            use_guardrail = False
            if len(recent_counts) >= guardrail_min_history:
                recent_window = recent_counts[-guardrail_history_window:]
                baseline_count = float(median(recent_window))
                spike_limit = max(
                    guardrail_min_absolute_count,
                    int(round(baseline_count * guardrail_spike_multiplier)),
                )
                use_guardrail = len(current) > spike_limit

            if use_guardrail:
                current = threshold_local_maxima(
                    _sample_id_from_path(sample_path),
                    t,
                    volume,
                    threshold=guardrail_fallback_threshold,
                    min_distance_voxels=(1, 5, 5),
                    max_detections=guardrail_fallback_max_detections,
                )

            recent_counts.append(len(current))

            for detection in current:
                detections_by_node_id[detection.node_id] = detection

            adjacent_edges = link_adjacent_timepoints(
                previous,
                current,
                max_link_distance_um,
                strategy=link_strategy,
                predecessor_by_node_id=predecessor_by_node_id,
            )

            for edge in adjacent_edges:
                predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
                track_length_by_node_id[edge.target_id] = track_length_by_node_id.get(edge.source_id, 0) + 1

            matched_source_ids = {edge.source_id for edge in adjacent_edges}
            unmatched_previous = [d for d in previous if d.node_id not in matched_source_ids]
            full_edges = link_adjacent_timepoints(
                unmatched_previous,
                current,
                max_link_distance_um,
                strategy=link_strategy,
                predecessor_by_node_id=predecessor_by_node_id,
            )
            full_source_ids = {edge.source_id for edge in full_edges}
            current_positions = np.array([np.array(d.position_um, dtype=float) for d in current], dtype=float) if current else np.empty((0, 3), dtype=float)

            for source in previous:
                if source.node_id in matched_source_ids:
                    continue
                predecessor = predecessor_by_node_id.get(source.node_id)
                if predecessor is None:
                    continue
                track_len = int(track_length_by_node_id.get(source.node_id, 0))
                if track_len < int(v17_meta["kinematic_recovery_settings"]["min_track_length_edges"]):
                    continue

                singleton_edges = link_adjacent_timepoints(
                    [source],
                    current,
                    max_link_distance_um,
                    strategy=link_strategy,
                    predecessor_by_node_id={source.node_id: predecessor},
                )
                singleton_has = bool(singleton_edges)
                full_has = source.node_id in full_source_ids
                source_position = np.array(source.position_um, dtype=float)
                nearest, second, count_neighbors = _candidate_stats(source_position, current_positions, max_link_distance_um)

                trace_records.append(
                    GateTraceRecord(
                        sample_id=str(sample_id),
                        source_id=str(source.node_id),
                        frame_t=int(source.t),
                        singleton_has_direct_candidate=bool(singleton_has),
                        full_context_has_direct_candidate=bool(full_has),
                        disagrees=bool(singleton_has != full_has),
                        track_length_edges=track_len,
                        has_predecessor=True,
                        nearest_source_distance_um=nearest,
                        second_source_distance_um=second,
                        source_neighbors_within_radius=count_neighbors,
                    )
                )

            previous = current

    disagreements = [row for row in trace_records if row.disagrees]
    disagreement_samples = sorted({row.sample_id for row in disagreements})

    graph_cache = {}
    disagreement_outcomes: list[DisagreementOutcomeRecord] = []

    for idx, sample_id in enumerate(disagreement_samples, start=1):
        print(f"[outcome {idx}/{len(disagreement_samples)}] sample={sample_id}", flush=True)
        sample_path = train_dir / f"{sample_id}.zarr"
        gt_graph = read_geff_graph(train_dir / f"{sample_id}.geff")

        off_edges, off_match, off_pred_to_gt = _build_graph_and_match(
            sample_path=sample_path,
            gt_graph=gt_graph,
            metadata=v17_meta,
            kinematic_enabled=False,
        )
        v17_edges, v17_match, _v17_pred_to_gt = _build_graph_and_match(
            sample_path=sample_path,
            gt_graph=gt_graph,
            metadata=v17_meta,
            kinematic_enabled=True,
        )
        v17_1_edges, v17_1_match, _v17_1_pred_to_gt = _build_graph_and_match(
            sample_path=sample_path,
            gt_graph=gt_graph,
            metadata=v17_1_meta,
            kinematic_enabled=True,
        )
        graph_cache[sample_id] = {
            "off_edges": off_edges,
            "off_match": off_match,
            "off_pred_to_gt": off_pred_to_gt,
            "v17_edges": v17_edges,
            "v17_match": v17_match,
            "v17_1_edges": v17_1_edges,
            "v17_1_match": v17_1_match,
        }

    for row in disagreements:
        cache = graph_cache[row.sample_id]
        gt_source_id, gt_target_id, mapped_from_v16 = _resolve_gt_edge(
            sample_id=row.sample_id,
            source_id=row.source_id,
            frame_t=row.frame_t,
            v16_by_source=v16_by_source,
            off_pred_to_gt=cache["off_pred_to_gt"],
            gt_outgoing_edges=gt_outgoing_edges,
        )

        if gt_source_id is None or gt_target_id is None:
            outcome_v17 = "unmapped"
            outcome_v17_1 = "unmapped"
            preferred_check = "unknown"
        else:
            outcome_v17 = _edge_outcome(
                gt_source_id=gt_source_id,
                gt_target_id=gt_target_id,
                off_match=cache["off_match"],
                off_edges=cache["off_edges"],
                run_match=cache["v17_match"],
                run_edges=cache["v17_edges"],
            )
            outcome_v17_1 = _edge_outcome(
                gt_source_id=gt_source_id,
                gt_target_id=gt_target_id,
                off_match=cache["off_match"],
                off_edges=cache["off_edges"],
                run_match=cache["v17_1_match"],
                run_edges=cache["v17_1_edges"],
            )

            rank_v17 = OUTCOME_RANK.get(outcome_v17, -1)
            rank_v17_1 = OUTCOME_RANK.get(outcome_v17_1, -1)
            if rank_v17 > rank_v17_1:
                preferred_check = "singleton"
            elif rank_v17_1 > rank_v17:
                preferred_check = "full_context"
            else:
                preferred_check = "tie"

        disagreement_outcomes.append(
            DisagreementOutcomeRecord(
                sample_id=row.sample_id,
                source_id=row.source_id,
                frame_t=row.frame_t,
                singleton_has_direct_candidate=row.singleton_has_direct_candidate,
                full_context_has_direct_candidate=row.full_context_has_direct_candidate,
                gt_source_id=gt_source_id,
                gt_target_id=gt_target_id,
                mapped_from_v16_regression=bool(mapped_from_v16),
                outcome_v17=outcome_v17,
                outcome_v17_1=outcome_v17_1,
                preferred_check=preferred_check,
                nearest_source_distance_um=row.nearest_source_distance_um,
                second_source_distance_um=row.second_source_distance_um,
                source_neighbors_within_radius=row.source_neighbors_within_radius,
            )
        )

    dense_threshold = 3
    all_neighbor_counts = [row.source_neighbors_within_radius for row in trace_records]
    disagreement_neighbor_counts = [row.source_neighbors_within_radius for row in disagreements]

    disagreement_count = len(disagreements)
    considered_count = len(trace_records)
    disagreement_rate = 0.0 if considered_count == 0 else disagreement_count / considered_count

    dense_disagreements = [row for row in disagreements if row.source_neighbors_within_radius >= dense_threshold]
    sparse_disagreements = [row for row in disagreements if row.source_neighbors_within_radius < dense_threshold]

    mapped_outcomes = [row for row in disagreement_outcomes if row.outcome_v17 != "unmapped" and row.outcome_v17_1 != "unmapped"]
    singleton_better = sum(1 for row in mapped_outcomes if row.preferred_check == "singleton")
    full_better = sum(1 for row in mapped_outcomes if row.preferred_check == "full_context")
    ties = sum(1 for row in mapped_outcomes if row.preferred_check == "tie")

    disagreements_sorted = sorted(
        [
            row
            for row in disagreement_outcomes
            if row.preferred_check in {"singleton", "full_context"}
        ],
        key=lambda item: (
            0 if item.preferred_check == "singleton" else 1,
            item.sample_id,
            item.frame_t,
        ),
    )
    example_rows = disagreements_sorted[:3]

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    with output_jsonl.open("w", encoding="utf-8") as handle:
        for row in trace_records:
            handle.write(json.dumps(asdict(row), ensure_ascii=True) + "\n")

    summary = {
        "inputs": {
            "scan_json": str(scan_json),
            "v17_json": str(v17_json),
            "v17_1_json": str(v17_1_json),
            "v16_diagnostic_json": str(v16_diagnostic_json),
            "train_dir": str(train_dir),
            "cohort_size": len(sample_ids),
        },
        "counts": {
            "considered_sources": considered_count,
            "disagreement_sources": disagreement_count,
            "disagreement_rate": disagreement_rate,
            "dense_threshold_neighbors": dense_threshold,
            "dense_disagreements": len(dense_disagreements),
            "sparse_disagreements": len(sparse_disagreements),
        },
        "density": {
            "median_neighbors_all": (median(all_neighbor_counts) if all_neighbor_counts else None),
            "median_neighbors_disagreements": (
                median(disagreement_neighbor_counts) if disagreement_neighbor_counts else None
            ),
            "mean_neighbors_all": (mean(all_neighbor_counts) if all_neighbor_counts else None),
            "mean_neighbors_disagreements": (
                mean(disagreement_neighbor_counts) if disagreement_neighbor_counts else None
            ),
        },
        "disagreement_outcome_comparison": {
            "mapped_disagreements": len(mapped_outcomes),
            "singleton_better": singleton_better,
            "full_context_better": full_better,
            "ties": ties,
        },
        "example_disagreements": [asdict(row) for row in example_rows],
        "output_records_jsonl": str(output_jsonl),
    }

    payload = {
        "summary": summary,
        "disagreement_outcomes": [asdict(row) for row in disagreement_outcomes],
    }
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output_json": str(output_json), **summary["counts"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
