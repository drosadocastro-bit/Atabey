from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from atabey.tracking.global_window_optimizer import GlobalWindowSettings
from atabey.tracking.kinematic_recovery import KinematicRecoverySettings

try:
    from run_hybrid_submission import build_graph_cfar_sidelobe
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_hybrid_submission import build_graph_cfar_sidelobe

try:
    from run_v16_kinematic_validation import (
        COHORT_AT_RISK_51,
        COHORT_OUTSIDE_15,
        COHORT_ROUTED_66,
        load_cfar_validation_cohorts,
        validate_expected_cohort_sizes,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_v16_kinematic_validation import (
        COHORT_AT_RISK_51,
        COHORT_OUTSIDE_15,
        COHORT_ROUTED_66,
        load_cfar_validation_cohorts,
        validate_expected_cohort_sizes,
    )


@dataclass(frozen=True)
class StageTimingRecord:
    sample_id: str
    source_id: str
    source_t: int
    window_frames: int
    layer1_candidates: int
    layer2_candidates: int
    candidate_enumeration_ms: float
    cost_build_ms: float
    solve_ms: float
    total_ms: float


@dataclass(frozen=True)
class SampleBuildTiming:
    sample_id: str
    graph_build_seconds: float
    prep_seconds: float
    profiled_edges: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V18 runtime diagnostic for bounded global optimization shadow pass.")
    parser.add_argument("--train-dir", default="train", help="Directory containing train sample zarr/geff pairs.")
    parser.add_argument("--scan-json", default="submissions/cfar_bounded_scan_fulltrain.json")
    parser.add_argument("--v16-diagnostic-json", default="submissions/v16_diagnostic_root_cause.json")
    parser.add_argument("--v17-validate-json", default="submissions/v17_hard_exclusion_validate.json")
    parser.add_argument("--v18-shadow-json", default="submissions/v18_global_optimization_bounded.json")
    parser.add_argument("--cohort", choices=["routed", "at_risk", "outside"], default="at_risk")
    parser.add_argument("--sample-limit", type=int, default=6)
    parser.add_argument("--window-sizes", default="3,5", help="Comma-separated window sizes to profile.")
    parser.add_argument("--output-json", default="submissions/v18_runtime_diagnostic.json")
    parser.add_argument("--kaggle-runtime-minutes", type=float, default=720.0)
    return parser.parse_args()


def _distance_um(left: Any, right: Any) -> float:
    return float(np.linalg.norm(np.array(left.position_um, dtype=float) - np.array(right.position_um, dtype=float)))


def _predicted_position(source: Any, predecessor: Any | None) -> np.ndarray:
    source_position = np.array(source.position_um, dtype=float)
    if predecessor is None:
        return source_position
    velocity = source_position - np.array(predecessor.position_um, dtype=float)
    return source_position + velocity


def _first_step_cost(source: Any, predecessor: Any | None, target: Any, settings: GlobalWindowSettings) -> float:
    predicted = _predicted_position(source, predecessor)
    prediction_error = float(np.linalg.norm(np.array(target.position_um, dtype=float) - predicted))
    direct_distance = _distance_um(source, target)
    return (
        float(settings.first_step_prediction_weight) * prediction_error
        + float(settings.first_step_distance_weight) * direct_distance
    )


def _transition_cost(prev: Any, nxt: Any, settings: GlobalWindowSettings) -> float:
    # Diagnostic-only transition cost for layers >= 2. This preserves the same
    # second-step weighted distance structure without changing production logic.
    direct_distance = _distance_um(prev, nxt)
    return float(settings.second_step_distance_weight) * direct_distance


def _build_predecessor_map(graph: Any) -> dict[str, Any]:
    detection_by_id = {d.node_id: d for d in graph.detections}
    predecessor_by_id: dict[str, Any] = {}
    for edge in graph.edges:
        src = detection_by_id.get(edge.source_id)
        tgt = detection_by_id.get(edge.target_id)
        if src is None or tgt is None:
            continue
        if int(tgt.t) != int(src.t) + 1:
            continue
        existing = predecessor_by_id.get(tgt.node_id)
        if existing is None or int(src.t) > int(existing.t):
            predecessor_by_id[tgt.node_id] = src
    return predecessor_by_id


def _target_rows_by_sample(v16_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample_id, payload in v16_payload.get("per_sample", {}).items():
        rows = []
        for row in payload.get("regressed_edges", []):
            if str(row.get("type")) != "Type1_direct_edge_replaced_by_frame_skip":
                continue
            rows.append(dict(row))
        if rows:
            grouped[str(sample_id)] = rows
    return grouped


def _profile_window_stages(
    *,
    source: Any,
    predecessor: Any | None,
    detections_by_t: dict[int, list[Any]],
    max_link_distance_um: float,
    settings: GlobalWindowSettings,
    window_frames: int,
    sample_id: str,
) -> StageTimingRecord:
    import networkx as nx

    t0 = time.perf_counter()

    enum_start = time.perf_counter()
    layers: list[list[Any]] = []
    for step in range(1, int(window_frames)):
        layers.append(list(detections_by_t.get(int(source.t) + step, [])))

    if not layers:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return StageTimingRecord(
            sample_id=sample_id,
            source_id=source.node_id,
            source_t=int(source.t),
            window_frames=int(window_frames),
            layer1_candidates=0,
            layer2_candidates=0,
            candidate_enumeration_ms=elapsed,
            cost_build_ms=0.0,
            solve_ms=0.0,
            total_ms=elapsed,
        )

    # Keep only reachable first-layer candidates under the same distance gate.
    first_layer = [node for node in layers[0] if _distance_um(source, node) <= float(max_link_distance_um)]
    layers[0] = first_layer

    transitions: dict[tuple[int, str], list[Any]] = {}
    for layer_idx in range(len(layers) - 1):
        current_layer = layers[layer_idx]
        next_layer = layers[layer_idx + 1]
        if not current_layer or not next_layer:
            continue
        for node in current_layer:
            key = (layer_idx, str(node.node_id))
            successors = [
                nxt for nxt in next_layer if _distance_um(node, nxt) <= float(max_link_distance_um)
            ]
            transitions[key] = successors

    enum_ms = (time.perf_counter() - enum_start) * 1000.0

    cost_start = time.perf_counter()
    graph = nx.DiGraph()
    graph.add_node("S", demand=-1)
    graph.add_node("T", demand=1)

    if layers[0]:
        for node in layers[0]:
            node_name = f"L1|{node.node_id}"
            graph.add_node(node_name, demand=0)
            start_cost = _first_step_cost(source, predecessor, node, settings)
            graph.add_edge(
                "S",
                node_name,
                capacity=1,
                weight=int(round(start_cost * float(settings.weight_scale))),
            )

    for layer_idx, layer_nodes in enumerate(layers, start=1):
        remaining_layers = max(0, len(layers) - layer_idx)
        terminal_weight = int(
            round(float(remaining_layers) * float(settings.terminal_without_second_step_penalty) * float(settings.weight_scale))
        )
        for node in layer_nodes:
            node_name = f"L{layer_idx}|{node.node_id}"
            if node_name not in graph:
                graph.add_node(node_name, demand=0)
            graph.add_edge(node_name, "T", capacity=1, weight=terminal_weight)

            if layer_idx >= len(layers):
                continue
            successors = transitions.get((layer_idx - 1, str(node.node_id)), [])
            for nxt in successors:
                next_name = f"L{layer_idx + 1}|{nxt.node_id}"
                if next_name not in graph:
                    graph.add_node(next_name, demand=0)
                transition_cost = _transition_cost(node, nxt, settings)
                graph.add_edge(
                    node_name,
                    next_name,
                    capacity=1,
                    weight=int(round(transition_cost * float(settings.weight_scale))),
                )

    cost_ms = (time.perf_counter() - cost_start) * 1000.0

    solve_start = time.perf_counter()
    if graph.out_degree("S") > 0:
        nx.min_cost_flow(graph)
    solve_ms = (time.perf_counter() - solve_start) * 1000.0

    total_ms = (time.perf_counter() - t0) * 1000.0

    return StageTimingRecord(
        sample_id=sample_id,
        source_id=source.node_id,
        source_t=int(source.t),
        window_frames=int(window_frames),
        layer1_candidates=len(layers[0]),
        layer2_candidates=(len(layers[1]) if len(layers) > 1 else 0),
        candidate_enumeration_ms=float(enum_ms),
        cost_build_ms=float(cost_ms),
        solve_ms=float(solve_ms),
        total_ms=float(total_ms),
    )


def _cohort_ids(*, cohort_name: str, cohorts: Any) -> list[str]:
    if cohort_name == "routed":
        return list(cohorts.routed_cfar_66)
    if cohort_name == "at_risk":
        return list(cohorts.at_risk_pfa_1e_03_51)
    return list(cohorts.outside_at_risk_15)


def _safe_pct(part: float, total: float) -> float:
    if total <= 0.0:
        return 0.0
    return float(part) / float(total)


def _density_buckets(records: list[StageTimingRecord], window_frames: int) -> dict[str, list[StageTimingRecord]]:
    scoped = [record for record in records if int(record.window_frames) == int(window_frames)]
    if not scoped:
        return {"sparse": [], "mid": [], "dense": []}
    counts = sorted(record.layer1_candidates for record in scoped)
    q1 = counts[max(0, int(0.25 * (len(counts) - 1)))]
    q3 = counts[max(0, int(0.75 * (len(counts) - 1)))]
    sparse = [record for record in scoped if record.layer1_candidates <= q1]
    dense = [record for record in scoped if record.layer1_candidates >= q3]
    mid = [record for record in scoped if record not in sparse and record not in dense]
    return {"sparse": sparse, "mid": mid, "dense": dense}


def _summarize_stage(records: list[StageTimingRecord]) -> dict[str, Any]:
    if not records:
        return {
            "records": 0,
            "mean_candidate_enumeration_ms": 0.0,
            "mean_cost_build_ms": 0.0,
            "mean_solve_ms": 0.0,
            "mean_total_ms": 0.0,
            "stage_percentages": {
                "candidate_enumeration": 0.0,
                "cost_build": 0.0,
                "solve": 0.0,
            },
            "mean_layer1_candidates": 0.0,
            "mean_layer2_candidates": 0.0,
        }

    enum = float(mean(record.candidate_enumeration_ms for record in records))
    cost = float(mean(record.cost_build_ms for record in records))
    solve = float(mean(record.solve_ms for record in records))
    total = float(mean(record.total_ms for record in records))
    return {
        "records": len(records),
        "mean_candidate_enumeration_ms": enum,
        "mean_cost_build_ms": cost,
        "mean_solve_ms": solve,
        "mean_total_ms": total,
        "stage_percentages": {
            "candidate_enumeration": _safe_pct(enum, total),
            "cost_build": _safe_pct(cost, total),
            "solve": _safe_pct(solve, total),
        },
        "mean_layer1_candidates": float(mean(record.layer1_candidates for record in records)),
        "mean_layer2_candidates": float(mean(record.layer2_candidates for record in records)),
    }


def main() -> None:
    args = _parse_args()
    train_dir = Path(args.train_dir)
    scan_json = Path(args.scan_json)
    v16_diagnostic_json = Path(args.v16_diagnostic_json)
    v17_validate_json = Path(args.v17_validate_json)
    v18_shadow_json = Path(args.v18_shadow_json)
    output_json = Path(args.output_json)

    cohorts = load_cfar_validation_cohorts(scan_json)
    validate_expected_cohort_sizes(cohorts)

    v16_payload = json.loads(v16_diagnostic_json.read_text(encoding="utf-8"))
    v17_payload = json.loads(v17_validate_json.read_text(encoding="utf-8"))
    v18_payload = json.loads(v18_shadow_json.read_text(encoding="utf-8")) if v18_shadow_json.exists() else None

    window_sizes = [int(part.strip()) for part in str(args.window_sizes).split(",") if part.strip()]
    if not window_sizes:
        raise ValueError("At least one window size is required.")

    target_rows_by_sample = _target_rows_by_sample(v16_payload)
    cohort_ids = [sample_id for sample_id in _cohort_ids(cohort_name=args.cohort, cohorts=cohorts) if sample_id in target_rows_by_sample]
    sample_ids = cohort_ids[: max(1, int(args.sample_limit))]

    v17_metadata = dict(v17_payload["metadata"])
    max_link_distance_um = float(v17_metadata["cfar_max_link_distance_um"])
    kinematic_settings = KinematicRecoverySettings(**v17_metadata["kinematic_recovery_settings"])
    window_settings = GlobalWindowSettings()

    sample_build_timings: list[SampleBuildTiming] = []
    stage_records: list[StageTimingRecord] = []

    for idx, sample_id in enumerate(sample_ids, start=1):
        print(f"[runtime {idx}/{len(sample_ids)}] sample={sample_id}", flush=True)
        sample_path = train_dir / f"{sample_id}.zarr"

        build_start = time.perf_counter()
        graph, _fallbacks, _telemetry = build_graph_cfar_sidelobe(
            sample_path=sample_path,
            threshold=float(v17_metadata["cfar_threshold"]),
            cfar_training_radius_voxels=tuple(v17_metadata["cfar_training_radius_voxels"]),
            cfar_guard_radius_voxels=tuple(v17_metadata["cfar_guard_radius_voxels"]),
            cfar_k_sigma=float(v17_metadata["cfar_k_sigma"]),
            sidelobe_radius_voxels=tuple(v17_metadata["sidelobe_radius_voxels"]),
            sidelobe_floor_ratio=float(v17_metadata["sidelobe_floor_ratio"]),
            max_detections_per_timepoint=(
                int(v17_metadata["max_detections_per_timepoint"])
                if v17_metadata["max_detections_per_timepoint"] is not None
                else None
            ),
            link_strategy=str(v17_metadata["cfar_link_strategy"]),
            max_link_distance_um=max_link_distance_um,
            max_timepoints=int(v17_metadata["max_timepoints"]),
            kinematic_recovery_enabled=True,
            kinematic_recovery_settings=kinematic_settings,
            return_kinematic_telemetry=True,
        )
        graph_build_seconds = float(time.perf_counter() - build_start)

        prep_start = time.perf_counter()
        detection_by_id = {d.node_id: d for d in graph.detections}
        detections_by_t: dict[int, list[Any]] = {}
        for detection in graph.detections:
            detections_by_t.setdefault(int(detection.t), []).append(detection)
        predecessor_by_id = _build_predecessor_map(graph)

        rows = target_rows_by_sample.get(sample_id, [])
        prep_seconds = float(time.perf_counter() - prep_start)

        profiled_edges = 0
        for row in rows:
            source_id = str(row["pred_source_off"])
            source = detection_by_id.get(source_id)
            if source is None:
                continue
            predecessor = predecessor_by_id.get(source.node_id)
            for window_frames in window_sizes:
                stage_records.append(
                    _profile_window_stages(
                        source=source,
                        predecessor=predecessor,
                        detections_by_t=detections_by_t,
                        max_link_distance_um=max_link_distance_um,
                        settings=window_settings,
                        window_frames=int(window_frames),
                        sample_id=sample_id,
                    )
                )
            profiled_edges += 1

        sample_build_timings.append(
            SampleBuildTiming(
                sample_id=sample_id,
                graph_build_seconds=graph_build_seconds,
                prep_seconds=prep_seconds,
                profiled_edges=profiled_edges,
            )
        )

    by_window: dict[int, dict[str, Any]] = {}
    for window_frames in window_sizes:
        scoped = [record for record in stage_records if int(record.window_frames) == int(window_frames)]
        density = _density_buckets(stage_records, window_frames)
        by_window[int(window_frames)] = {
            "overall": _summarize_stage(scoped),
            "sparse": _summarize_stage(density["sparse"]),
            "dense": _summarize_stage(density["dense"]),
        }

    mean_graph_build_seconds = float(mean(item.graph_build_seconds for item in sample_build_timings)) if sample_build_timings else 0.0
    mean_prep_seconds = float(mean(item.prep_seconds for item in sample_build_timings)) if sample_build_timings else 0.0
    default_window = min(window_sizes)
    default_window_records = [record for record in stage_records if int(record.window_frames) == int(default_window)]
    mean_default_shadow_ms = float(mean(record.total_ms for record in default_window_records)) if default_window_records else 0.0

    build_vs_shadow_share = {
        "graph_build_share": _safe_pct(mean_graph_build_seconds * 1000.0, (mean_graph_build_seconds * 1000.0) + mean_default_shadow_ms),
        "shadow_share": _safe_pct(mean_default_shadow_ms, (mean_graph_build_seconds * 1000.0) + mean_default_shadow_ms),
    }

    full_mean_graph_build = (
        float(v18_payload.get("runtime", {}).get("graph_build_mean_seconds", mean_graph_build_seconds))
        if isinstance(v18_payload, dict)
        else mean_graph_build_seconds
    )
    full_mean_shadow_ms = (
        float(v18_payload.get("runtime", {}).get("shadow_eval_mean_ms", mean_default_shadow_ms))
        if isinstance(v18_payload, dict)
        else mean_default_shadow_ms
    )

    extrapolated = {
        "cohort_66_total_minutes": (66.0 * (full_mean_graph_build + (full_mean_shadow_ms / 1000.0))) / 60.0,
        "cohort_51_total_minutes": (51.0 * (full_mean_graph_build + (full_mean_shadow_ms / 1000.0))) / 60.0,
        "kaggle_runtime_limit_minutes": float(args.kaggle_runtime_minutes),
    }
    extrapolated["cohort_66_budget_fraction"] = _safe_pct(
        extrapolated["cohort_66_total_minutes"], extrapolated["kaggle_runtime_limit_minutes"]
    )
    extrapolated["cohort_51_budget_fraction"] = _safe_pct(
        extrapolated["cohort_51_total_minutes"], extrapolated["kaggle_runtime_limit_minutes"]
    )

    output_payload = {
        "metadata": {
            "experiment": "v18_runtime_diagnostic",
            "objective": "locate runtime hot spots for bounded global optimization shadow before additional accuracy work",
            "cohort": args.cohort,
            "sample_limit": int(args.sample_limit),
            "sample_ids": sample_ids,
            "window_sizes": window_sizes,
            "v16_diagnostic_json": str(v16_diagnostic_json),
            "v17_validate_json": str(v17_validate_json),
            "v18_shadow_json": str(v18_shadow_json),
            "cohort_sizes": {
                COHORT_ROUTED_66: len(cohorts.routed_cfar_66),
                COHORT_AT_RISK_51: len(cohorts.at_risk_pfa_1e_03_51),
                COHORT_OUTSIDE_15: len(cohorts.outside_at_risk_15),
            },
        },
        "sample_build_timings": [asdict(item) for item in sample_build_timings],
        "window_stage_breakdown": by_window,
        "setup_vs_solver": {
            "mean_graph_build_seconds": mean_graph_build_seconds,
            "mean_prep_seconds": mean_prep_seconds,
            "mean_shadow_decision_ms_window_default": mean_default_shadow_ms,
            "build_vs_shadow_share": build_vs_shadow_share,
        },
        "extrapolated_runtime": extrapolated,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "output_json": str(output_json),
                "samples_profiled": len(sample_ids),
                "edge_profiles": len(stage_records),
                "mean_graph_build_seconds": mean_graph_build_seconds,
                "mean_shadow_decision_ms": mean_default_shadow_ms,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
