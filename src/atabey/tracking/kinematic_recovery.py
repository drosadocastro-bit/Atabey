from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageEdge


@dataclass(frozen=True)
class LocalContext:
    background_mean: float
    background_std: float
    adaptive_threshold: float
    normalized_signal: float
    contrast: float
    cfar_margin: float
    predicted_zyx: tuple[int, int, int]


@dataclass
class KinematicTrack:
    source: Detection
    predecessor: Detection | None
    missing_frames: int
    local_context: LocalContext


@dataclass(frozen=True)
class KinematicRecoverySettings:
    max_gap_frames: int = 1
    min_track_length_edges: int = 2
    trigger_background_mean_min: float = 0.18
    trigger_adaptive_threshold_min: float = 0.24
    trigger_contrast_max: float = 0.14
    trigger_cfar_margin_max: float = 0.02
    base_sigma_um: float = 2.0
    velocity_sigma_scale: float = 0.75
    transverse_sigma_um: float = 4.0
    mahalanobis_threshold: float = 3.5
    directional_cosine_min: float = 0.0
    temporal_discount: float = 0.7
    edge_inflation_ceiling_ratio: float = 0.25
    visual_prior_weight: float = 0.0


@dataclass
class KinematicRecoveryTelemetry:
    source_tracks_considered: int = 0
    source_tracks_enqueued: int = 0
    suppressed_by_direct_candidate: int = 0
    suppressed_by_clean_context: int = 0
    candidate_pairs_evaluated: int = 0
    recovered_edges: int = 0
    suppressed_by_edge_ceiling: int = 0
    overhead_ms: float = 0.0


def inspect_local_context(
    *,
    source: Detection,
    predecessor: Detection | None,
    normalized: np.ndarray,
    background_mean: np.ndarray,
    background_std: np.ndarray,
    cfar_k_sigma: float,
) -> LocalContext:
    z_idx, y_idx, x_idx = _predicted_voxel(source, predecessor, step_multiplier=1.0)
    z_idx = int(np.clip(z_idx, 0, normalized.shape[0] - 1))
    y_idx = int(np.clip(y_idx, 0, normalized.shape[1] - 1))
    x_idx = int(np.clip(x_idx, 0, normalized.shape[2] - 1))
    background = float(background_mean[z_idx, y_idx, x_idx])
    spread = float(background_std[z_idx, y_idx, x_idx])
    signal = float(normalized[z_idx, y_idx, x_idx])
    adaptive_threshold = background + float(cfar_k_sigma) * spread
    contrast = max(0.0, signal - background)
    cfar_margin = signal - adaptive_threshold
    return LocalContext(
        background_mean=background,
        background_std=spread,
        adaptive_threshold=adaptive_threshold,
        normalized_signal=signal,
        contrast=contrast,
        cfar_margin=cfar_margin,
        predicted_zyx=(z_idx, y_idx, x_idx),
    )


def context_authorizes_recovery(
    context: LocalContext,
    *,
    settings: KinematicRecoverySettings,
) -> bool:
    epsilon = 1e-6
    return (
        context.background_mean + epsilon >= float(settings.trigger_background_mean_min)
        and context.adaptive_threshold + epsilon >= float(settings.trigger_adaptive_threshold_min)
        and context.contrast <= float(settings.trigger_contrast_max) + epsilon
        and context.cfar_margin <= float(settings.trigger_cfar_margin_max) + epsilon
    )


def enqueue_kinematic_tracks(
    *,
    latent_tracks: dict[str, KinematicTrack],
    previous: list[Detection],
    current: list[Detection] | None = None,
    max_link_distance_um: float | None = None,
    link_strategy: str = "motion_mutual",
    matched_source_ids: set[str],
    predecessor_by_node_id: dict[str, Detection],
    track_length_by_node_id: dict[str, int],
    normalized: np.ndarray,
    background_mean: np.ndarray,
    background_std: np.ndarray,
    cfar_k_sigma: float,
    settings: KinematicRecoverySettings,
    telemetry: KinematicRecoveryTelemetry,
) -> None:
    for source in previous:
        if source.node_id in matched_source_ids:
            continue
        predecessor = predecessor_by_node_id.get(source.node_id)
        if predecessor is None:
            continue
        if track_length_by_node_id.get(source.node_id, 0) < int(settings.min_track_length_edges):
            continue
        telemetry.source_tracks_considered += 1
        if current is not None and max_link_distance_um is not None:
            direct_edges = link_adjacent_timepoints(
                [source],
                current,
                float(max_link_distance_um),
                strategy=link_strategy,
                predecessor_by_node_id={source.node_id: predecessor},
            )
            if direct_edges:
                telemetry.suppressed_by_direct_candidate += 1
                continue
        context = inspect_local_context(
            source=source,
            predecessor=predecessor,
            normalized=normalized,
            background_mean=background_mean,
            background_std=background_std,
            cfar_k_sigma=cfar_k_sigma,
        )
        if not context_authorizes_recovery(context, settings=settings):
            telemetry.suppressed_by_clean_context += 1
            continue
        latent_tracks[source.node_id] = KinematicTrack(
            source=source,
            predecessor=predecessor,
            missing_frames=1,
            local_context=context,
        )
        telemetry.source_tracks_enqueued += 1


def recover_kinematic_edges(
    *,
    latent_tracks: dict[str, KinematicTrack],
    current: list[Detection],
    used_target_ids: set[str],
    max_link_distance_um: float,
    settings: KinematicRecoverySettings,
    telemetry: KinematicRecoveryTelemetry,
    reference_edge_count: int,
) -> tuple[list[LineageEdge], set[str]]:
    if not latent_tracks or not current:
        return [], set()

    source_ids = [
        source_id
        for source_id, latent in latent_tracks.items()
        if 1 <= int(latent.missing_frames) <= int(settings.max_gap_frames)
    ]
    available_targets = [detection for detection in current if detection.node_id not in used_target_ids]
    if not source_ids or not available_targets:
        return [], set()

    cost_matrix = np.full((len(source_ids), len(available_targets)), np.inf, dtype=float)
    score_matrix = np.zeros((len(source_ids), len(available_targets)), dtype=float)
    for row_idx, source_id in enumerate(source_ids):
        latent = latent_tracks[source_id]
        for col_idx, target in enumerate(available_targets):
            candidate = _candidate_cost(
                latent=latent,
                target=target,
                max_link_distance_um=max_link_distance_um,
                settings=settings,
            )
            if candidate is None:
                continue
            cost, score = candidate
            cost_matrix[row_idx, col_idx] = cost
            score_matrix[row_idx, col_idx] = score
            telemetry.candidate_pairs_evaluated += 1

    assignments = _solve_assignments(cost_matrix)
    if not assignments:
        return [], set()

    assignments.sort(key=lambda item: item[2])
    max_recoveries = _edge_recovery_ceiling(
        reference_edge_count=reference_edge_count,
        assignment_count=len(assignments),
        ceiling_ratio=float(settings.edge_inflation_ceiling_ratio),
    )
    if len(assignments) > max_recoveries:
        telemetry.suppressed_by_edge_ceiling += len(assignments) - max_recoveries
        assignments = assignments[:max_recoveries]

    recovered_edges: list[LineageEdge] = []
    recovered_source_ids: set[str] = set()
    for row_idx, col_idx, _cost in assignments:
        latent = latent_tracks[source_ids[row_idx]]
        target = available_targets[col_idx]
        recovered_edges.append(
            LineageEdge(
                source_id=latent.source.node_id,
                target_id=target.node_id,
                confidence=float(score_matrix[row_idx, col_idx]),
                relation="kinematic_recovery",
            )
        )
        recovered_source_ids.add(latent.source.node_id)
        telemetry.recovered_edges += 1
    return recovered_edges, recovered_source_ids


def age_and_prune_kinematic_tracks(
    latent_tracks: dict[str, KinematicTrack],
    *,
    recovered_source_ids: set[str],
    max_gap_frames: int,
) -> None:
    for source_id in recovered_source_ids:
        latent_tracks.pop(source_id, None)
    for source_id, latent in list(latent_tracks.items()):
        latent.missing_frames += 1
        if latent.missing_frames > int(max_gap_frames):
            del latent_tracks[source_id]


def _candidate_cost(
    *,
    latent: KinematicTrack,
    target: Detection,
    max_link_distance_um: float,
    settings: KinematicRecoverySettings,
) -> tuple[float, float] | None:
    source_position = np.array(latent.source.position_um, dtype=float)
    target_position = np.array(target.position_um, dtype=float)
    missing_scale = float(latent.missing_frames + 1)
    predicted_position = _predicted_position_um(
        latent.source,
        latent.predecessor,
        step_multiplier=missing_scale,
    )
    displacement = target_position - source_position
    step_distance = float(np.linalg.norm(displacement))
    if step_distance > float(max_link_distance_um) * missing_scale:
        return None

    velocity = _velocity_vector_um(latent.source, latent.predecessor)
    if velocity is not None and not _passes_direction_gate(
        displacement,
        velocity,
        min_cosine=float(settings.directional_cosine_min),
    ):
        return None

    mahalanobis = _mahalanobis_distance(
        predicted_position=predicted_position,
        target_position=target_position,
        velocity=velocity,
        missing_scale=missing_scale,
        settings=settings,
    )
    if mahalanobis > float(settings.mahalanobis_threshold):
        return None

    temporal_penalty = float(latent.missing_frames) * max(0.0, 1.0 - float(settings.temporal_discount))
    cost = mahalanobis + temporal_penalty
    confidence = math.exp(-0.5 * mahalanobis * mahalanobis) * (
        float(settings.temporal_discount) ** float(latent.missing_frames)
    )
    confidence = max(0.0, min(1.0, confidence + float(settings.visual_prior_weight) * 0.0))
    return cost, confidence


def _solve_assignments(cost_matrix: np.ndarray) -> list[tuple[int, int, float]]:
    finite_mask = np.isfinite(cost_matrix)
    if not np.any(finite_mask):
        return []

    try:
        from scipy.optimize import linear_sum_assignment

        safe_costs = np.where(finite_mask, cost_matrix, 1e9)
        rows, cols = linear_sum_assignment(safe_costs)
        assignments = []
        for row_idx, col_idx in zip(rows.tolist(), cols.tolist(), strict=True):
            cost = float(cost_matrix[row_idx, col_idx])
            if math.isfinite(cost):
                assignments.append((int(row_idx), int(col_idx), cost))
        return assignments
    except ImportError:
        pass

    assignments: list[tuple[int, int, float]] = []
    used_rows: set[int] = set()
    used_cols: set[int] = set()
    for row_idx, col_idx in np.argwhere(finite_mask):
        if int(row_idx) in used_rows or int(col_idx) in used_cols:
            continue
        used_rows.add(int(row_idx))
        used_cols.add(int(col_idx))
        assignments.append((int(row_idx), int(col_idx), float(cost_matrix[int(row_idx), int(col_idx)])))
    assignments.sort(key=lambda item: item[2])
    return assignments


def _edge_recovery_ceiling(
    *,
    reference_edge_count: int,
    assignment_count: int,
    ceiling_ratio: float,
) -> int:
    if assignment_count <= 0:
        return 0
    if ceiling_ratio <= 0.0:
        return assignment_count
    baseline = max(1, int(reference_edge_count))
    return max(1, min(assignment_count, int(math.ceil(baseline * ceiling_ratio))))


def _predicted_position_um(
    source: Detection,
    predecessor: Detection | None,
    *,
    step_multiplier: float,
) -> np.ndarray:
    source_position = np.array(source.position_um, dtype=float)
    velocity = _velocity_vector_um(source, predecessor)
    if velocity is None:
        return source_position
    return source_position + velocity * float(step_multiplier)


def _predicted_voxel(
    source: Detection,
    predecessor: Detection | None,
    *,
    step_multiplier: float,
) -> tuple[int, int, int]:
    zf = float(source.z)
    yf = float(source.y)
    xf = float(source.x)
    if predecessor is not None:
        zf += (float(source.z) - float(predecessor.z)) * float(step_multiplier)
        yf += (float(source.y) - float(predecessor.y)) * float(step_multiplier)
        xf += (float(source.x) - float(predecessor.x)) * float(step_multiplier)
    return int(round(zf)), int(round(yf)), int(round(xf))


def _velocity_vector_um(source: Detection, predecessor: Detection | None) -> np.ndarray | None:
    if predecessor is None:
        return None
    velocity = np.array(source.position_um, dtype=float) - np.array(predecessor.position_um, dtype=float)
    if float(np.linalg.norm(velocity)) <= 1e-9:
        return None
    return velocity


def _passes_direction_gate(
    displacement: np.ndarray,
    velocity: np.ndarray,
    *,
    min_cosine: float,
) -> bool:
    velocity_norm = float(np.linalg.norm(velocity))
    displacement_norm = float(np.linalg.norm(displacement))
    if velocity_norm <= 1e-9 or displacement_norm <= 1e-9:
        return True
    cosine = float(np.dot(displacement, velocity) / (velocity_norm * displacement_norm))
    return cosine >= float(min_cosine)


def _mahalanobis_distance(
    *,
    predicted_position: np.ndarray,
    target_position: np.ndarray,
    velocity: np.ndarray | None,
    missing_scale: float,
    settings: KinematicRecoverySettings,
) -> float:
    residual = target_position - predicted_position
    if velocity is None:
        sigma = max(float(settings.base_sigma_um), 1e-6) * float(missing_scale)
        return float(np.linalg.norm(residual) / sigma)

    speed = float(np.linalg.norm(velocity))
    direction = velocity / max(speed, 1e-9)
    along = float(np.dot(residual, direction))
    perpendicular = residual - along * direction
    along_sigma = max(
        float(settings.base_sigma_um),
        float(settings.base_sigma_um) + speed * float(settings.velocity_sigma_scale) * float(missing_scale),
    )
    cross_sigma = max(float(settings.transverse_sigma_um), 1e-6) * float(missing_scale)
    cross_distance = float(np.linalg.norm(perpendicular))
    mahal_sq = (along / max(along_sigma, 1e-6)) ** 2 + (cross_distance / cross_sigma) ** 2
    return float(math.sqrt(max(mahal_sq, 0.0)))