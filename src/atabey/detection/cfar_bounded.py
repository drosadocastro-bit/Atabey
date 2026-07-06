"""Experimental bounded-domain CFAR formulations for [0,1] normalized signal.

ISOLATED EXPERIMENTAL MODULE. Nothing in the production/baseline path imports
this file. It exists to explore CFAR threshold formulations that do not break on
a bounded [0,1] signal, after diagnostics confirmed that the multiplicative
CA-CFAR threshold ``alpha * background_mean`` can exceed the signal ceiling and
annihilate all detections on high-background samples (root cause of the
``44b6_0c582fdc`` collapse; see ``docs/V14_DIAGNOSTICS.md``).

Three formulations are provided, all bounded-safe by construction:

- ``alpha_clip``: standard CA-CFAR alpha, but the multiplicative threshold is
  clamped so it can never exceed a ceiling < 1. Cheapest; a bounded-safe patch of
  the existing formula rather than a distributional change.
- ``logit``: map the signal ``[0,1] -> R`` via logit, run a Gaussian-clutter CFAR
  in the unbounded transformed space (``mean + z(pfa) * std`` or ``mean + k*std``),
  then compare in transformed space. Never hits a ceiling.
- ``beta``: model the local background as ``Beta(a, b)`` (naturally bounded on
  [0,1]) via method of moments, and take the threshold as the ``1 - pfa`` quantile
  of that Beta. Distributionally correct for a bounded signal.

Runtime note: background box-ring statistics use a single-pass summed-area-table
(integral image) instead of four ``uniform_filter`` passes, applying the Part 1
diagnostic finding that ``cfar_background_stats`` dominated hybrid runtime. The
expensive per-voxel threshold transforms (Beta ppf in particular) are evaluated
only at candidate peak voxels, not the whole volume.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from atabey.constants import DEFAULT_VOXEL_SCALE_UM, VoxelScale
from atabey.detection.baseline import _cfar_alpha_from_pfa, _cfar_margin_confidence, robust_normalize
from atabey.types import Detection


BoundedCFARMode = Literal["alpha_clip", "logit", "beta"]

# Signal is robust-normalized to [0, 1]; keep thresholds strictly below the
# ceiling so the brightest peaks can always survive a bounded-safe threshold.
SIGNAL_CEILING = 0.999
_EPS = 1e-6


def _integral_image(arr: np.ndarray) -> np.ndarray:
    """3D summed-area table with a leading zero border on each axis."""

    integral = np.zeros(
        (arr.shape[0] + 1, arr.shape[1] + 1, arr.shape[2] + 1),
        dtype=np.float64,
    )
    integral[1:, 1:, 1:] = arr.astype(np.float64, copy=False).cumsum(0).cumsum(1).cumsum(2)
    return integral


def _box_sums_from_integral(integral: np.ndarray, rz: int, ry: int, rx: int) -> np.ndarray:
    """Vectorized clamped box sums for every voxel via 8-term inclusion-exclusion.

    Borders use a shrinking window (sum over the valid in-bounds region only),
    which is border-correct for a bounded signal and avoids the edge-replication
    mass that ``uniform_filter(mode="nearest")`` introduces.
    """

    z_dim = integral.shape[0] - 1
    y_dim = integral.shape[1] - 1
    x_dim = integral.shape[2] - 1

    z = np.arange(z_dim)
    y = np.arange(y_dim)
    x = np.arange(x_dim)

    zl = np.clip(z - rz, 0, z_dim)
    zu = np.clip(z + rz + 1, 0, z_dim)
    yl = np.clip(y - ry, 0, y_dim)
    yu = np.clip(y + ry + 1, 0, y_dim)
    xl = np.clip(x - rx, 0, x_dim)
    xu = np.clip(x + rx + 1, 0, x_dim)

    return (
        integral[np.ix_(zu, yu, xu)]
        - integral[np.ix_(zl, yu, xu)]
        - integral[np.ix_(zu, yl, xu)]
        - integral[np.ix_(zu, yu, xl)]
        + integral[np.ix_(zl, yl, xu)]
        + integral[np.ix_(zl, yu, xl)]
        + integral[np.ix_(zu, yl, xl)]
        - integral[np.ix_(zl, yl, xl)]
    )


def background_ring_stats_sat(
    signal: np.ndarray,
    *,
    training_radius_voxels: tuple[int, int, int],
    guard_radius_voxels: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Box-ring background mean, variance, and per-voxel ring count via SAT.

    Returns ``(mean, variance, ring_count)`` where the ring is the training box
    minus the guard box. This is the single-pass optimization of the four
    ``uniform_filter`` passes used by the production estimator.
    """

    tz, ty, tx = (max(0, int(v)) for v in training_radius_voxels)
    gz, gy, gx = (max(0, int(v)) for v in guard_radius_voxels)
    if gz > tz or gy > ty or gx > tx:
        raise ValueError("CFAR guard radius must not exceed training radius")

    signal = signal.astype(np.float64, copy=False)
    ones = np.ones_like(signal, dtype=np.float64)

    integral_signal = _integral_image(signal)
    integral_signal_sq = _integral_image(signal * signal)
    integral_ones = _integral_image(ones)

    train_sum = _box_sums_from_integral(integral_signal, tz, ty, tx)
    guard_sum = _box_sums_from_integral(integral_signal, gz, gy, gx)
    train_sum_sq = _box_sums_from_integral(integral_signal_sq, tz, ty, tx)
    guard_sum_sq = _box_sums_from_integral(integral_signal_sq, gz, gy, gx)
    train_count = _box_sums_from_integral(integral_ones, tz, ty, tx)
    guard_count = _box_sums_from_integral(integral_ones, gz, gy, gx)

    ring_sum = train_sum - guard_sum
    ring_sum_sq = train_sum_sq - guard_sum_sq
    ring_count = train_count - guard_count
    ring_count_safe = np.maximum(ring_count, 1.0)

    mean = ring_sum / ring_count_safe
    mean_sq = ring_sum_sq / ring_count_safe
    variance = np.clip(mean_sq - mean * mean, 0.0, None)
    return mean, variance, ring_count


def _threshold_alpha_clip(
    mean_at_peaks: np.ndarray,
    *,
    pfa: float,
    ring_count: float,
    ceiling: float,
) -> np.ndarray:
    """CA-CFAR alpha threshold clamped so it can never exceed the ceiling."""

    alpha = _cfar_alpha_from_pfa(float(pfa), float(ring_count))
    raw_threshold = mean_at_peaks * alpha
    return np.minimum(raw_threshold, float(ceiling))


def _threshold_logit(
    logit_mean_at_peaks: np.ndarray,
    logit_std_at_peaks: np.ndarray,
    *,
    pfa: float | None,
    k_sigma: float | None,
) -> np.ndarray:
    """Gaussian-clutter CFAR threshold in unbounded logit space, mapped back.

    Returns the threshold on the normalized [0,1] scale (sigmoid of the logit
    threshold), which is always < 1, so the brightest peaks can survive.
    """

    if pfa is not None:
        from scipy.stats import norm

        z_score = float(norm.isf(float(pfa)))
    elif k_sigma is not None:
        z_score = float(k_sigma)
    else:
        raise ValueError("logit threshold requires either pfa or k_sigma")

    logit_threshold = logit_mean_at_peaks + z_score * logit_std_at_peaks
    # Inverse logit (sigmoid) maps back to the bounded [0,1] domain.
    return 1.0 / (1.0 + np.exp(-logit_threshold))


def _threshold_beta(
    mean_at_peaks: np.ndarray,
    var_at_peaks: np.ndarray,
    *,
    pfa: float,
) -> np.ndarray:
    """Beta(a,b) method-of-moments background model; threshold at 1 - pfa quantile."""

    from scipy.stats import beta as beta_dist

    mean = np.clip(mean_at_peaks, _EPS, 1.0 - _EPS)
    max_var = mean * (1.0 - mean)
    var = np.clip(var_at_peaks, _EPS * _EPS, None)

    # Where the background is over-dispersed beyond Beta support, fall back to a
    # bounded-safe ceiling threshold rather than producing invalid parameters.
    valid = var < (max_var - _EPS)
    common = np.where(valid, max_var / np.maximum(var, _EPS) - 1.0, 0.0)
    a = np.clip(mean * common, _EPS, None)
    b = np.clip((1.0 - mean) * common, _EPS, None)

    threshold = np.empty_like(mean)
    if np.any(valid):
        threshold[valid] = beta_dist.isf(float(pfa), a[valid], b[valid])
    threshold[~valid] = SIGNAL_CEILING
    return np.clip(threshold, 0.0, SIGNAL_CEILING)


def detect_bounded_cfar(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    *,
    mode: BoundedCFARMode,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 5, 5),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    training_radius_voxels: tuple[int, int, int] = (1, 6, 6),
    guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    pfa: float | None = 1e-3,
    k_sigma: float | None = None,
    ceiling: float = SIGNAL_CEILING,
) -> list[Detection]:
    """Bounded-domain CFAR peak detector (experimental).

    Mirrors the structure of ``threshold_local_maxima_cfar`` but replaces the
    unbounded multiplicative threshold with a bounded-safe formulation and only
    evaluates the threshold transform at candidate peak voxels.
    """

    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - scipy is required by the caller.
        raise RuntimeError("scipy is required for bounded CFAR detection") from exc

    normalized = robust_normalize(volume, upper=99.9).astype(np.float64, copy=False)
    peak_source = volume.astype(np.float32)
    peak_size = tuple(2 * max(0, int(radius)) + 1 for radius in min_distance_voxels)
    local_max = ndimage.maximum_filter(peak_source, size=peak_size, mode="nearest")
    peak_mask = (peak_source == local_max) & (normalized >= float(threshold))
    coords = np.argwhere(peak_mask)
    if coords.size == 0:
        return []

    mean, variance, ring_count = background_ring_stats_sat(
        normalized,
        training_radius_voxels=training_radius_voxels,
        guard_radius_voxels=guard_radius_voxels,
    )
    representative_ring_count = float(np.median(ring_count[ring_count > 0])) if np.any(ring_count > 0) else 1.0

    zc = coords[:, 0]
    yc = coords[:, 1]
    xc = coords[:, 2]
    peak_norm = normalized[zc, yc, xc]
    mean_at_peaks = mean[zc, yc, xc]

    if mode == "alpha_clip":
        if pfa is None:
            raise ValueError("alpha_clip mode requires pfa")
        threshold_at_peaks = _threshold_alpha_clip(
            mean_at_peaks,
            pfa=float(pfa),
            ring_count=representative_ring_count,
            ceiling=float(ceiling),
        )
    elif mode == "logit":
        clamped = np.clip(normalized, _EPS, 1.0 - _EPS)
        logit_signal = np.log(clamped / (1.0 - clamped))
        logit_mean, logit_var, _ = background_ring_stats_sat(
            logit_signal,
            training_radius_voxels=training_radius_voxels,
            guard_radius_voxels=guard_radius_voxels,
        )
        logit_std = np.sqrt(logit_var)
        threshold_at_peaks = _threshold_logit(
            logit_mean[zc, yc, xc],
            logit_std[zc, yc, xc],
            pfa=(None if pfa is None else float(pfa)),
            k_sigma=(None if k_sigma is None else float(k_sigma)),
        )
    elif mode == "beta":
        if pfa is None:
            raise ValueError("beta mode requires pfa")
        threshold_at_peaks = _threshold_beta(
            mean_at_peaks,
            variance[zc, yc, xc],
            pfa=float(pfa),
        )
    else:
        raise ValueError(f"Unknown bounded CFAR mode: {mode}")

    keep = peak_norm >= threshold_at_peaks
    if not np.any(keep):
        return []

    kept_coords = coords[keep]
    kept_norm = peak_norm[keep]
    kept_threshold = threshold_at_peaks[keep]
    margin = np.maximum(0.0, (kept_norm - kept_threshold) / np.maximum(kept_threshold, _EPS))
    order = np.argsort(margin)[::-1]
    if max_detections is not None:
        order = order[: int(max_detections)]

    detections: list[Detection] = []
    for output_idx, sel in enumerate(order, start=1):
        z, y, x = kept_coords[int(sel)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = voxel_scale.voxel_to_um(zf, yf, xf)
        raw_value = float(volume[int(z), int(y), int(x)])
        confidence = _cfar_margin_confidence(
            float(kept_norm[int(sel)]),
            float(kept_threshold[int(sel)]),
        )
        detections.append(
            Detection(
                node_id=f"{sample_id}:t{t}:bc{output_idx}",
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
