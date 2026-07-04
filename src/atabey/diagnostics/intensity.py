from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from pathlib import Path

import numpy as np

from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.io.zarr_reader import open_competition_array, read_timepoint, sample_id_from_zarr_path


@dataclass(frozen=True)
class TimepointIntensityStats:
    t: int
    annotated_nodes: int
    p01: float
    p50: float
    p95: float
    p99: float
    p995: float
    p999: float
    max_value: float


@dataclass(frozen=True)
class AnnotationIntensitySummary:
    count: int
    mean_raw: float | None
    median_raw: float | None
    mean_normalized: float | None
    median_normalized: float | None
    mean_local_max_normalized: float | None
    median_local_max_normalized: float | None
    fraction_centroid_at_threshold: float | None
    fraction_local_max_at_threshold: float | None


@dataclass(frozen=True)
class AnnotationIntensityReport:
    sample_id: str
    threshold: float
    local_radius: int
    annotated_nodes: int
    annotated_timepoints: int
    timepoint_stats: list[TimepointIntensityStats]
    centroid_summary: AnnotationIntensitySummary
    note: str = (
        "Intensity diagnostics describe sparse annotated positions under the baseline "
        "normalization; they are failure-analysis evidence, not biological truth."
    )


def summarize_annotation_intensity(
    sample_path: str | Path,
    ground_truth: SparseGroundTruthGraph,
    *,
    threshold: float = 0.65,
    local_radius: int = 1,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.5,
) -> AnnotationIntensityReport:
    """Summarize raw and normalized intensity around sparse annotated centroids.

    Only annotated timepoints are read. Normalization mirrors the current baseline
    detector so this report can explain threshold misses without loading a full
    video for unrelated frames.
    """

    sample_id = sample_id_from_zarr_path(sample_path)
    array = open_competition_array(sample_path)
    nodes_by_t: dict[int, list[GroundTruthNode]] = {}
    for node in ground_truth.nodes:
        nodes_by_t.setdefault(node.t, []).append(node)

    timepoint_stats: list[TimepointIntensityStats] = []
    centroid_values: list[float] = []
    normalized_values: list[float] = []
    local_max_values: list[float] = []
    for t in sorted(nodes_by_t):
        volume = np.asarray(read_timepoint(array, t))
        p01, p50, p95, p99, p995, p999 = np.percentile(
            volume, [lower_percentile, 50.0, 95.0, 99.0, upper_percentile, 99.9]
        )
        high = float(p995)
        low = float(p01)
        scale = high - low
        timepoint_stats.append(
            TimepointIntensityStats(
                t=t,
                annotated_nodes=len(nodes_by_t[t]),
                p01=low,
                p50=float(p50),
                p95=float(p95),
                p99=float(p99),
                p995=high,
                p999=float(p999),
                max_value=float(np.max(volume)),
            )
        )
        for node in nodes_by_t[t]:
            z, y, x = _clipped_indices(volume.shape, node.z, node.y, node.x)
            raw = float(volume[z, y, x])
            patch = _local_patch(volume, z, y, x, local_radius)
            centroid_values.append(raw)
            normalized_values.append(_normalize_scalar(raw, low, scale))
            local_max_values.append(_normalize_scalar(float(np.max(patch)), low, scale))

    return AnnotationIntensityReport(
        sample_id=sample_id,
        threshold=threshold,
        local_radius=local_radius,
        annotated_nodes=len(ground_truth.nodes),
        annotated_timepoints=len(nodes_by_t),
        timepoint_stats=timepoint_stats,
        centroid_summary=_summarize_annotation_values(
            centroid_values,
            normalized_values,
            local_max_values,
            threshold,
        ),
    )


def _summarize_annotation_values(
    raw_values: list[float],
    normalized_values: list[float],
    local_max_values: list[float],
    threshold: float,
) -> AnnotationIntensitySummary:
    if not raw_values:
        return AnnotationIntensitySummary(0, None, None, None, None, None, None, None, None)
    centroid_hits = sum(value >= threshold for value in normalized_values)
    local_hits = sum(value >= threshold for value in local_max_values)
    return AnnotationIntensitySummary(
        count=len(raw_values),
        mean_raw=float(mean(raw_values)),
        median_raw=float(median(raw_values)),
        mean_normalized=float(mean(normalized_values)),
        median_normalized=float(median(normalized_values)),
        mean_local_max_normalized=float(mean(local_max_values)),
        median_local_max_normalized=float(median(local_max_values)),
        fraction_centroid_at_threshold=centroid_hits / len(normalized_values),
        fraction_local_max_at_threshold=local_hits / len(local_max_values),
    )


def _normalize_scalar(value: float, low: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return float(np.clip((value - low) / scale, 0.0, 1.0))


def _clipped_indices(shape: tuple[int, int, int], z: int, y: int, x: int) -> tuple[int, int, int]:
    return (
        int(np.clip(z, 0, shape[0] - 1)),
        int(np.clip(y, 0, shape[1] - 1)),
        int(np.clip(x, 0, shape[2] - 1)),
    )


def _local_patch(volume: np.ndarray, z: int, y: int, x: int, radius: int) -> np.ndarray:
    radius = max(0, int(radius))
    return volume[
        max(0, z - radius) : min(volume.shape[0], z + radius + 1),
        max(0, y - radius) : min(volume.shape[1], y + radius + 1),
        max(0, x - radius) : min(volume.shape[2], x + radius + 1),
    ]
