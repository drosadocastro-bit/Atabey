from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

import numpy as np

from atabey.baseline import DetectorName
from atabey.detection.baseline import robust_normalize
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.nearest_neighbor import LinkStrategy


@dataclass(frozen=True)
class ForegroundProfile:
    sampled_timepoints: tuple[int, ...]
    median_largest_component_voxels: float
    median_foreground_fraction: float
    median_component_count: float
    median_kept_component_count: float


@dataclass(frozen=True)
class AdaptiveBaselineSettings:
    detector: DetectorName
    threshold: float
    min_volume: int
    peak_min_distance_voxels: tuple[int, int, int]
    link_strategy: LinkStrategy
    max_link_distance_um: float
    reason: str


def profile_sample_foreground(
    sample_path: str | Path,
    *,
    threshold: float = 0.65,
    min_volume: int = 2,
    sample_timepoints: tuple[int, ...] | None = None,
) -> ForegroundProfile:
    """Profile thresholded foreground from a few image timepoints only."""

    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - exercised when scipy is absent.
        raise RuntimeError("scipy is required for adaptive foreground profiling") from exc

    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    timepoints = sample_timepoints or _default_timepoints(total_timepoints)
    largest_components: list[int] = []
    foreground_fractions: list[float] = []
    component_counts: list[int] = []
    kept_component_counts: list[int] = []

    for t in timepoints:
        volume = read_timepoint(array, min(max(0, int(t)), total_timepoints - 1))
        normalized = robust_normalize(volume)
        mask = normalized >= threshold
        labels, component_count = ndimage.label(mask)
        counts = np.bincount(labels.ravel())[1:]
        largest_components.append(int(counts.max()) if counts.size else 0)
        foreground_fractions.append(float(mask.mean()))
        component_counts.append(int(component_count))
        kept_component_counts.append(int((counts >= min_volume).sum()) if counts.size else 0)

    return ForegroundProfile(
        sampled_timepoints=tuple(timepoints),
        median_largest_component_voxels=float(median(largest_components)),
        median_foreground_fraction=float(median(foreground_fractions)),
        median_component_count=float(median(component_counts)),
        median_kept_component_count=float(median(kept_component_counts)),
    )


def choose_adaptive_baseline_settings(
    profile: ForegroundProfile,
    *,
    merged_component_voxels: int = 100_000,
    merged_foreground_fraction: float = 0.05,
) -> AdaptiveBaselineSettings:
    """Choose a bounded baseline path from image-only foreground structure."""

    if (
        profile.median_largest_component_voxels >= merged_component_voxels
        or profile.median_foreground_fraction >= merged_foreground_fraction
    ):
        return AdaptiveBaselineSettings(
            detector="local_maxima",
            threshold=0.65,
            min_volume=2,
            peak_min_distance_voxels=(1, 5, 5),
            link_strategy="motion_mutual_latent",
            max_link_distance_um=9.0,
            reason=(
                "merged foreground profile: large thresholded components or high foreground "
                "fraction, so use local maxima and strict motion+mutual linking with a bounded "
                "one-frame latent recovery bridge"
            ),
        )

    return AdaptiveBaselineSettings(
        detector="components",
        threshold=0.65,
        min_volume=2,
        peak_min_distance_voxels=(1, 5, 5),
        link_strategy="greedy",
        max_link_distance_um=7.0,
        reason=(
            "clean foreground profile: thresholded components are compact enough for component "
            "centroids and simple greedy linking"
        ),
    )


def choose_settings_for_sample(sample_path: str | Path) -> tuple[ForegroundProfile, AdaptiveBaselineSettings]:
    profile = profile_sample_foreground(sample_path)
    return profile, choose_adaptive_baseline_settings(profile)


def _default_timepoints(total_timepoints: int) -> tuple[int, ...]:
    if total_timepoints <= 1:
        return (0,)
    anchors = [0, total_timepoints // 4, total_timepoints // 2, (3 * total_timepoints) // 4, total_timepoints - 1]
    return tuple(dict.fromkeys(anchors))
