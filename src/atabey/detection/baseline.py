from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from atabey.constants import DEFAULT_VOXEL_SCALE_UM, VoxelScale
from atabey.types import Detection


def robust_normalize(volume: np.ndarray, lower: float = 1.0, upper: float = 99.5) -> np.ndarray:
    """Normalize a 3D timepoint by percentiles without assuming global video statistics."""

    low, high = np.percentile(volume, [lower, upper])
    if high <= low:
        return np.zeros_like(volume, dtype=np.float32)
    normalized = (volume.astype(np.float32) - low) / (high - low)
    return np.clip(normalized, 0.0, 1.0)


def detections_from_components(
    sample_id: str,
    t: int,
    labels: np.ndarray,
    image: np.ndarray,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    min_volume: int = 1,
) -> list[Detection]:
    """Convert connected-component labels to detections without per-label rescans."""

    flat_labels = labels.ravel()
    if flat_labels.size == 0:
        return []

    max_label = int(flat_labels.max())
    if max_label <= 0:
        return []

    z_idx, y_idx, x_idx = np.nonzero(labels)
    component_labels = labels[z_idx, y_idx, x_idx].astype(np.int64)
    counts = np.bincount(component_labels, minlength=max_label + 1)
    valid_labels = [
        int(label_id)
        for label_id in range(1, max_label + 1)
        if counts[label_id] >= min_volume
    ]
    if not valid_labels:
        return []

    z_sums = np.bincount(component_labels, weights=z_idx, minlength=max_label + 1)
    y_sums = np.bincount(component_labels, weights=y_idx, minlength=max_label + 1)
    x_sums = np.bincount(component_labels, weights=x_idx, minlength=max_label + 1)
    values = image[z_idx, y_idx, x_idx].astype(float)
    intensity_sums = np.bincount(component_labels, weights=values, minlength=max_label + 1)

    try:
        from scipy import ndimage

        intensity_maxima = ndimage.maximum(image, labels=labels, index=valid_labels)
    except ImportError:  # pragma: no cover - scipy is required by the caller.
        intensity_maxima = [float(values[component_labels == label_id].max()) for label_id in valid_labels]

    detections: list[Detection] = []
    for label_id, intensity_max in zip(valid_labels, intensity_maxima, strict=True):
        count = int(counts[label_id])
        z = float(z_sums[label_id] / count)
        y = float(y_sums[label_id] / count)
        x = float(x_sums[label_id] / count)
        z_um, y_um, x_um = voxel_scale.voxel_to_um(z, y, x)
        detections.append(
            Detection(
                node_id=f"{sample_id}:t{t}:c{label_id}",
                sample_id=sample_id,
                t=t,
                z=z,
                y=y,
                x=x,
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
                intensity_mean=float(intensity_sums[label_id] / count),
                intensity_max=float(intensity_max),
                component_volume=count,
                detection_confidence=None,
            )
        )
    return detections

def threshold_connected_components(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.65,
    min_volume: int = 4,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
) -> list[Detection]:
    """Small CPU baseline: percentile normalize, threshold, label, and centroid components."""

    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - exercised when scipy is absent.
        raise RuntimeError("scipy is required for threshold_connected_components") from exc

    normalized = robust_normalize(volume)
    labels, _ = ndimage.label(normalized >= threshold)
    return detections_from_components(
        sample_id=sample_id,
        t=t,
        labels=labels,
        image=volume,
        voxel_scale=voxel_scale,
        min_volume=min_volume,
    )


def threshold_local_maxima(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.65,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
) -> list[Detection]:
    """Detect candidate cell centers as local intensity peaks above a threshold.

    This avoids treating a merged foreground island as one cell. It is still a
    simple calibration detector: peaks are candidate centers, not confirmed cell
    identities.
    """

    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - exercised when scipy is absent.
        raise RuntimeError("scipy is required for threshold_local_maxima") from exc

    normalized = robust_normalize(volume, upper=99.9)
    size = tuple(2 * max(0, int(radius)) + 1 for radius in min_distance_voxels)
    peak_source = volume.astype(np.float32)
    local_max = ndimage.maximum_filter(peak_source, size=size, mode="nearest")
    peak_mask = (normalized >= threshold) & (peak_source == local_max)
    coords = np.argwhere(peak_mask)
    if coords.size == 0:
        return []

    confidences = normalized[peak_mask]
    raw_values = volume[peak_mask]
    order = np.argsort(confidences)[::-1]
    if max_detections is not None:
        order = order[: int(max_detections)]

    detections: list[Detection] = []
    for output_idx, coord_idx in enumerate(order, start=1):
        z, y, x = coords[int(coord_idx)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = voxel_scale.voxel_to_um(zf, yf, xf)
        raw_value = float(raw_values[int(coord_idx)])
        detections.append(
            Detection(
                node_id=f"{sample_id}:t{t}:p{output_idx}",
                sample_id=sample_id,
                t=t,
                z=zf,
                y=yf,
                x=xf,
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
                intensity_mean=raw_value,
                intensity_max=raw_value,
                component_volume=1,
                detection_confidence=float(confidences[int(coord_idx)]),
            )
        )

    detections.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return detections


def threshold_local_maxima_cfar(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 7, 7),
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    cfar_k_sigma: float = 1.0,
) -> list[Detection]:
    """Detect peaks with a simple cell-averaging CFAR-like adaptive threshold.

    The detector uses robust normalized intensity as a bounded signal scale.
    A local background box-ring (training box minus guard box) estimates
    mean and variance per voxel. Peaks are kept only when they exceed both:

    - a global floor ``threshold`` (safety bound)
    - a local adaptive threshold ``bg_mean + cfar_k_sigma * bg_std``

    This is an uncertainty-aware detection aid, not evidence of biological truth.
    """

    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - exercised when scipy is absent.
        raise RuntimeError("scipy is required for threshold_local_maxima_cfar") from exc

    normalized = robust_normalize(volume, upper=99.9)
    peak_source = volume.astype(np.float32)
    peak_size = tuple(2 * max(0, int(radius)) + 1 for radius in min_distance_voxels)
    local_max = ndimage.maximum_filter(peak_source, size=peak_size, mode="nearest")
    peak_mask = peak_source == local_max

    background_mean, background_std = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
    )

    adaptive_threshold = background_mean + float(cfar_k_sigma) * background_std
    keep_mask = peak_mask & (normalized >= float(threshold)) & (normalized >= adaptive_threshold)
    coords = np.argwhere(keep_mask)
    if coords.size == 0:
        return []

    confidences = normalized[keep_mask]
    adaptive_at_peaks = adaptive_threshold[keep_mask]
    margin_confidences = np.maximum(
        0.0,
        (confidences - adaptive_at_peaks) / np.maximum(adaptive_at_peaks, 1e-6),
    )
    raw_values = volume[keep_mask]
    order = np.argsort(margin_confidences)[::-1]
    if max_detections is not None:
        order = order[: int(max_detections)]

    detections: list[Detection] = []
    for output_idx, coord_idx in enumerate(order, start=1):
        z, y, x = coords[int(coord_idx)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = voxel_scale.voxel_to_um(zf, yf, xf)
        raw_value = float(raw_values[int(coord_idx)])
        confidence = _cfar_margin_confidence(
            float(confidences[int(coord_idx)]),
            float(adaptive_at_peaks[int(coord_idx)]),
        )
        detections.append(
            Detection(
                node_id=f"{sample_id}:t{t}:cf{output_idx}",
                sample_id=sample_id,
                t=t,
                z=zf,
                y=yf,
                x=xf,
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
                intensity_mean=raw_value,
                intensity_max=raw_value,
                component_volume=1,
                detection_confidence=confidence,
            )
        )

    detections.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return detections


def threshold_local_maxima_cfar_sidelobe(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 7, 7),
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    cfar_k_sigma: float = 1.0,
    sidelobe_radius_voxels: tuple[int, int, int] = (0, 2, 2),
    sidelobe_floor_ratio: float = 0.85,
) -> list[Detection]:
    """CFAR peaks with side-lobe-style suppression of nearby weaker neighbors.

    Nearby peaks are suppressed if they fall within ``sidelobe_radius_voxels``
    of a stronger kept peak and their confidence is below
    ``stronger_confidence * sidelobe_floor_ratio``.
    """

    detections = threshold_local_maxima_cfar(
        sample_id=sample_id,
        t=t,
        volume=volume,
        threshold=threshold,
        min_distance_voxels=min_distance_voxels,
        voxel_scale=voxel_scale,
        max_detections=max_detections,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
        cfar_k_sigma=cfar_k_sigma,
    )
    if not detections:
        return []

    kept = _sidelobe_suppress_detections(
        detections,
        sidelobe_radius_voxels=sidelobe_radius_voxels,
        sidelobe_floor_ratio=sidelobe_floor_ratio,
    )

    kept.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return kept


def _cfar_background_stats_box(
    normalized: np.ndarray,
    *,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - exercised when scipy is absent.
        raise RuntimeError("scipy is required for CFAR background estimation") from exc

    tz, ty, tx = (max(0, int(v)) for v in cfar_training_radius_voxels)
    gz, gy, gx = (max(0, int(v)) for v in cfar_guard_radius_voxels)
    if gz > tz or gy > ty or gx > tx:
        raise ValueError("CFAR guard radius must not exceed training radius")

    training_size = (2 * tz + 1, 2 * ty + 1, 2 * tx + 1)
    guard_size = (2 * gz + 1, 2 * gy + 1, 2 * gx + 1)
    training_count = float(np.prod(training_size))
    guard_count = float(np.prod(guard_size))
    ring_count = training_count - guard_count
    if ring_count <= 0.0:
        raise ValueError("CFAR ring must contain at least one training voxel")

    signal = normalized.astype(np.float32, copy=False)
    signal_sq = signal * signal

    mean_training = ndimage.uniform_filter(signal, size=training_size, mode="nearest")
    mean_guard = ndimage.uniform_filter(signal, size=guard_size, mode="nearest")
    mean_sq_training = ndimage.uniform_filter(signal_sq, size=training_size, mode="nearest")
    mean_sq_guard = ndimage.uniform_filter(signal_sq, size=guard_size, mode="nearest")

    sum_training = mean_training * training_count
    sum_guard = mean_guard * guard_count
    sum_sq_training = mean_sq_training * training_count
    sum_sq_guard = mean_sq_guard * guard_count

    background_mean = (sum_training - sum_guard) / ring_count
    background_sq_mean = (sum_sq_training - sum_sq_guard) / ring_count
    background_var = np.clip(background_sq_mean - background_mean * background_mean, 0.0, None)
    background_std = np.sqrt(background_var)
    return background_mean, background_std


def _sidelobe_suppress_detections(
    detections: list[Detection],
    *,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_floor_ratio: float,
) -> list[Detection]:
    ordered = sorted(
        detections,
        key=lambda detection: float(detection.detection_confidence or 0.0),
        reverse=True,
    )
    kept: list[Detection] = []
    rz, ry, rx = (max(0, int(v)) for v in sidelobe_radius_voxels)
    floor_ratio = float(np.clip(sidelobe_floor_ratio, 0.0, 1.0))

    kept_by_voxel: dict[tuple[int, int, int], list[Detection]] = {}
    for detection in ordered:
        confidence = float(detection.detection_confidence or 0.0)
        z0, y0, x0 = int(round(detection.z)), int(round(detection.y)), int(round(detection.x))
        suppressed = False
        for z in range(z0 - rz, z0 + rz + 1):
            for y in range(y0 - ry, y0 + ry + 1):
                for x in range(x0 - rx, x0 + rx + 1):
                    for stronger in kept_by_voxel.get((z, y, x), []):
                        stronger_confidence = float(stronger.detection_confidence or 0.0)
                        if confidence >= stronger_confidence * floor_ratio:
                            continue
                        if (
                            abs(detection.z - stronger.z) <= rz
                            and abs(detection.y - stronger.y) <= ry
                            and abs(detection.x - stronger.x) <= rx
                        ):
                            suppressed = True
                            break
                    if suppressed:
                        break
                if suppressed:
                    break
            if suppressed:
                break
        if suppressed:
            continue

        kept.append(detection)
        kept_by_voxel.setdefault((z0, y0, x0), []).append(detection)
    return kept


def _cfar_margin_confidence(signal: float, adaptive_threshold: float) -> float:
    # Emphasize local contrast over absolute intensity so sidelobe suppression
    # compares peaks by CFAR salience, not by global brightness.
    denominator = max(adaptive_threshold, 1e-6)
    return max(0.0, (signal - adaptive_threshold) / denominator)

def _positive_labels(labels: np.ndarray) -> Iterable[int]:
    return (int(label_id) for label_id in np.unique(labels) if label_id > 0)
