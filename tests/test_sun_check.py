import numpy as np

from atabey.diagnostics.sun_check import audit_sample, estimate_bulk_shift, summarize_frame


def _gaussian_volume(shape=(12, 24, 24), center=(6, 12, 12), sigma=(1.2, 2.0, 2.5)):
    grids = np.indices(shape, dtype=float)
    exponent = sum(((grids[axis] - center[axis]) / sigma[axis]) ** 2 for axis in range(3))
    return (20.0 + 1000.0 * np.exp(-0.5 * exponent)).astype(np.uint16)


def test_summarize_frame_reports_bounded_read_only_proxies():
    volume = _gaussian_volume()
    before = volume.copy()

    result = summarize_frame(volume, t=3, sample_stride=(1, 2, 2), max_compact_peaks=4)

    assert np.array_equal(volume, before)
    assert result.t == 3
    assert result.background_median >= 0
    assert result.snr_proxy > 0
    assert result.compact_peak_count >= 1
    assert result.compact_sigma_z_um is not None
    assert result.saturation_fraction == 0.0


def test_estimate_bulk_shift_recovers_integer_translation_magnitude():
    reference = _gaussian_volume(shape=(16, 32, 32), center=(8, 16, 16))
    moving = np.roll(reference, shift=(2, -3, 4), axis=(0, 1, 2))

    result = estimate_bulk_shift(
        reference,
        moving,
        t_from=0,
        t_to=1,
        voxel_scale_um=(1.0, 1.0, 1.0),
        sample_stride=(1, 1, 1),
    )

    assert np.allclose(
        (result.shift_z_um, result.shift_y_um, result.shift_x_um),
        (-2.0, 3.0, -4.0),
        atol=0.25,
    )
    assert np.isclose(result.shift_magnitude_um, np.sqrt(29.0), atol=0.25)


def test_audit_sample_reads_only_anchor_and_adjacent_frames(monkeypatch):
    class FakeArray:
        shape = (4, 12, 24, 24)

        def __init__(self):
            base = _gaussian_volume()
            self.frames = [np.roll(base, shift=t, axis=2) for t in range(4)]

        def __getitem__(self, index):
            calls.append(int(index))
            return self.frames[index]

    calls = []
    monkeypatch.setattr("atabey.diagnostics.sun_check.open_competition_array", lambda _path: FakeArray())

    report = audit_sample("demo.zarr", anchor_timepoints=(0, 2))

    assert calls == [0, 1, 2, 3]
    assert report.sample_id == "demo"
    assert report.sampled_timepoints == (0, 2)
    assert len(report.frame_metrics) == 2
    assert len(report.drift_metrics) == 2
    assert report.median_drift_um >= 0
