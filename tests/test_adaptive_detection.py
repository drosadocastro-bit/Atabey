import numpy as np

from atabey.detection.adaptive import (
    ForegroundProfile,
    choose_adaptive_baseline_settings,
    profile_sample_foreground,
)


class FakeArray:
    shape = (5, 4, 8, 8)

    def __init__(self):
        compact = np.zeros((4, 8, 8), dtype=np.uint16)
        compact[1, 2, 2] = 100
        compact[2, 5, 5] = 120
        merged = np.zeros((4, 8, 8), dtype=np.uint16)
        merged[:, 1:7, 1:7] = 100
        self.frames = [compact, merged, compact, merged, compact]

    def __getitem__(self, index):
        return self.frames[index]


def test_choose_adaptive_settings_uses_components_for_clean_foreground():
    profile = ForegroundProfile(
        sampled_timepoints=(0, 25, 50, 75, 99),
        median_largest_component_voxels=6000,
        median_foreground_fraction=0.015,
        median_component_count=50,
        median_kept_component_count=30,
    )

    settings = choose_adaptive_baseline_settings(profile)

    assert settings.detector == "components"
    assert settings.link_strategy == "greedy"
    assert settings.max_link_distance_um == 7.0
    assert "clean foreground" in settings.reason


def test_choose_adaptive_settings_uses_local_maxima_for_merged_foreground():
    profile = ForegroundProfile(
        sampled_timepoints=(0, 25, 50, 75, 99),
        median_largest_component_voxels=250000,
        median_foreground_fraction=0.08,
        median_component_count=400,
        median_kept_component_count=100,
    )

    settings = choose_adaptive_baseline_settings(profile)

    assert settings.detector == "local_maxima"
    assert settings.link_strategy == "motion_mutual_latent"
    assert settings.max_link_distance_um == 9.0
    assert settings.peak_min_distance_voxels == (1, 5, 5)
    assert "merged foreground" in settings.reason


def test_profile_sample_foreground_reads_default_timepoint_anchors(monkeypatch):
    calls = []
    fake = FakeArray()

    def fake_open_competition_array(path):
        return fake

    def fake_read_timepoint(array, t):
        calls.append(t)
        return array[t]

    monkeypatch.setattr("atabey.detection.adaptive.open_competition_array", fake_open_competition_array)
    monkeypatch.setattr("atabey.detection.adaptive.read_timepoint", fake_read_timepoint)

    profile = profile_sample_foreground("demo.zarr", threshold=0.5, min_volume=1)

    assert calls == [0, 1, 2, 3, 4]
    assert profile.sampled_timepoints == (0, 1, 2, 3, 4)
    assert profile.median_largest_component_voxels > 0
    assert profile.median_foreground_fraction > 0
