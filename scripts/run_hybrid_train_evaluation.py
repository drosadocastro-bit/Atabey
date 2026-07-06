from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from atabey.baseline import build_baseline_graph
from atabey.detection.adaptive import ForegroundProfile, choose_settings_for_sample
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.hybrid_config import (
    DEFAULT_GUARDRAIL_SETTINGS,
    DEFAULT_HYBRID_FROZEN_DEFAULTS,
    DEFAULT_KINEMATIC_RECOVERY_SETTINGS,
)
from atabey.tracking.kinematic_recovery import KinematicRecoverySettings
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.correlation_active import build_active_graph
from atabey.tracking.event_shadow import compute_lineage_event_shadow
from atabey.tracking.track_quality_shadow import compute_track_quality_shadow

try:
    from run_hybrid_submission import build_graph_cfar_sidelobe
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_hybrid_train_evaluation.
    from scripts.run_hybrid_submission import build_graph_cfar_sidelobe


@dataclass(frozen=True)
class TrainHybridEvalRecord:
    sample_id: str
    route: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    sparse_nodes: int
    matched_sparse_nodes: int
    sparse_recall: float | None
    sparse_edge_recall: float | None
    predicted_to_estimated_node_ratio: float | None
    quality_score: float
    quality_per_second: float
    detector: str
    link_strategy: str
    max_link_distance_um: float
    cfar_threshold_mode: str | None
    cfar_k_sigma: float | None
    cfar_pfa: float | None
    sidelobe_mode: str | None
    sidelobe_radius_voxels: tuple[int, int, int] | None
    sidelobe_axial_z_radius_voxels: int | None
    sidelobe_axial_xy_tolerance_voxels: tuple[int, int] | None
    sidelobe_floor_ratio: float | None
    median_largest_component_voxels: float
    median_foreground_fraction: float
    reason: str
    max_detections_per_timepoint: int | None
    max_timepoints: int | None
<<<<<<< HEAD
    kinematic_recovery_enabled: bool = False
    kinematic_recovered_edges: int | None = None
    kinematic_suppressed_by_clean_context: int | None = None
    kinematic_suppressed_by_edge_ceiling: int | None = None
    kinematic_overhead_ms: float | None = None
=======
    track_quality_shadow_enabled: bool
    track_quality_shadow_mean: float | None
    track_quality_shadow_beacon_count: int | None
    track_quality_shadow_beacon_fraction: float | None
    latent_shadow_enabled: bool
    latent_shadow_window_frames: int | None
    latent_shadow_candidate_count: int | None
    latent_shadow_mean_prediction_error_um: float | None
    mitosis_shadow_enabled: bool
    mitosis_shadow_candidate_count: int | None
    correlation_recovery_enabled: bool = False
    correlation_synthetic_count: int | None = None
    correlation_suppressed_by_merge_gate: int | None = None
>>>>>>> origin/main


@dataclass(frozen=True)
class TrainHybridEvalSummary:
    route: str
    samples: int
    total_elapsed_seconds: float
    mean_elapsed_seconds: float
    total_predicted_nodes: int
    total_predicted_edges: int
    mean_sparse_recall: float | None
    mean_sparse_edge_recall: float | None
    mean_quality_score: float
    quality_per_second: float


def _parse_int_tuple(spec: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in str(spec).split(",") if part.strip()]
    if len(parts) != 3:
        raise ValueError(f"Expected three comma-separated integers, got: {spec!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _format_int_tuple(spec: tuple[int, int, int]) -> str:
    return f"{spec[0]},{spec[1]},{spec[2]}"


def _parse_int_pair(spec: str) -> tuple[int, int]:
    parts = [part.strip() for part in str(spec).split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError(f"Expected two comma-separated integers, got: {spec!r}")
    return int(parts[0]), int(parts[1])


def _format_int_pair(spec: tuple[int, int]) -> str:
    return f"{spec[0]},{spec[1]}"


def _safe_rate(numerator: float, elapsed_seconds: float) -> float:
    return float(numerator) / max(float(elapsed_seconds), 1e-9)


def _quality_score(sparse_recall: float | None, sparse_edge_recall: float | None) -> float:
    node_component = 0.0 if sparse_recall is None else float(sparse_recall)
    edge_component = 0.0 if sparse_edge_recall is None else float(sparse_edge_recall)
    return 0.5 * node_component + 0.5 * edge_component


def _mean_optional(values: list[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return float(sum(filtered) / len(filtered))


def _is_profile_6bba_like_for_cfar(profile: ForegroundProfile) -> bool:
    return (
        profile.median_largest_component_voxels >= 100_000
        and profile.median_largest_component_voxels <= 600_000
        and profile.median_foreground_fraction >= 0.05
        and profile.median_foreground_fraction <= 0.20
    )


def _should_use_cfar_route(*, profile: ForegroundProfile, adaptive_detector: str, cfar_route_policy: str) -> bool:
    if adaptive_detector != "local_maxima":
        return False
    if cfar_route_policy == "merged_all":
        return True
    if cfar_route_policy == "merged_6bba_only":
        return _is_profile_6bba_like_for_cfar(profile)
    raise ValueError(f"Unknown CFAR route policy: {cfar_route_policy}")


def _validate_experimental_route_scope(
    *,
    cfar_route_policy: str,
    cfar_threshold_mode: str,
    sidelobe_mode: str,
    latent_shadow: bool,
    mitosis_shadow: bool,
    allow_unsafe_pfa_axial: bool,
) -> None:
    experimental_enabled = (
        cfar_threshold_mode != "sigma"
        or sidelobe_mode != "isotropic"
        or latent_shadow
        or mitosis_shadow
    )
    if experimental_enabled and cfar_route_policy != "merged_6bba_only":
        raise ValueError(
            "Experimental CFAR/lineage shadow features are restricted to "
            "cfar-route-policy=merged_6bba_only for bounded evaluation."
        )

    unsafe_combo_enabled = cfar_threshold_mode == "pfa" and sidelobe_mode == "axial"
    if unsafe_combo_enabled and not allow_unsafe_pfa_axial:
        raise ValueError(
            "CFAR pfa+axial is parked by default due collapse-risk observations; "
            "pass --allow-unsafe-pfa-axial only for bounded experiments."
        )


def _build_v9_style_graph(sample_path: Path, max_timepoints: int | None):
    profile, settings = choose_settings_for_sample(sample_path)
    link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
    reason = settings.reason.replace(" with a bounded one-frame latent recovery bridge", "")
    graph = build_baseline_graph(
        sample_path,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
    return graph, profile, settings.detector, link_strategy, reason, float(settings.max_link_distance_um)


def _build_hybrid_graph(
    *,
    sample_path: Path,
    max_timepoints: int | None,
    cfar_threshold: float,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
    cfar_threshold_mode: str,
    cfar_k_sigma: float,
    cfar_pfa: float,
    sidelobe_mode: str,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_axial_z_radius_voxels: int,
    sidelobe_axial_xy_tolerance_voxels: tuple[int, int],
    sidelobe_floor_ratio: float,
    max_detections_per_timepoint: int | None,
    cfar_link_strategy: str,
    cfar_max_link_distance_um: float,
    cfar_route_policy: str,
    enable_kinematic_recovery: bool,
    kinematic_recovery_settings: KinematicRecoverySettings,
):
    profile, settings = choose_settings_for_sample(sample_path)
    if _should_use_cfar_route(
        profile=profile,
        adaptive_detector=settings.detector,
        cfar_route_policy=cfar_route_policy,
    ):
        graph, _spike_fallback_count, telemetry = build_graph_cfar_sidelobe(
            sample_path=sample_path,
            threshold=cfar_threshold,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_threshold_mode=cfar_threshold_mode,
            cfar_k_sigma=cfar_k_sigma,
            cfar_pfa=cfar_pfa,
            sidelobe_mode=sidelobe_mode,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_axial_z_radius_voxels=sidelobe_axial_z_radius_voxels,
            sidelobe_axial_xy_tolerance_voxels=sidelobe_axial_xy_tolerance_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            max_detections_per_timepoint=max_detections_per_timepoint,
            guardrail_spike_multiplier=DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier,
            guardrail_min_history=DEFAULT_GUARDRAIL_SETTINGS.min_history,
            guardrail_history_window=DEFAULT_GUARDRAIL_SETTINGS.history_window,
            guardrail_min_absolute_count=DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count,
            guardrail_fallback_threshold=DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold,
            guardrail_fallback_max_detections=max_detections_per_timepoint,
            link_strategy=cfar_link_strategy,
            max_link_distance_um=cfar_max_link_distance_um,
            max_timepoints=max_timepoints,
            kinematic_recovery_enabled=enable_kinematic_recovery,
            kinematic_recovery_settings=kinematic_recovery_settings,
            return_kinematic_telemetry=True,
        )
<<<<<<< HEAD
        return graph, profile, "cfar_sidelobe", cfar_link_strategy, settings.reason, telemetry
=======
        return graph, profile, "cfar_sidelobe", cfar_link_strategy, settings.reason, float(cfar_max_link_distance_um)
>>>>>>> origin/main

    baseline_link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
    graph = build_baseline_graph(
        sample_path,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=baseline_link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
    reason = settings.reason.replace(" with a bounded one-frame latent recovery bridge", "")
<<<<<<< HEAD
    return graph, profile, settings.detector, baseline_link_strategy, reason, None
=======
    return graph, profile, settings.detector, baseline_link_strategy, reason, float(settings.max_link_distance_um)
>>>>>>> origin/main


def _record_for_graph(
    *,
    route: str,
    elapsed_seconds: float,
    graph,
    ground_truth,
    profile,
    detector: str,
    link_strategy: str,
    reason: str,
    max_link_distance_um: float,
    cfar_threshold_mode: str | None,
    cfar_k_sigma: float | None,
    cfar_pfa: float | None,
    sidelobe_mode: str | None,
    sidelobe_radius_voxels: tuple[int, int, int] | None,
    sidelobe_axial_z_radius_voxels: int | None,
    sidelobe_axial_xy_tolerance_voxels: tuple[int, int] | None,
    sidelobe_floor_ratio: float | None,
    max_detections_per_timepoint: int | None,
    max_timepoints: int | None,
<<<<<<< HEAD
    kinematic_recovery_enabled: bool = False,
    kinematic_recovered_edges: int | None = None,
    kinematic_suppressed_by_clean_context: int | None = None,
    kinematic_suppressed_by_edge_ceiling: int | None = None,
    kinematic_overhead_ms: float | None = None,
=======
    track_quality_shadow: bool,
    track_quality_beacon_threshold: float,
    track_quality_min_track_length: int,
    latent_shadow: bool,
    latent_shadow_window_frames: int,
    latent_shadow_max_link_distance_um: float,
    mitosis_shadow: bool,
    mitosis_shadow_distance_um: float,
    mitosis_shadow_intensity_tolerance: float,
    correlation_recovery_enabled: bool = False,
    correlation_synthetic_count: int | None = None,
    correlation_suppressed_by_merge_gate: int | None = None,
>>>>>>> origin/main
) -> TrainHybridEvalRecord:
    report = evaluate_sparse_ground_truth(graph, ground_truth, match_radius_um=7.0)
    quality_score = _quality_score(report.sparse_recall, report.sparse_edge_recall)
    track_quality_shadow_mean: float | None = None
    track_quality_shadow_beacon_count: int | None = None
    track_quality_shadow_beacon_fraction: float | None = None
    if track_quality_shadow:
        shadow = compute_track_quality_shadow(
            graph,
            beacon_quality_threshold=float(track_quality_beacon_threshold),
            min_track_length_for_beacon=int(track_quality_min_track_length),
        )
        track_quality_shadow_mean = float(shadow.mean_track_quality)
        track_quality_shadow_beacon_count = int(shadow.beacon_count)
        track_quality_shadow_beacon_fraction = float(shadow.beacon_fraction)

    latent_shadow_candidate_count: int | None = None
    latent_shadow_mean_prediction_error_um: float | None = None
    mitosis_shadow_candidate_count: int | None = None
    if latent_shadow or mitosis_shadow:
        event_shadow = compute_lineage_event_shadow(
            graph,
            latent_window_frames=int(latent_shadow_window_frames),
            latent_max_link_distance_um=float(latent_shadow_max_link_distance_um),
            mitosis_distance_um=float(mitosis_shadow_distance_um),
            mitosis_intensity_tolerance=float(mitosis_shadow_intensity_tolerance),
        )
        if latent_shadow:
            latent_shadow_candidate_count = int(event_shadow.latent_candidate_count)
            latent_shadow_mean_prediction_error_um = event_shadow.latent_mean_prediction_error_um
        if mitosis_shadow:
            mitosis_shadow_candidate_count = int(event_shadow.mitosis_candidate_count)

    return TrainHybridEvalRecord(
        sample_id=graph.sample_id,
        route=route,
        elapsed_seconds=round(elapsed_seconds, 2),
        predicted_nodes=report.predicted_nodes,
        predicted_edges=report.predicted_edges,
        sparse_nodes=report.sparse_ground_truth_nodes,
        matched_sparse_nodes=report.matched_sparse_nodes,
        sparse_recall=report.sparse_recall,
        sparse_edge_recall=report.sparse_edge_recall,
        predicted_to_estimated_node_ratio=report.predicted_to_estimated_node_ratio,
        quality_score=quality_score,
        quality_per_second=_safe_rate(quality_score, elapsed_seconds),
        detector=detector,
        link_strategy=link_strategy,
        max_link_distance_um=max_link_distance_um,
        cfar_threshold_mode=cfar_threshold_mode,
        cfar_k_sigma=cfar_k_sigma,
        cfar_pfa=cfar_pfa,
        sidelobe_mode=sidelobe_mode,
        sidelobe_radius_voxels=sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=sidelobe_floor_ratio,
        median_largest_component_voxels=profile.median_largest_component_voxels,
        median_foreground_fraction=profile.median_foreground_fraction,
        reason=reason,
        max_detections_per_timepoint=max_detections_per_timepoint,
        max_timepoints=max_timepoints,
<<<<<<< HEAD
        kinematic_recovery_enabled=bool(kinematic_recovery_enabled),
        kinematic_recovered_edges=kinematic_recovered_edges,
        kinematic_suppressed_by_clean_context=kinematic_suppressed_by_clean_context,
        kinematic_suppressed_by_edge_ceiling=kinematic_suppressed_by_edge_ceiling,
        kinematic_overhead_ms=kinematic_overhead_ms,
=======
        track_quality_shadow_enabled=bool(track_quality_shadow),
        track_quality_shadow_mean=track_quality_shadow_mean,
        track_quality_shadow_beacon_count=track_quality_shadow_beacon_count,
        track_quality_shadow_beacon_fraction=track_quality_shadow_beacon_fraction,
        latent_shadow_enabled=bool(latent_shadow),
        latent_shadow_window_frames=int(latent_shadow_window_frames) if latent_shadow else None,
        latent_shadow_candidate_count=latent_shadow_candidate_count,
        latent_shadow_mean_prediction_error_um=latent_shadow_mean_prediction_error_um,
        mitosis_shadow_enabled=bool(mitosis_shadow),
        mitosis_shadow_candidate_count=mitosis_shadow_candidate_count,
        correlation_recovery_enabled=bool(correlation_recovery_enabled),
        correlation_synthetic_count=correlation_synthetic_count,
        correlation_suppressed_by_merge_gate=correlation_suppressed_by_merge_gate,
>>>>>>> origin/main
    )


def _build_summaries(records: list[TrainHybridEvalRecord]) -> list[TrainHybridEvalSummary]:
    routes = sorted({record.route for record in records})
    summaries: list[TrainHybridEvalSummary] = []
    for route in routes:
        items = [record for record in records if record.route == route]
        total_elapsed = float(sum(item.elapsed_seconds for item in items))
        quality_total = float(sum(item.quality_score for item in items))
        summaries.append(
            TrainHybridEvalSummary(
                route=route,
                samples=len(items),
                total_elapsed_seconds=round(total_elapsed, 2),
                mean_elapsed_seconds=round(total_elapsed / len(items), 2),
                total_predicted_nodes=int(sum(item.predicted_nodes for item in items)),
                total_predicted_edges=int(sum(item.predicted_edges for item in items)),
                mean_sparse_recall=_mean_optional([item.sparse_recall for item in items]),
                mean_sparse_edge_recall=_mean_optional([item.sparse_edge_recall for item in items]),
                mean_quality_score=quality_total / len(items),
                quality_per_second=_safe_rate(quality_total, total_elapsed),
            )
        )
    summaries.sort(key=lambda summary: summary.route)
    return summaries


def run_train_evaluation(
    *,
    train_dir: Path,
    sample_ids: list[str],
    output_json: Path,
    output_summary_json: Path | None,
    max_timepoints: int | None,
    cfar_threshold: float,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
    cfar_threshold_mode: str,
    cfar_k_sigma: float,
    cfar_pfa: float,
    sidelobe_mode: str,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_axial_z_radius_voxels: int,
    sidelobe_axial_xy_tolerance_voxels: tuple[int, int],
    sidelobe_floor_ratio: float,
    max_detections_per_timepoint: int | None,
    cfar_link_strategy: str,
    cfar_max_link_distance_um: float,
    cfar_route_policy: str,
<<<<<<< HEAD
    enable_kinematic_recovery: bool,
    kinematic_recovery_settings: KinematicRecoverySettings,
=======
    track_quality_shadow: bool,
    track_quality_beacon_threshold: float,
    track_quality_min_track_length: int,
    latent_shadow: bool,
    latent_shadow_window_frames: int,
    latent_shadow_max_link_distance_um: float,
    mitosis_shadow: bool,
    mitosis_shadow_distance_um: float,
    mitosis_shadow_intensity_tolerance: float,
    allow_unsafe_pfa_axial: bool = False,
    correlation_recovery: bool = False,
    correlation_merge_gate_radius_um: float = 3.0,
    correlation_merge_gate_frame_window: int = 1,
    correlation_discount: float = 0.6,
>>>>>>> origin/main
) -> list[TrainHybridEvalRecord]:
    _validate_experimental_route_scope(
        cfar_route_policy=cfar_route_policy,
        cfar_threshold_mode=cfar_threshold_mode,
        sidelobe_mode=sidelobe_mode,
        latent_shadow=latent_shadow,
        mitosis_shadow=mitosis_shadow,
        allow_unsafe_pfa_axial=allow_unsafe_pfa_axial,
    )

    records: list[TrainHybridEvalRecord] = []
    for sample_id in sample_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")

        start = time.perf_counter()
        graph, profile, detector, link_strategy, reason, max_link_distance_um = _build_v9_style_graph(sample_path, max_timepoints)
        elapsed = time.perf_counter() - start
        record = _record_for_graph(
            route="v9_style_adaptive",
            elapsed_seconds=elapsed,
            graph=graph,
            ground_truth=ground_truth,
            profile=profile,
            detector=detector,
            link_strategy=link_strategy,
            reason=reason,
            max_link_distance_um=max_link_distance_um,
            cfar_threshold_mode=None,
            cfar_k_sigma=None,
            cfar_pfa=None,
            sidelobe_mode=None,
            sidelobe_radius_voxels=None,
            sidelobe_axial_z_radius_voxels=None,
            sidelobe_axial_xy_tolerance_voxels=None,
            sidelobe_floor_ratio=None,
            max_detections_per_timepoint=None,
            max_timepoints=max_timepoints,
            track_quality_shadow=track_quality_shadow,
            track_quality_beacon_threshold=track_quality_beacon_threshold,
            track_quality_min_track_length=track_quality_min_track_length,
            latent_shadow=latent_shadow,
            latent_shadow_window_frames=latent_shadow_window_frames,
            latent_shadow_max_link_distance_um=latent_shadow_max_link_distance_um,
            mitosis_shadow=mitosis_shadow,
            mitosis_shadow_distance_um=mitosis_shadow_distance_um,
            mitosis_shadow_intensity_tolerance=mitosis_shadow_intensity_tolerance,
        )
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

        start = time.perf_counter()
<<<<<<< HEAD
        graph, profile, detector, link_strategy, reason, telemetry = _build_hybrid_graph(
=======
        graph, profile, detector, link_strategy, reason, max_link_distance_um = _build_hybrid_graph(
>>>>>>> origin/main
            sample_path=sample_path,
            max_timepoints=max_timepoints,
            cfar_threshold=cfar_threshold,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_threshold_mode=cfar_threshold_mode,
            cfar_k_sigma=cfar_k_sigma,
            cfar_pfa=cfar_pfa,
            sidelobe_mode=sidelobe_mode,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_axial_z_radius_voxels=sidelobe_axial_z_radius_voxels,
            sidelobe_axial_xy_tolerance_voxels=sidelobe_axial_xy_tolerance_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            max_detections_per_timepoint=max_detections_per_timepoint,
            cfar_link_strategy=cfar_link_strategy,
            cfar_max_link_distance_um=cfar_max_link_distance_um,
            cfar_route_policy=cfar_route_policy,
            enable_kinematic_recovery=enable_kinematic_recovery,
            kinematic_recovery_settings=kinematic_recovery_settings,
        )
        # Experimental merge-gated recovery (Phase 3), gated OFF by default; applied
        # only on the CFAR route (validated scope). Never mutates the input graph.
        correlation_synthetic_count: int | None = None
        correlation_suppressed_by_merge_gate: int | None = None
        correlation_applied = bool(correlation_recovery and detector == "cfar_sidelobe")
        if correlation_applied:
            graph, correlation_summary = build_active_graph(
                graph,
                discount=float(correlation_discount),
                merge_gate_radius_um=float(correlation_merge_gate_radius_um),
                merge_gate_frame_window=int(correlation_merge_gate_frame_window),
                apply_merge_gate=True,
            )
            correlation_synthetic_count = int(correlation_summary.synthetic_candidate_count)
            correlation_suppressed_by_merge_gate = int(correlation_summary.suppressed_by_merge_gate)
        elapsed = time.perf_counter() - start
        record = _record_for_graph(
            route="hybrid_cfar_sidelobe",
            elapsed_seconds=elapsed,
            graph=graph,
            ground_truth=ground_truth,
            profile=profile,
            detector=detector,
            link_strategy=link_strategy,
            reason=reason,
            max_link_distance_um=max_link_distance_um,
            cfar_threshold_mode=cfar_threshold_mode if detector == "cfar_sidelobe" else None,
            cfar_k_sigma=cfar_k_sigma if detector == "cfar_sidelobe" and cfar_threshold_mode == "sigma" else None,
            cfar_pfa=cfar_pfa if detector == "cfar_sidelobe" and cfar_threshold_mode == "pfa" else None,
            sidelobe_mode=sidelobe_mode if detector == "cfar_sidelobe" else None,
            sidelobe_radius_voxels=sidelobe_radius_voxels if detector == "cfar_sidelobe" else None,
            sidelobe_axial_z_radius_voxels=sidelobe_axial_z_radius_voxels if detector == "cfar_sidelobe" else None,
            sidelobe_axial_xy_tolerance_voxels=sidelobe_axial_xy_tolerance_voxels if detector == "cfar_sidelobe" else None,
            sidelobe_floor_ratio=sidelobe_floor_ratio if detector == "cfar_sidelobe" else None,
            max_detections_per_timepoint=max_detections_per_timepoint if detector == "cfar_sidelobe" else None,
            max_timepoints=max_timepoints,
<<<<<<< HEAD
            kinematic_recovery_enabled=bool(detector == "cfar_sidelobe" and enable_kinematic_recovery),
            kinematic_recovered_edges=(telemetry.recovered_edges if telemetry is not None else None),
            kinematic_suppressed_by_clean_context=(telemetry.suppressed_by_clean_context if telemetry is not None else None),
            kinematic_suppressed_by_edge_ceiling=(telemetry.suppressed_by_edge_ceiling if telemetry is not None else None),
            kinematic_overhead_ms=(round(telemetry.overhead_ms, 2) if telemetry is not None else None),
=======
            track_quality_shadow=track_quality_shadow,
            track_quality_beacon_threshold=track_quality_beacon_threshold,
            track_quality_min_track_length=track_quality_min_track_length,
            latent_shadow=latent_shadow,
            latent_shadow_window_frames=latent_shadow_window_frames,
            latent_shadow_max_link_distance_um=latent_shadow_max_link_distance_um,
            mitosis_shadow=mitosis_shadow,
            mitosis_shadow_distance_um=mitosis_shadow_distance_um,
            mitosis_shadow_intensity_tolerance=mitosis_shadow_intensity_tolerance,
            correlation_recovery_enabled=correlation_applied,
            correlation_synthetic_count=correlation_synthetic_count,
            correlation_suppressed_by_merge_gate=correlation_suppressed_by_merge_gate,
>>>>>>> origin/main
        )
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")

    summaries = _build_summaries(records)
    if output_summary_json is not None:
        output_summary_json.parent.mkdir(parents=True, exist_ok=True)
        output_summary_json.write_text(json.dumps([asdict(summary) for summary in summaries], indent=2), encoding="utf-8")
        print(json.dumps({"output_summary_json": str(output_summary_json)}), flush=True)
    print(json.dumps({"output_json": str(output_json), "records": len(records), "summaries": [asdict(summary) for summary in summaries]}), flush=True)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare v9-style adaptive routing against hybrid CFAR+sidelobe on sparse train labels.")
    parser.add_argument("--train-dir", default="train", help="Directory containing .zarr/.geff train pairs.")
    parser.add_argument("--sample-ids", nargs="+", default=["44b6_40c45f5a", "6bba_05db0fb1"], help="Sample IDs to evaluate.")
    parser.add_argument("--output-json", default="submissions/train_slice_hybrid_eval.json", help="Output record JSON path.")
    parser.add_argument("--output-summary-json", default="submissions/train_slice_hybrid_eval_summary.json", help="Output summary JSON path.")
    parser.add_argument("--max-timepoints", type=int, default=100, help="Optional timepoint cap.")
    parser.add_argument(
        "--cfar-threshold",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
        help="CFAR global normalized floor threshold.",
    )
    parser.add_argument(
        "--cfar-training-radius",
        default=_format_int_tuple(DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels),
        help="CFAR training radius as tz,ty,tx.",
    )
    parser.add_argument(
        "--cfar-guard-radius",
        default=_format_int_tuple(DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels),
        help="CFAR guard radius as gz,gy,gx.",
    )
    parser.add_argument(
        "--cfar-k-sigma",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
        help="CFAR k-sigma multiplier.",
    )
    parser.add_argument(
        "--cfar-threshold-mode",
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode,
        choices=["sigma", "pfa"],
        help="CFAR adaptive threshold mode: sigma (mean + k*std) or pfa (CA-CFAR alpha*mean).",
    )
    parser.add_argument(
        "--cfar-pfa",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
        help="CFAR probability of false alarm used when --cfar-threshold-mode=pfa.",
    )
    parser.add_argument(
        "--sidelobe-mode",
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
        choices=["isotropic", "axial"],
        help="Sidelobe suppression mode: isotropic radius or axial Z-priority suppression.",
    )
    parser.add_argument(
        "--allow-unsafe-pfa-axial",
        action="store_true",
        default=False,
        help="Override safety gate to run the parked pfa+axial combo for bounded experiments.",
    )
    parser.add_argument(
        "--sidelobe-radius",
        default=_format_int_tuple(DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels),
        help="Sidelobe suppression radius as sz,sy,sx.",
    )
    parser.add_argument(
        "--sidelobe-axial-z-radius",
        type=int,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
        help="Axial mode Z suppression radius in voxels.",
    )
    parser.add_argument(
        "--sidelobe-axial-xy-tolerance",
        default=_format_int_pair(DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels),
        help="Axial mode XY tolerance as y,x.",
    )
    parser.add_argument(
        "--sidelobe-floor",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
        help="Sidelobe floor ratio.",
    )
    parser.add_argument(
        "--max-detections-per-timepoint",
        type=int,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
        help="CFAR route detection cap.",
    )
    parser.add_argument(
        "--cfar-route-policy",
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        choices=["merged_all", "merged_6bba_only"],
        help=(
            "Which adaptive local-maxima samples should be routed through CFAR+sidelobe; "
            "merged_6bba_only uses profile-based gating (dim/dense merged foreground), not sample prefixes."
        ),
    )
    parser.add_argument(
        "--cfar-link-strategy",
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
        help="CFAR route link strategy.",
    )
    parser.add_argument(
        "--cfar-max-link-distance-um",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
        help="CFAR route link distance.",
    )
    parser.add_argument(
<<<<<<< HEAD
        "--enable-kinematic-recovery",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable V16 kinematic soft-link recovery on the CFAR route only. Default OFF preserves V13 behavior.",
    )
    parser.add_argument(
        "--kinematic-max-gap-frames",
        type=int,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.max_gap_frames,
        help="Maximum number of missing frames eligible for kinematic recovery.",
    )
    parser.add_argument(
        "--kinematic-min-track-length-edges",
        type=int,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.min_track_length_edges,
        help="Minimum accepted track length before a dying track can enter recovery.",
    )
    parser.add_argument(
        "--kinematic-trigger-background-mean-min",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_background_mean_min,
        help="Minimum local CFAR background mean required to classify a gap as clutter-risk.",
    )
    parser.add_argument(
        "--kinematic-trigger-adaptive-threshold-min",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_adaptive_threshold_min,
        help="Minimum local adaptive threshold required for clutter-risk authorization.",
    )
    parser.add_argument(
        "--kinematic-trigger-contrast-max",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_contrast_max,
        help="Maximum allowed local contrast for a recovery-eligible suppressed termination.",
    )
    parser.add_argument(
        "--kinematic-trigger-cfar-margin-max",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_cfar_margin_max,
        help="Maximum local CFAR margin allowed for recovery authorization.",
    )
    parser.add_argument(
        "--kinematic-base-sigma-um",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.base_sigma_um,
        help="Base positional uncertainty in microns for the kinematic cone.",
    )
    parser.add_argument(
        "--kinematic-velocity-sigma-scale",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.velocity_sigma_scale,
        help="How much velocity magnitude expands the cone along the motion axis.",
    )
    parser.add_argument(
        "--kinematic-transverse-sigma-um",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.transverse_sigma_um,
        help="Cross-axis uncertainty in microns for the kinematic cone.",
    )
    parser.add_argument(
        "--kinematic-mahalanobis-threshold",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.mahalanobis_threshold,
        help="Mahalanobis gate threshold for virtual gap edges.",
    )
    parser.add_argument(
        "--kinematic-directional-cosine-min",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.directional_cosine_min,
        help="Minimum cosine agreement between historical motion and the recovered displacement.",
    )
    parser.add_argument(
        "--kinematic-temporal-discount",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.temporal_discount,
        help="Discount factor applied to gap-edge confidence as missing frames increase.",
    )
    parser.add_argument(
        "--kinematic-edge-inflation-ceiling-ratio",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.edge_inflation_ceiling_ratio,
        help="Maximum recovered-edge count as a ratio of adjacent recovered edges in the same frame.",
=======
        "--track-quality-shadow",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute shadow-only track quality/beacon diagnostics (does not alter linking).",
    )
    parser.add_argument(
        "--track-quality-beacon-threshold",
        type=float,
        default=0.75,
        help="Minimum shadow track quality to mark a detection as beacon candidate.",
    )
    parser.add_argument(
        "--track-quality-min-track-length",
        type=int,
        default=3,
        help="Minimum shadow track depth for beacon candidacy.",
    )
    parser.add_argument(
        "--latent-shadow",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Compute dormant latent-recovery shadow diagnostics (no graph mutation).",
    )
    parser.add_argument(
        "--latent-shadow-window-frames",
        type=int,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_window_frames,
        help="Shadow latent recovery window (frames).",
    )
    parser.add_argument(
        "--latent-shadow-max-link-distance-um",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_max_link_distance_um,
        help="Shadow latent base link distance in microns (scaled by gap).",
    )
    parser.add_argument(
        "--mitosis-shadow",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Compute mitosis split shadow diagnostics (no graph mutation).",
    )
    parser.add_argument(
        "--mitosis-shadow-distance-um",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_distance_um,
        help="Mitosis shadow daughter proximity threshold in microns.",
    )
    parser.add_argument(
        "--mitosis-shadow-intensity-tolerance",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_intensity_tolerance,
        help="Relative tolerance for parent vs daughter intensity conservation in mitosis shadow.",
    )
    parser.add_argument(
        "--enable-correlation-recovery",
        action="store_true",
        default=False,
        help=(
            "EXPERIMENTAL, default OFF. Apply merge-gated (Phase 3) beacon-derived recovery "
            "to the hybrid CFAR route before scoring. Off = current V13 evaluation, unchanged."
        ),
    )
    parser.add_argument(
        "--correlation-merge-gate-radius",
        type=float,
        default=3.0,
        help="Merge-gate spatial radius (um). Validated default 3.0.",
    )
    parser.add_argument(
        "--correlation-merge-gate-frame-window",
        type=int,
        default=1,
        help="Merge-gate temporal window (frames). Validated default 1.",
    )
    parser.add_argument(
        "--correlation-discount",
        type=float,
        default=0.6,
        help="Confidence discount for synthetic recovery nodes. Validated default 0.6.",
>>>>>>> origin/main
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_train_evaluation(
        train_dir=Path(args.train_dir),
        sample_ids=list(args.sample_ids),
        output_json=Path(args.output_json),
        output_summary_json=Path(args.output_summary_json) if args.output_summary_json else None,
        max_timepoints=args.max_timepoints,
        cfar_threshold=float(args.cfar_threshold),
        cfar_training_radius_voxels=_parse_int_tuple(args.cfar_training_radius),
        cfar_guard_radius_voxels=_parse_int_tuple(args.cfar_guard_radius),
        cfar_threshold_mode=str(args.cfar_threshold_mode),
        cfar_k_sigma=float(args.cfar_k_sigma),
        cfar_pfa=float(args.cfar_pfa),
        sidelobe_mode=str(args.sidelobe_mode),
        sidelobe_radius_voxels=_parse_int_tuple(args.sidelobe_radius),
        sidelobe_axial_z_radius_voxels=int(args.sidelobe_axial_z_radius),
        sidelobe_axial_xy_tolerance_voxels=_parse_int_pair(args.sidelobe_axial_xy_tolerance),
        sidelobe_floor_ratio=float(args.sidelobe_floor),
        max_detections_per_timepoint=args.max_detections_per_timepoint,
        cfar_link_strategy=str(args.cfar_link_strategy),
        cfar_max_link_distance_um=float(args.cfar_max_link_distance_um),
        cfar_route_policy=str(args.cfar_route_policy),
<<<<<<< HEAD
        enable_kinematic_recovery=bool(args.enable_kinematic_recovery),
        kinematic_recovery_settings=KinematicRecoverySettings(
            max_gap_frames=int(args.kinematic_max_gap_frames),
            min_track_length_edges=int(args.kinematic_min_track_length_edges),
            trigger_background_mean_min=float(args.kinematic_trigger_background_mean_min),
            trigger_adaptive_threshold_min=float(args.kinematic_trigger_adaptive_threshold_min),
            trigger_contrast_max=float(args.kinematic_trigger_contrast_max),
            trigger_cfar_margin_max=float(args.kinematic_trigger_cfar_margin_max),
            base_sigma_um=float(args.kinematic_base_sigma_um),
            velocity_sigma_scale=float(args.kinematic_velocity_sigma_scale),
            transverse_sigma_um=float(args.kinematic_transverse_sigma_um),
            mahalanobis_threshold=float(args.kinematic_mahalanobis_threshold),
            directional_cosine_min=float(args.kinematic_directional_cosine_min),
            temporal_discount=float(args.kinematic_temporal_discount),
            edge_inflation_ceiling_ratio=float(args.kinematic_edge_inflation_ceiling_ratio),
        ),
=======
        track_quality_shadow=bool(args.track_quality_shadow),
        track_quality_beacon_threshold=float(args.track_quality_beacon_threshold),
        track_quality_min_track_length=int(args.track_quality_min_track_length),
        latent_shadow=bool(args.latent_shadow),
        latent_shadow_window_frames=int(args.latent_shadow_window_frames),
        latent_shadow_max_link_distance_um=float(args.latent_shadow_max_link_distance_um),
        mitosis_shadow=bool(args.mitosis_shadow),
        mitosis_shadow_distance_um=float(args.mitosis_shadow_distance_um),
        mitosis_shadow_intensity_tolerance=float(args.mitosis_shadow_intensity_tolerance),
        allow_unsafe_pfa_axial=bool(args.allow_unsafe_pfa_axial),
        correlation_recovery=bool(args.enable_correlation_recovery),
        correlation_merge_gate_radius_um=float(args.correlation_merge_gate_radius),
        correlation_merge_gate_frame_window=int(args.correlation_merge_gate_frame_window),
        correlation_discount=float(args.correlation_discount),
>>>>>>> origin/main
    )


if __name__ == "__main__":
    main()
