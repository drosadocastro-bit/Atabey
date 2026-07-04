from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from atabey.detection.baseline import threshold_connected_components, threshold_local_maxima
from atabey.io.zarr_reader import open_competition_array, read_timepoint, sample_id_from_zarr_path
from atabey.tracking.nearest_neighbor import LinkStrategy, link_adjacent_timepoints
from atabey.types import Detection, LineageEdge, LineageGraph


DetectorName = Literal["components", "local_maxima"]


@dataclass
class _LatentTrack:
    source: Detection
    predecessor: Detection | None
    missing_frames: int


def _recover_latent_edges(
    *,
    latent_tracks: dict[str, _LatentTrack],
    current: list[Detection],
    used_target_ids: set[str],
    max_link_distance_um: float,
    latent_window_frames: int,
) -> tuple[list[LineageEdge], set[str]]:
    if not latent_tracks:
        return [], set()

    available_targets = [detection for detection in current if detection.node_id not in used_target_ids]
    if not available_targets:
        return [], set()

    target_positions = np.array([detection.position_um for detection in available_targets], dtype=float)
    candidate_pairs: list[tuple[float, str, str]] = []
    for source_id, latent in latent_tracks.items():
        if latent.missing_frames < 1 or latent.missing_frames > latent_window_frames:
            continue
        source_position = np.array(latent.source.position_um, dtype=float)
        predicted_position = source_position
        if latent.predecessor is not None:
            predecessor_position = np.array(latent.predecessor.position_um, dtype=float)
            velocity = source_position - predecessor_position
            predicted_position = source_position + velocity * float(latent.missing_frames + 1)

        prediction_errors = np.linalg.norm(target_positions - predicted_position, axis=1)
        best_idx = int(np.argmin(prediction_errors))
        target = available_targets[best_idx]
        prediction_error = float(prediction_errors[best_idx])
        step_distance = float(np.linalg.norm(np.array(target.position_um, dtype=float) - source_position))
        if prediction_error > max_link_distance_um:
            continue
        if step_distance > max_link_distance_um * float(latent.missing_frames + 1):
            continue
        candidate_pairs.append((prediction_error, source_id, target.node_id))

    candidate_pairs.sort(key=lambda item: item[0])
    recovered_source_ids: set[str] = set()
    assigned_target_ids: set[str] = set()
    recovered_edges: list[LineageEdge] = []
    for prediction_error, source_id, target_id in candidate_pairs:
        if source_id in recovered_source_ids or target_id in used_target_ids or target_id in assigned_target_ids:
            continue
        confidence = max(0.0, 1.0 - prediction_error / max_link_distance_um)
        recovered_edges.append(
            LineageEdge(
                source_id=source_id,
                target_id=target_id,
                confidence=confidence,
                relation="latent_recovery",
            )
        )
        recovered_source_ids.add(source_id)
        assigned_target_ids.add(target_id)
    return recovered_edges, recovered_source_ids


def _age_and_prune_latent_tracks(
    latent_tracks: dict[str, _LatentTrack],
    recovered_source_ids: set[str],
    latent_window_frames: int,
) -> None:
    for source_id in recovered_source_ids:
        latent_tracks.pop(source_id, None)
    for source_id, latent in list(latent_tracks.items()):
        latent.missing_frames += 1
        if latent.missing_frames > latent_window_frames:
            del latent_tracks[source_id]


def _enqueue_new_latent_tracks(
    *,
    latent_tracks: dict[str, _LatentTrack],
    previous: list[Detection],
    matched_source_ids: set[str],
    predecessor_by_node_id: dict[str, Detection],
    track_length_by_node_id: dict[str, int],
    min_latent_track_length_edges: int,
) -> None:
    for source in previous:
        if source.node_id in matched_source_ids:
            continue
        predecessor = predecessor_by_node_id.get(source.node_id)
        if predecessor is None:
            continue
        if track_length_by_node_id.get(source.node_id, 0) < min_latent_track_length_edges:
            continue
        latent_tracks[source.node_id] = _LatentTrack(
            source=source,
            predecessor=predecessor,
            missing_frames=1,
        )


def build_baseline_graph(
    sample_path: str | Path,
    *,
    sample_id: str | None = None,
    max_timepoints: int | None = None,
    threshold: float = 0.65,
    min_volume: int = 4,
    max_link_distance_um: float = 7.0,
    link_strategy: LinkStrategy = "greedy",
    detector: DetectorName = "components",
    peak_min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    max_detections_per_timepoint: int | None = None,
) -> LineageGraph:
    """Build a minimal streamed detection/linking graph for one sample.

    This baseline reads one 3D timepoint at a time, detects candidate centers,
    and links adjacent frames by one-to-one nearest neighbor in physical microns.
    It is calibration machinery, not a biological identity claim.
    """

    path = Path(sample_path)
    dataset = sample_id or sample_id_from_zarr_path(path)
    array = open_competition_array(path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))

    graph = LineageGraph(sample_id=dataset)
    previous = []
    detections_by_node_id: dict[str, Detection] = {}
    predecessor_by_node_id: dict[str, Detection] = {}
    latent_enabled = link_strategy == "motion_mutual_latent"
    adjacent_strategy: LinkStrategy = "motion_mutual" if latent_enabled else link_strategy
    latent_window_frames = 1
    min_latent_track_length_edges = 2
    latent_tracks: dict[str, _LatentTrack] = {}
    track_length_by_node_id: dict[str, int] = {}
    for t in range(total_timepoints):
        volume = read_timepoint(array, t)
        if detector == "components":
            current = threshold_connected_components(
                sample_id=dataset,
                t=t,
                volume=volume,
                threshold=threshold,
                min_volume=min_volume,
            )
        elif detector == "local_maxima":
            current = threshold_local_maxima(
                sample_id=dataset,
                t=t,
                volume=volume,
                threshold=threshold,
                min_distance_voxels=peak_min_distance_voxels,
                max_detections=max_detections_per_timepoint,
            )
        else:
            raise ValueError(f"Unknown detector: {detector}")

        for detection in current:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection

        adjacent_edges = link_adjacent_timepoints(
            previous,
            current,
            max_link_distance_um,
            strategy=adjacent_strategy,
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in adjacent_edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
            track_length_by_node_id[edge.target_id] = track_length_by_node_id.get(edge.source_id, 0) + 1

        if latent_enabled:
            matched_source_ids = {edge.source_id for edge in adjacent_edges}
            used_target_ids = {edge.target_id for edge in adjacent_edges}
            latent_edges, recovered_source_ids = _recover_latent_edges(
                latent_tracks=latent_tracks,
                current=current,
                used_target_ids=used_target_ids,
                max_link_distance_um=max_link_distance_um,
                latent_window_frames=latent_window_frames,
            )
            for edge in latent_edges:
                graph.add_edge(edge)
                predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
                track_length_by_node_id[edge.target_id] = track_length_by_node_id.get(edge.source_id, 0) + 1

            _age_and_prune_latent_tracks(
                latent_tracks=latent_tracks,
                recovered_source_ids=recovered_source_ids,
                latent_window_frames=latent_window_frames,
            )
            _enqueue_new_latent_tracks(
                latent_tracks=latent_tracks,
                previous=previous,
                matched_source_ids=matched_source_ids,
                predecessor_by_node_id=predecessor_by_node_id,
                track_length_by_node_id=track_length_by_node_id,
                min_latent_track_length_edges=min_latent_track_length_edges,
            )
        previous = current
    return graph


def build_baseline_graphs(
    sample_paths: list[str | Path],
    **kwargs: object,
) -> list[LineageGraph]:
    return [build_baseline_graph(sample_path, **kwargs) for sample_path in sample_paths]


def build_adaptive_baseline_graph(
    sample_path: str | Path,
    *,
    sample_id: str | None = None,
    max_timepoints: int | None = None,
) -> LineageGraph:
    """Build a baseline graph using image-only foreground diagnostics to choose settings."""

    from atabey.detection.adaptive import choose_settings_for_sample

    _, settings = choose_settings_for_sample(sample_path)
    return build_baseline_graph(
        sample_path,
        sample_id=sample_id,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=settings.link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
