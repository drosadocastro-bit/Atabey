"""Tests for the experimental bounded-domain CFAR module.

These guard the two properties the reformulation must deliver:
1. The SAT background estimator matches a brute-force box-ring reference.
2. Every bounded formulation avoids zero-node collapse on a high-background,
   bounded [0,1] volume (the ``44b6_0c582fdc`` failure mode).
"""

from __future__ import annotations

import numpy as np

from atabey.detection.cfar_bounded import (
    SIGNAL_CEILING,
    background_ring_stats_sat,
    detect_bounded_cfar,
)


def _brute_force_ring_mean(
    signal: np.ndarray,
    training: tuple[int, int, int],
    guard: tuple[int, int, int],
) -> np.ndarray:
    tz, ty, tx = training
    gz, gy, gx = guard
    z_dim, y_dim, x_dim = signal.shape
    out = np.zeros_like(signal, dtype=np.float64)
    for z in range(z_dim):
        for y in range(y_dim):
            for x in range(x_dim):
                z0, z1 = max(0, z - tz), min(z_dim, z + tz + 1)
                y0, y1 = max(0, y - ty), min(y_dim, y + ty + 1)
                x0, x1 = max(0, x - tx), min(x_dim, x + tx + 1)
                train_sum = signal[z0:z1, y0:y1, x0:x1].sum()
                train_count = (z1 - z0) * (y1 - y0) * (x1 - x0)
                gz0, gz1 = max(0, z - gz), min(z_dim, z + gz + 1)
                gy0, gy1 = max(0, y - gy), min(y_dim, y + gy + 1)
                gx0, gx1 = max(0, x - gx), min(x_dim, x + gx + 1)
                guard_sum = signal[gz0:gz1, gy0:gy1, gx0:gx1].sum()
                guard_count = (gz1 - gz0) * (gy1 - gy0) * (gx1 - gx0)
                ring_count = train_count - guard_count
                out[z, y, x] = (train_sum - guard_sum) / max(ring_count, 1)
    return out


def test_sat_ring_mean_matches_brute_force() -> None:
    rng = np.random.default_rng(7)
    signal = rng.random((5, 9, 9))
    training = (1, 3, 3)
    guard = (0, 1, 1)

    mean, _, ring_count = background_ring_stats_sat(
        signal, training_radius_voxels=training, guard_radius_voxels=guard
    )
    reference = _brute_force_ring_mean(signal, training, guard)

    np.testing.assert_allclose(mean, reference, rtol=1e-9, atol=1e-9)
    assert np.all(ring_count > 0)


def test_sat_variance_is_nonnegative_and_bounded() -> None:
    rng = np.random.default_rng(11)
    signal = rng.random((4, 8, 8))
    _, variance, _ = background_ring_stats_sat(
        signal, training_radius_voxels=(1, 3, 3), guard_radius_voxels=(0, 1, 1)
    )
    assert np.all(variance >= 0.0)
    # Variance of a [0,1] signal cannot exceed 0.25.
    assert np.all(variance <= 0.25 + 1e-9)


def _high_background_collapse_volume() -> np.ndarray:
    """Bounded volume whose background mean * CA-CFAR alpha exceeds 1.0."""

    rng = np.random.default_rng(3)
    volume = rng.uniform(0.30, 0.55, size=(6, 40, 40)).astype(np.float32)
    # A handful of bright cells that must survive any bounded-safe threshold.
    for z, y, x in [(2, 10, 10), (3, 25, 15), (4, 15, 30), (2, 30, 30)]:
        volume[z, y, x] = 1.0
        volume[z, y - 1 : y + 2, x - 1 : x + 2] = np.maximum(
            volume[z, y - 1 : y + 2, x - 1 : x + 2], 0.9
        )
    return volume


def test_bounded_modes_avoid_zero_node_collapse() -> None:
    volume = _high_background_collapse_volume()
    for mode in ("alpha_clip", "logit", "beta"):
        detections = detect_bounded_cfar(
            "collapse_probe",
            0,
            volume,
            mode=mode,
            pfa=1e-3,
            max_detections=50,
        )
        assert detections, f"mode {mode} collapsed to zero detections"


def test_logit_mode_accepts_k_sigma() -> None:
    volume = _high_background_collapse_volume()
    detections = detect_bounded_cfar(
        "collapse_probe",
        0,
        volume,
        mode="logit",
        pfa=None,
        k_sigma=1.1,
        max_detections=50,
    )
    assert detections


def test_bounded_confidence_within_unit_interval() -> None:
    volume = _high_background_collapse_volume()
    detections = detect_bounded_cfar(
        "collapse_probe", 0, volume, mode="beta", pfa=1e-3, max_detections=50
    )
    for detection in detections:
        assert detection.detection_confidence is not None
        assert 0.0 <= detection.detection_confidence <= 1.0


def test_signal_ceiling_is_below_one() -> None:
    assert SIGNAL_CEILING < 1.0
