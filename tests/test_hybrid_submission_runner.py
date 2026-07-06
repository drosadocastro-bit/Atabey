from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from atabey.detection.adaptive import ForegroundProfile
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.types import Detection
from scripts import run_hybrid_submission as hybrid_submission


class _FakeArray:
    shape = (3,)


def _make_detections(sample_id: str, t: int, count: int, prefix: str) -> list[Detection]:
    detections: list[Detection] = []
    for idx in range(count):
        detections.append(
            Detection(
                node_id=f"{sample_id}:t{t}:{prefix}{idx}",
                sample_id=sample_id,
                t=t,
                z=0.0,
                y=float(idx),
                x=0.0,
                z_um=0.0,
                y_um=float(idx),
                x_um=0.0,
                detection_confidence=1.0,
            )
        )
    return detections


def test_should_use_cfar_route_respects_policy_gates() -> None:
    merged_profile = ForegroundProfile(
        sampled_timepoints=(0,),
        median_largest_component_voxels=180_000.0,
        median_foreground_fraction=0.11,
        median_component_count=10.0,
        median_kept_component_count=8.0,
    )
    clean_profile = ForegroundProfile(
        sampled_timepoints=(0,),
        median_largest_component_voxels=20_000.0,
        median_foreground_fraction=0.01,
        median_component_count=6.0,
        median_kept_component_count=4.0,
    )

    assert hybrid_submission._should_use_cfar_route(
        profile=merged_profile,
        adaptive_detector="local_maxima",
        cfar_route_policy="merged_6bba_only",
    )
    assert not hybrid_submission._should_use_cfar_route(
        profile=clean_profile,
        adaptive_detector="local_maxima",
        cfar_route_policy="merged_6bba_only",
    )
    assert hybrid_submission._should_use_cfar_route(
        profile=clean_profile,
        adaptive_detector="local_maxima",
        cfar_route_policy="merged_all",
    )
    assert not hybrid_submission._should_use_cfar_route(
        profile=merged_profile,
        adaptive_detector="components",
        cfar_route_policy="merged_all",
    )


def test_cfar_guardrail_falls_back_on_spike(monkeypatch) -> None:
    cfar_calls: list[int] = []
    fallback_calls: list[int] = []

    monkeypatch.setattr(hybrid_submission, "open_competition_array", lambda _: _FakeArray())
    monkeypatch.setattr(hybrid_submission, "read_timepoint", lambda _array, _t: np.zeros((1, 1, 1), dtype=np.uint16))
    monkeypatch.setattr(hybrid_submission, "link_adjacent_timepoints", lambda *args, **kwargs: [])

    def _fake_cfar(sample_id, t, _volume, **_kwargs):
        cfar_calls.append(int(t))
        count = 2 if t < 2 else 10
        return _make_detections(sample_id, int(t), count, "cf")

    def _fake_fallback(sample_id, t, _volume, **_kwargs):
        fallback_calls.append(int(t))
        return _make_detections(sample_id, int(t), 1, "fb")

    monkeypatch.setattr(hybrid_submission, "threshold_local_maxima_cfar_sidelobe", _fake_cfar)
    monkeypatch.setattr(hybrid_submission, "threshold_local_maxima", _fake_fallback)

    graph, spike_fallback_count = hybrid_submission.build_graph_cfar_sidelobe(
        sample_path=Path("demo.zarr"),
        threshold=0.50,
        cfar_training_radius_voxels=(1, 6, 6),
        cfar_guard_radius_voxels=(0, 1, 1),
        cfar_threshold_mode="sigma",
        cfar_k_sigma=1.1,
        cfar_pfa=1e-4,
        sidelobe_mode="isotropic",
        sidelobe_radius_voxels=(1, 12, 12),
        sidelobe_axial_z_radius_voxels=2,
        sidelobe_axial_xy_tolerance_voxels=(1, 1),
        sidelobe_floor_ratio=0.85,
        max_detections_per_timepoint=900,
        guardrail_spike_multiplier=1.5,
        guardrail_min_history=2,
        guardrail_history_window=2,
        guardrail_min_absolute_count=0,
        guardrail_fallback_threshold=0.65,
        guardrail_fallback_max_detections=900,
        link_strategy="motion_mutual",
        max_link_distance_um=9.0,
        max_timepoints=3,
    )

    assert cfar_calls == [0, 1, 2]
    assert fallback_calls == [2]
    assert spike_fallback_count == 1
    assert len(graph.detections) == 5


def test_hybrid_defaults_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_hybrid_submission.py"])
    args = hybrid_submission.parse_args()

    assert args.cfar_threshold == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold
    assert args.cfar_training_radius == "1,6,6"
    assert args.cfar_guard_radius == "0,1,1"
    assert args.cfar_threshold_mode == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode
    assert args.cfar_k_sigma == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma
    assert args.cfar_pfa == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa
    assert args.sidelobe_mode == DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode
    assert args.allow_unsafe_pfa_axial is False
    assert args.sidelobe_radius == "1,12,12"
    assert args.sidelobe_axial_z_radius == DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels
    assert args.sidelobe_axial_xy_tolerance == "1,1"
    assert args.sidelobe_floor == DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio
    assert args.max_detections_per_timepoint == DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint
    assert args.cfar_route_policy == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy
    assert args.cfar_link_strategy == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy
    assert args.cfar_max_link_distance_um == DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um
    assert args.track_quality_shadow is True
    assert args.track_quality_beacon_threshold == 0.75
    assert args.track_quality_min_track_length == 3
    assert args.latent_shadow is False
    assert args.latent_shadow_window_frames == DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_window_frames
    assert args.latent_shadow_max_link_distance_um == DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_max_link_distance_um
    assert args.mitosis_shadow is False
    assert args.mitosis_shadow_distance_um == DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_distance_um
    assert args.mitosis_shadow_intensity_tolerance == DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_intensity_tolerance
    # Experimental merge-gated correlation recovery must default OFF (V13 protection).
    assert args.enable_correlation_recovery is False
    assert args.correlation_merge_gate_radius == 3.0
    assert args.correlation_merge_gate_frame_window == 1
    assert args.correlation_discount == 0.6

    assert DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier == 1.8
    assert DEFAULT_GUARDRAIL_SETTINGS.min_history == 6
    assert DEFAULT_GUARDRAIL_SETTINGS.history_window == 12
    assert DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count == 1200
    assert DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold == 0.65


def test_pfa_axial_combo_requires_explicit_override() -> None:
    with pytest.raises(ValueError, match="allow-unsafe-pfa-axial"):
        hybrid_submission._validate_experimental_route_scope(
            cfar_route_policy="merged_6bba_only",
            cfar_threshold_mode="pfa",
            sidelobe_mode="axial",
            latent_shadow=False,
            mitosis_shadow=False,
            allow_unsafe_pfa_axial=False,
        )


def test_pfa_axial_combo_allowed_with_explicit_override() -> None:
    hybrid_submission._validate_experimental_route_scope(
        cfar_route_policy="merged_6bba_only",
        cfar_threshold_mode="pfa",
        sidelobe_mode="axial",
        latent_shadow=False,
        mitosis_shadow=False,
        allow_unsafe_pfa_axial=True,
    )


def test_experimental_features_restricted_to_merged_6bba_only() -> None:
    with pytest.raises(ValueError, match="merged_6bba_only"):
        hybrid_submission.run_hybrid_submission(
            input_dir=Path("test"),
            output_csv=Path("submissions/test.csv"),
            report_json=Path("submissions/test_report.json"),
            summary_json=None,
            max_samples=1,
            max_timepoints=1,
            cfar_threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
            cfar_training_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels,
            cfar_guard_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels,
            cfar_threshold_mode="pfa",
            cfar_k_sigma=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
            cfar_pfa=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
            sidelobe_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
            sidelobe_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels,
            sidelobe_axial_z_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
            sidelobe_axial_xy_tolerance_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels,
            sidelobe_floor_ratio=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
            max_detections_per_timepoint=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
            cfar_link_strategy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
            cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
            cfar_route_policy="merged_all",
            track_quality_shadow=True,
            track_quality_beacon_threshold=0.75,
            track_quality_min_track_length=3,
            latent_shadow=False,
            latent_shadow_window_frames=DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_window_frames,
            latent_shadow_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.latent_shadow_max_link_distance_um,
            mitosis_shadow=False,
            mitosis_shadow_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_distance_um,
            mitosis_shadow_intensity_tolerance=DEFAULT_HYBRID_FROZEN_DEFAULTS.mitosis_shadow_intensity_tolerance,
        )
