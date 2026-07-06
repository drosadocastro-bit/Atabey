from __future__ import annotations

import numpy as np

from atabey.tracking.kinematic_recovery import (
    KinematicRecoverySettings,
    KinematicRecoveryTelemetry,
    KinematicTrack,
    age_and_prune_kinematic_tracks,
    context_authorizes_recovery,
    enqueue_kinematic_tracks,
    inspect_local_context,
    recover_kinematic_edges,
)
from atabey.types import Detection


def _det(node_id: str, t: int, x: float) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="demo",
        t=t,
        z=0.0,
        y=0.0,
        x=float(x),
        z_um=0.0,
        y_um=0.0,
        x_um=float(x),
        detection_confidence=1.0,
    )


def test_context_authorizes_clutter_and_suppresses_clean_context() -> None:
    source = _det("demo:t2:src", 2, 2.0)
    predecessor = _det("demo:t1:pred", 1, 1.0)
    settings = KinematicRecoverySettings(
        trigger_background_mean_min=0.20,
        trigger_adaptive_threshold_min=0.30,
        trigger_contrast_max=0.10,
        trigger_cfar_margin_max=0.02,
    )

    normalized = np.zeros((1, 1, 5), dtype=np.float32)
    background_mean = np.zeros_like(normalized)
    background_std = np.zeros_like(normalized)

    normalized[0, 0, 3] = 0.34
    background_mean[0, 0, 3] = 0.28
    background_std[0, 0, 3] = 0.04
    clutter_context = inspect_local_context(
        source=source,
        predecessor=predecessor,
        normalized=normalized,
        background_mean=background_mean,
        background_std=background_std,
        cfar_k_sigma=1.0,
    )
    assert context_authorizes_recovery(clutter_context, settings=settings) is True

    normalized[0, 0, 3] = 0.85
    background_mean[0, 0, 3] = 0.05
    background_std[0, 0, 3] = 0.02
    clean_context = inspect_local_context(
        source=source,
        predecessor=predecessor,
        normalized=normalized,
        background_mean=background_mean,
        background_std=background_std,
        cfar_k_sigma=1.0,
    )
    assert context_authorizes_recovery(clean_context, settings=settings) is False


def test_enqueue_and_recover_gap_edge_without_synthetic_nodes() -> None:
    source = _det("demo:t2:src", 2, 2.0)
    predecessor = _det("demo:t1:pred", 1, 1.0)
    target = _det("demo:t4:target", 4, 4.0)
    settings = KinematicRecoverySettings(
        min_track_length_edges=2,
        trigger_background_mean_min=0.20,
        trigger_adaptive_threshold_min=0.30,
        trigger_contrast_max=0.10,
        trigger_cfar_margin_max=0.02,
        base_sigma_um=0.5,
        velocity_sigma_scale=0.5,
        transverse_sigma_um=1.0,
        mahalanobis_threshold=2.0,
        directional_cosine_min=0.0,
        temporal_discount=0.7,
        edge_inflation_ceiling_ratio=1.0,
    )
    telemetry = KinematicRecoveryTelemetry()
    latent_tracks: dict[str, KinematicTrack] = {}

    normalized = np.zeros((1, 1, 5), dtype=np.float32)
    background_mean = np.zeros_like(normalized)
    background_std = np.zeros_like(normalized)
    normalized[0, 0, 3] = 0.34
    background_mean[0, 0, 3] = 0.28
    background_std[0, 0, 3] = 0.04
    gap_frame = _det("demo:t3:gap", 3, 12.0)

    enqueue_kinematic_tracks(
        latent_tracks=latent_tracks,
        previous=[source],
        current=[gap_frame],
        max_link_distance_um=2.0,
        link_strategy="motion_mutual",
        matched_source_ids=set(),
        predecessor_by_node_id={source.node_id: predecessor},
        track_length_by_node_id={source.node_id: 2},
        normalized=normalized,
        background_mean=background_mean,
        background_std=background_std,
        cfar_k_sigma=1.0,
        settings=settings,
        telemetry=telemetry,
    )
    assert list(latent_tracks) == [source.node_id]
    assert telemetry.suppressed_by_clean_context == 0
    assert telemetry.suppressed_by_direct_candidate == 0

    edges, recovered_source_ids = recover_kinematic_edges(
        latent_tracks=latent_tracks,
        current=[target],
        used_target_ids=set(),
        max_link_distance_um=2.0,
        settings=settings,
        telemetry=telemetry,
        reference_edge_count=1,
    )

    assert recovered_source_ids == {source.node_id}
    assert [(edge.source_id, edge.target_id, edge.relation) for edge in edges] == [
        (source.node_id, target.node_id, "kinematic_recovery")
    ]
    assert telemetry.recovered_edges == 1
    assert all("synth::" not in edge.source_id and "synth::" not in edge.target_id for edge in edges)


def test_enqueue_suppresses_recovery_when_direct_candidate_exists() -> None:
    source = _det("demo:t2:src", 2, 2.0)
    predecessor = _det("demo:t1:pred", 1, 1.0)
    direct_target = _det("demo:t3:direct", 3, 3.0)
    later_target = _det("demo:t4:target", 4, 4.0)
    settings = KinematicRecoverySettings(
        min_track_length_edges=2,
        trigger_background_mean_min=0.20,
        trigger_adaptive_threshold_min=0.30,
        trigger_contrast_max=0.10,
        trigger_cfar_margin_max=0.02,
        base_sigma_um=0.5,
        velocity_sigma_scale=0.5,
        transverse_sigma_um=1.0,
        mahalanobis_threshold=2.0,
        directional_cosine_min=0.0,
        temporal_discount=0.7,
        edge_inflation_ceiling_ratio=1.0,
    )
    telemetry = KinematicRecoveryTelemetry()
    latent_tracks: dict[str, KinematicTrack] = {}

    normalized = np.zeros((1, 1, 5), dtype=np.float32)
    background_mean = np.zeros_like(normalized)
    background_std = np.zeros_like(normalized)
    normalized[0, 0, 3] = 0.34
    background_mean[0, 0, 3] = 0.28
    background_std[0, 0, 3] = 0.04

    enqueue_kinematic_tracks(
        latent_tracks=latent_tracks,
        previous=[source],
        current=[direct_target],
        max_link_distance_um=2.0,
        link_strategy="motion_mutual",
        matched_source_ids=set(),
        predecessor_by_node_id={source.node_id: predecessor},
        track_length_by_node_id={source.node_id: 2},
        normalized=normalized,
        background_mean=background_mean,
        background_std=background_std,
        cfar_k_sigma=1.0,
        settings=settings,
        telemetry=telemetry,
    )

    assert latent_tracks == {}
    assert telemetry.suppressed_by_direct_candidate == 1
    assert telemetry.suppressed_by_clean_context == 0
    assert telemetry.source_tracks_enqueued == 0

    edges, recovered_source_ids = recover_kinematic_edges(
        latent_tracks=latent_tracks,
        current=[later_target],
        used_target_ids=set(),
        max_link_distance_um=2.0,
        settings=settings,
        telemetry=telemetry,
        reference_edge_count=1,
    )

    assert edges == []
    assert recovered_source_ids == set()


def test_edge_inflation_ceiling_limits_recoveries() -> None:
    settings = KinematicRecoverySettings(
        base_sigma_um=0.5,
        velocity_sigma_scale=0.5,
        transverse_sigma_um=1.0,
        mahalanobis_threshold=2.5,
        temporal_discount=0.7,
        edge_inflation_ceiling_ratio=0.5,
    )
    telemetry = KinematicRecoveryTelemetry()
    source_a = _det("demo:t2:a", 2, 2.0)
    pred_a = _det("demo:t1:a", 1, 1.0)
    source_b = _det("demo:t2:b", 2, 12.0)
    pred_b = _det("demo:t1:b", 1, 11.0)
    target_a = _det("demo:t4:a", 4, 4.0)
    target_b = _det("demo:t4:b", 4, 14.0)

    latent_tracks = {
        source_a.node_id: KinematicTrack(source=source_a, predecessor=pred_a, missing_frames=1, local_context=None),
        source_b.node_id: KinematicTrack(source=source_b, predecessor=pred_b, missing_frames=1, local_context=None),
    }

    edges, _ = recover_kinematic_edges(
        latent_tracks=latent_tracks,
        current=[target_a, target_b],
        used_target_ids=set(),
        max_link_distance_um=2.0,
        settings=settings,
        telemetry=telemetry,
        reference_edge_count=1,
    )

    assert len(edges) == 1
    assert telemetry.suppressed_by_edge_ceiling == 1

    age_and_prune_kinematic_tracks(
        latent_tracks,
        recovered_source_ids={edges[0].source_id},
        max_gap_frames=settings.max_gap_frames,
    )
    assert latent_tracks == {}