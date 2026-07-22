from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from atabey.io.zarr_reader import open_competition_array, read_timepoint, sample_id_from_zarr_path


DEFAULT_VOXEL_SCALE_UM = (1.625, 0.40625, 0.40625)


@dataclass(frozen=True)
class FrameSunCheck:
    t: int
    background_median: float
    background_mad: float
    q10: float
    q50: float
    q90: float
    q99: float
    snr_proxy: float
    z_profile_spread: float
    xy_shading_spread: float
    saturation_fraction: float
    compact_peak_count: int
    compact_sigma_z_um: float | None
    compact_sigma_y_um: float | None
    compact_sigma_x_um: float | None


@dataclass(frozen=True)
class DriftSunCheck:
    t_from: int
    t_to: int
    shift_z_um: float
    shift_y_um: float
    shift_x_um: float
    shift_magnitude_um: float


@dataclass(frozen=True)
class SampleSunCheck:
    sample_id: str
    shape: tuple[int, ...]
    sampled_timepoints: tuple[int, ...]
    frame_metrics: tuple[FrameSunCheck, ...]
    drift_metrics: tuple[DriftSunCheck, ...]
    median_background: float
    background_temporal_spread: float
    median_snr_proxy: float
    median_z_profile_spread: float
    median_xy_shading_spread: float
    max_saturation_fraction: float
    median_compact_sigma_z_um: float | None
    median_compact_sigma_y_um: float | None
    median_compact_sigma_x_um: float | None
    median_drift_um: float
    p90_drift_um: float
    q90_end_to_start_ratio: float


def default_anchor_timepoints(total_timepoints: int) -> tuple[int, ...]:
    """Return five anchors that each have an adjacent frame for drift estimation."""

    if total_timepoints <= 1:
        return (0,)
    last_start = total_timepoints - 2
    anchors = [0, total_timepoints // 4, total_timepoints // 2, (3 * total_timepoints) // 4, last_start]
    return tuple(dict.fromkeys(min(max(0, int(t)), last_start) for t in anchors))


def summarize_frame(
    volume: np.ndarray,
    *,
    t: int,
    voxel_scale_um: tuple[float, float, float] = DEFAULT_VOXEL_SCALE_UM,
    sample_stride: tuple[int, int, int] = (2, 4, 4),
    max_compact_peaks: int = 32,
) -> FrameSunCheck:
    """Measure bead-free radiometric and footprint proxies for one volume.

    The lower half of a sparse voxel lattice is treated as a background proxy.
    Compact bright objects are biological structures, not sub-resolution PSF beads.
    """

    data = np.asarray(volume)
    if data.ndim != 3:
        raise ValueError(f"Expected a 3D volume, got shape {data.shape}")
    stride = tuple(max(1, int(value)) for value in sample_stride)
    sampled = data[:: stride[0], :: stride[1], :: stride[2]].astype(np.float64, copy=False)
    q10, q50, q90, q99 = (float(value) for value in np.percentile(sampled, [10, 50, 90, 99]))
    lower = sampled[sampled <= q50]
    background = float(np.median(lower)) if lower.size else q10
    background_mad = float(np.median(np.abs(lower - background))) if lower.size else 0.0
    robust_noise = max(1e-9, 1.4826 * background_mad)
    snr_proxy = float((q90 - background) / robust_noise)

    z_profile = np.median(sampled, axis=(1, 2))
    xy_profile = np.median(sampled, axis=0)
    z_spread = _relative_percentile_spread(z_profile)
    xy_spread = _relative_percentile_spread(xy_profile)

    if np.issubdtype(data.dtype, np.integer):
        saturation_level = np.iinfo(data.dtype).max
        saturation_fraction = float(np.mean(sampled >= saturation_level))
    else:
        saturation_fraction = 0.0

    footprints = _compact_peak_footprints(
        data,
        voxel_scale_um=voxel_scale_um,
        max_peaks=max_compact_peaks,
    )
    return FrameSunCheck(
        t=int(t),
        background_median=background,
        background_mad=background_mad,
        q10=q10,
        q50=q50,
        q90=q90,
        q99=q99,
        snr_proxy=snr_proxy,
        z_profile_spread=z_spread,
        xy_shading_spread=xy_spread,
        saturation_fraction=saturation_fraction,
        compact_peak_count=len(footprints),
        compact_sigma_z_um=_median_axis(footprints, 0),
        compact_sigma_y_um=_median_axis(footprints, 1),
        compact_sigma_x_um=_median_axis(footprints, 2),
    )


def estimate_bulk_shift(
    reference: np.ndarray,
    moving: np.ndarray,
    *,
    t_from: int,
    t_to: int,
    voxel_scale_um: tuple[float, float, float] = DEFAULT_VOXEL_SCALE_UM,
    sample_stride: tuple[int, int, int] = (2, 4, 4),
) -> DriftSunCheck:
    """Estimate an integer-grid phase-correlation shift as a bulk-motion proxy."""

    if np.shape(reference) != np.shape(moving):
        raise ValueError("Reference and moving volumes must have the same shape")
    stride = tuple(max(1, int(value)) for value in sample_stride)
    left = _phase_source(np.asarray(reference)[:: stride[0], :: stride[1], :: stride[2]])
    right = _phase_source(np.asarray(moving)[:: stride[0], :: stride[1], :: stride[2]])
    cross_power = np.fft.fftn(left) * np.conj(np.fft.fftn(right))
    magnitude = np.abs(cross_power)
    cross_power /= np.where(magnitude > 1e-12, magnitude, 1.0)
    correlation = np.abs(np.fft.ifftn(cross_power))
    peak = np.unravel_index(int(np.argmax(correlation)), left.shape)
    shift_voxels = []
    for axis, (index, size, step) in enumerate(zip(peak, left.shape, stride, strict=True)):
        coordinate = float(index) + _quadratic_peak_offset(correlation, peak, axis)
        if coordinate > size / 2:
            coordinate -= float(size)
        shift_voxels.append(float(coordinate * step))
    shift_um = tuple(
        shift * scale for shift, scale in zip(shift_voxels, voxel_scale_um, strict=True)
    )
    return DriftSunCheck(
        t_from=int(t_from),
        t_to=int(t_to),
        shift_z_um=shift_um[0],
        shift_y_um=shift_um[1],
        shift_x_um=shift_um[2],
        shift_magnitude_um=float(np.linalg.norm(shift_um)),
    )


def audit_sample(
    sample_path: str | Path,
    *,
    anchor_timepoints: tuple[int, ...] | None = None,
    voxel_scale_um: tuple[float, float, float] = DEFAULT_VOXEL_SCALE_UM,
) -> SampleSunCheck:
    """Run the read-only Sun Check proxy on sparse adjacent-frame pairs."""

    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    anchors = anchor_timepoints or default_anchor_timepoints(total_timepoints)
    frames: list[FrameSunCheck] = []
    drifts: list[DriftSunCheck] = []
    for t in anchors:
        t = min(max(0, int(t)), max(0, total_timepoints - 1))
        current = np.asarray(read_timepoint(array, t))
        frames.append(summarize_frame(current, t=t, voxel_scale_um=voxel_scale_um))
        if t + 1 < total_timepoints:
            adjacent = np.asarray(read_timepoint(array, t + 1))
            drifts.append(
                estimate_bulk_shift(
                    current,
                    adjacent,
                    t_from=t,
                    t_to=t + 1,
                    voxel_scale_um=voxel_scale_um,
                )
            )

    q90_values = [frame.q90 for frame in frames]
    return SampleSunCheck(
        sample_id=sample_id_from_zarr_path(sample_path),
        shape=tuple(int(value) for value in array.shape),
        sampled_timepoints=tuple(frame.t for frame in frames),
        frame_metrics=tuple(frames),
        drift_metrics=tuple(drifts),
        median_background=float(median(frame.background_median for frame in frames)),
        background_temporal_spread=_relative_percentile_spread(
            np.asarray([frame.background_median for frame in frames], dtype=float)
        ),
        median_snr_proxy=float(median(frame.snr_proxy for frame in frames)),
        median_z_profile_spread=float(median(frame.z_profile_spread for frame in frames)),
        median_xy_shading_spread=float(median(frame.xy_shading_spread for frame in frames)),
        max_saturation_fraction=max(frame.saturation_fraction for frame in frames),
        median_compact_sigma_z_um=_optional_median(frame.compact_sigma_z_um for frame in frames),
        median_compact_sigma_y_um=_optional_median(frame.compact_sigma_y_um for frame in frames),
        median_compact_sigma_x_um=_optional_median(frame.compact_sigma_x_um for frame in frames),
        median_drift_um=float(median(drift.shift_magnitude_um for drift in drifts)) if drifts else 0.0,
        p90_drift_um=float(np.percentile([drift.shift_magnitude_um for drift in drifts], 90)) if drifts else 0.0,
        q90_end_to_start_ratio=float(q90_values[-1] / q90_values[0]) if q90_values and q90_values[0] else 1.0,
    )


def _phase_source(volume: np.ndarray) -> np.ndarray:
    data = volume.astype(np.float64, copy=False)
    low, high = np.percentile(data, [1, 99])
    if high <= low:
        return np.zeros_like(data)
    return np.clip((data - low) / (high - low), 0.0, 1.0) - 0.5


def _quadratic_peak_offset(correlation: np.ndarray, peak: tuple[int, ...], axis: int) -> float:
    left_index = list(peak)
    right_index = list(peak)
    left_index[axis] = (left_index[axis] - 1) % correlation.shape[axis]
    right_index[axis] = (right_index[axis] + 1) % correlation.shape[axis]
    left = float(correlation[tuple(left_index)])
    center = float(correlation[peak])
    right = float(correlation[tuple(right_index)])
    denominator = left - 2.0 * center + right
    if abs(denominator) <= 1e-12:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))


def _relative_percentile_spread(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    center = float(np.median(data))
    p10, p90 = np.percentile(data, [10, 90])
    return float((p90 - p10) / max(abs(center), 1e-9))


def _compact_peak_footprints(
    volume: np.ndarray,
    *,
    voxel_scale_um: tuple[float, float, float],
    max_peaks: int,
) -> list[tuple[float, float, float]]:
    if max_peaks <= 0:
        return []
    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - project dependency.
        raise RuntimeError("scipy is required for compact-object footprint proxies") from exc

    source = volume.astype(np.float32, copy=False)
    threshold = float(np.percentile(source[::2, ::4, ::4], 99.5))
    maxima = source == ndimage.maximum_filter(source, size=(3, 7, 7), mode="nearest")
    coords = np.argwhere(maxima & (source >= threshold))
    if not coords.size:
        return []
    order = np.argsort(source[tuple(coords.T)])[::-1]
    selected: list[np.ndarray] = []
    radii = np.asarray((2, 5, 5), dtype=int)
    for index in order:
        coord = coords[int(index)]
        if np.any(coord - radii < 0) or np.any(coord + radii >= np.asarray(source.shape)):
            continue
        if any(np.all(np.abs(coord - previous) <= radii) for previous in selected):
            continue
        selected.append(coord)
        if len(selected) >= max_peaks:
            break

    footprints: list[tuple[float, float, float]] = []
    for coord in selected:
        slices = tuple(
            slice(int(axis - radius), int(axis + radius + 1))
            for axis, radius in zip(coord, radii, strict=True)
        )
        patch = source[slices].astype(np.float64, copy=False)
        weights = np.maximum(patch - float(np.percentile(patch, 10)), 0.0)
        if float(weights.sum()) <= 0:
            continue
        grids = np.indices(patch.shape, dtype=float)
        sigmas: list[float] = []
        for axis, scale in enumerate(voxel_scale_um):
            mean_axis = float(np.sum(grids[axis] * weights) / weights.sum())
            variance = float(np.sum(((grids[axis] - mean_axis) ** 2) * weights) / weights.sum())
            sigmas.append(float(np.sqrt(max(0.0, variance)) * scale))
        footprints.append(tuple(sigmas))
    return footprints


def _median_axis(values: list[tuple[float, float, float]], axis: int) -> float | None:
    return float(median(value[axis] for value in values)) if values else None


def _optional_median(values: Any) -> float | None:
    present = [float(value) for value in values if value is not None]
    return float(median(present)) if present else None
