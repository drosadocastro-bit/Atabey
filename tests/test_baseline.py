import numpy as np

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.detection.baseline import (
    detections_from_components,
    robust_normalize,
    threshold_connected_components,
    threshold_local_maxima_cfar,
    threshold_local_maxima_cfar_sidelobe,
    threshold_local_maxima,
)
from atabey.tracking.nearest_neighbor import (
    link_adjacent_timepoints,
    link_adjacent_timepoints_motion_crowding,
)
from atabey.types import Detection


def test_robust_normalize_handles_flat_volume():
    volume = np.ones((3, 3, 3), dtype=np.uint16) * 7

    normalized = robust_normalize(volume)

    assert normalized.dtype == np.float32
    assert np.all(normalized == 0)


def test_detections_from_components_uses_physical_scale():
    labels = np.zeros((3, 3, 3), dtype=np.int32)
    labels[1, 2, 2] = 1
    image = np.ones_like(labels, dtype=np.uint16) * 10

    detections = detections_from_components("sample", 4, labels, image)

    assert len(detections) == 1
    detection = detections[0]
    assert detection.t == 4
    assert detection.z_um == DEFAULT_VOXEL_SCALE_UM.z
    assert detection.y_um == 2 * DEFAULT_VOXEL_SCALE_UM.y
    assert detection.x_um == 2 * DEFAULT_VOXEL_SCALE_UM.x


def test_local_maxima_splits_two_peaks_in_one_connected_foreground():
    volume = np.zeros((5, 9, 9), dtype=np.uint16)
    volume[2, 1:8, 1:8] = 50
    volume[2, 2, 2] = 120
    volume[2, 6, 6] = 130

    component_detections = threshold_connected_components(
        "sample", 0, volume, threshold=0.6, min_volume=1
    )
    peak_detections = threshold_local_maxima(
        "sample",
        0,
        volume,
        threshold=0.6,
        min_distance_voxels=(0, 1, 1),
    )

    assert len(component_detections) == 1
    assert len(peak_detections) == 2
    assert [(d.z, d.y, d.x) for d in peak_detections] == [(2.0, 2.0, 2.0), (2.0, 6.0, 6.0)]


def test_local_maxima_can_cap_peak_count_by_confidence():
    volume = np.zeros((3, 7, 7), dtype=np.uint16)
    volume[1, 1, 1] = 100
    volume[1, 3, 3] = 200
    volume[1, 5, 5] = 150

    detections = threshold_local_maxima(
        "sample",
        0,
        volume,
        threshold=0.2,
        min_distance_voxels=(0, 1, 1),
        max_detections=2,
    )

    assert len(detections) == 2
    assert {(d.y, d.x) for d in detections} == {(3.0, 3.0), (5.0, 5.0)}


def test_local_maxima_cfar_detects_strong_peak():
    volume = np.zeros((3, 9, 9), dtype=np.uint16)
    volume[1, 4, 4] = 200

    detections = threshold_local_maxima_cfar(
        "sample",
        0,
        volume,
        threshold=0.1,
        min_distance_voxels=(0, 1, 1),
        cfar_training_radius_voxels=(0, 3, 3),
        cfar_guard_radius_voxels=(0, 1, 1),
        cfar_k_sigma=0.5,
    )

    assert len(detections) == 1
    assert (detections[0].z, detections[0].y, detections[0].x) == (1.0, 4.0, 4.0)


def test_local_maxima_cfar_detects_peak_with_pfa_mode():
    volume = np.zeros((3, 9, 9), dtype=np.uint16)
    volume[1, 4, 4] = 220

    detections = threshold_local_maxima_cfar(
        "sample",
        0,
        volume,
        threshold=0.1,
        min_distance_voxels=(0, 1, 1),
        cfar_training_radius_voxels=(0, 3, 3),
        cfar_guard_radius_voxels=(0, 1, 1),
        cfar_threshold_mode="pfa",
        cfar_pfa=1e-2,
    )

    assert len(detections) == 1
    assert (detections[0].z, detections[0].y, detections[0].x) == (1.0, 4.0, 4.0)


def test_local_maxima_cfar_sidelobe_suppresses_nearby_weaker_peak():
    volume = np.zeros((3, 11, 11), dtype=np.uint16)
    volume[1, 5, 5] = 220
    volume[1, 6, 6] = 150
    volume[1, 2, 2] = 180

    cfar = threshold_local_maxima_cfar(
        "sample",
        0,
        volume,
        threshold=0.1,
        min_distance_voxels=(0, 0, 0),
        cfar_training_radius_voxels=(0, 3, 3),
        cfar_guard_radius_voxels=(0, 1, 1),
        cfar_k_sigma=0.5,
    )
    suppressed = threshold_local_maxima_cfar_sidelobe(
        "sample",
        0,
        volume,
        threshold=0.1,
        min_distance_voxels=(0, 0, 0),
        cfar_training_radius_voxels=(0, 3, 3),
        cfar_guard_radius_voxels=(0, 1, 1),
        cfar_k_sigma=0.5,
        sidelobe_radius_voxels=(0, 2, 2),
        sidelobe_floor_ratio=0.85,
    )

    assert len(cfar) == 3
    assert len(suppressed) == 2
    kept_positions = {(d.y, d.x) for d in suppressed}
    assert (2.0, 2.0) in kept_positions
    assert ((5.0, 5.0) in kept_positions) ^ ((6.0, 6.0) in kept_positions)


def test_local_maxima_cfar_sidelobe_axial_mode_suppresses_z_stacks():
    volume = np.zeros((5, 11, 11), dtype=np.uint16)
    volume[2, 5, 5] = 240
    volume[3, 5, 5] = 170
    volume[2, 2, 2] = 200

    suppressed = threshold_local_maxima_cfar_sidelobe(
        "sample",
        0,
        volume,
        threshold=0.1,
        min_distance_voxels=(0, 0, 0),
        cfar_training_radius_voxels=(1, 3, 3),
        cfar_guard_radius_voxels=(0, 1, 1),
        cfar_k_sigma=0.5,
        sidelobe_mode="axial",
        sidelobe_radius_voxels=(0, 0, 0),
        sidelobe_axial_z_radius_voxels=2,
        sidelobe_axial_xy_tolerance_voxels=(0, 0),
        sidelobe_floor_ratio=0.90,
    )

    assert len(suppressed) == 2
    kept_positions = {(d.z, d.y, d.x) for d in suppressed}
    assert (2.0, 2.0, 2.0) in kept_positions
    assert ((2.0, 5.0, 5.0) in kept_positions) ^ ((3.0, 5.0, 5.0) in kept_positions)


def test_nearest_neighbor_linking_is_one_to_one():
    previous = [
        Detection("a", "s", 0, 0, 0, 0, 0, 0, 0),
        Detection("b", "s", 0, 0, 0, 0, 0, 10, 0),
    ]
    current = [
        Detection("c", "s", 1, 0, 0, 0, 0, 0.5, 0),
        Detection("d", "s", 1, 0, 0, 0, 0, 10.5, 0),
    ]

    edges = link_adjacent_timepoints(previous, current, max_link_distance_um=2.0)

    assert [(edge.source_id, edge.target_id) for edge in edges] == [("a", "c"), ("b", "d")]


def test_mutual_nearest_neighbor_rejects_asymmetric_link():
    previous = [
        Detection("a", "s", 0, 0, 0, 0, 0, 0, 0),
        Detection("b", "s", 0, 0, 0, 0, 0, 2, 0),
    ]
    current = [
        Detection("c", "s", 1, 0, 0, 0, 0, 1.5, 0),
        Detection("d", "s", 1, 0, 0, 0, 0, 2.1, 0),
    ]

    greedy_edges = link_adjacent_timepoints(previous, current, 3.0, strategy="greedy")
    mutual_edges = link_adjacent_timepoints(previous, current, 3.0, strategy="mutual")

    assert [(edge.source_id, edge.target_id) for edge in greedy_edges] == [("b", "d"), ("a", "c")]
    assert [(edge.source_id, edge.target_id) for edge in mutual_edges] == [("b", "d")]


def test_motion_linking_prefers_predicted_continuation():
    predecessor = Detection("p0", "s", 0, 0, 0, 0, 0, 0, 0)
    source = Detection("p1", "s", 1, 0, 0, 0, 0, 2, 0)
    current = [
        Detection("near_source", "s", 2, 0, 0, 0, 0, 2.5, 0),
        Detection("predicted", "s", 2, 0, 0, 0, 0, 4.0, 0),
    ]

    greedy_edges = link_adjacent_timepoints([source], current, 5.0, strategy="greedy")
    motion_edges = link_adjacent_timepoints(
        [source],
        current,
        5.0,
        strategy="motion",
        predecessor_by_node_id={"p1": predecessor},
    )

    assert [(edge.source_id, edge.target_id) for edge in greedy_edges] == [("p1", "near_source")]
    assert [(edge.source_id, edge.target_id) for edge in motion_edges] == [("p1", "predicted")]


def test_motion_linking_falls_back_without_predecessor():
    source = Detection("p1", "s", 1, 0, 0, 0, 0, 2, 0)
    current = [
        Detection("near", "s", 2, 0, 0, 0, 0, 2.5, 0),
        Detection("far", "s", 2, 0, 0, 0, 0, 4.0, 0),
    ]

    edges = link_adjacent_timepoints([source], current, 5.0, strategy="motion")

    assert [(edge.source_id, edge.target_id) for edge in edges] == [("p1", "near")]



def test_motion_division_adds_one_bounded_split_edge():
    source = Detection("p1", "s", 1, 0, 0, 0, 0, 0, 0)
    current = [
        Detection("daughter_a", "s", 2, 0, 0, 0, 0, 1.0, 0),
        Detection("daughter_b", "s", 2, 0, 0, 0, 0, -1.2, 0),
    ]

    motion_edges = link_adjacent_timepoints([source], current, 5.0, strategy="motion")
    division_edges = link_adjacent_timepoints([source], current, 5.0, strategy="motion_division")

    assert [(edge.source_id, edge.target_id, edge.relation) for edge in motion_edges] == [
        ("p1", "daughter_a", "continuation")
    ]
    assert [(edge.source_id, edge.target_id, edge.relation) for edge in division_edges] == [
        ("p1", "daughter_a", "continuation"),
        ("p1", "daughter_b", "division"),
    ]


def test_motion_division_does_not_add_second_edge_when_target_prefers_other_source():
    previous = [
        Detection("a", "s", 1, 0, 0, 0, 0, 0, 0),
        Detection("b", "s", 1, 0, 0, 0, 0, 4.0, 0),
    ]
    current = [
        Detection("a_next", "s", 2, 0, 0, 0, 0, 1.0, 0),
        Detection("belongs_to_b", "s", 2, 0, 0, 0, 0, 3.8, 0),
    ]

    edges = link_adjacent_timepoints(previous, current, 5.0, strategy="motion_division")

    assert set((edge.source_id, edge.target_id, edge.relation) for edge in edges) == {
        ("a", "a_next", "continuation"),
        ("b", "belongs_to_b", "continuation"),
    }


def test_motion_mutual_rejects_contested_target():
    predecessor = Detection("a0", "s", 0, 0, 0, 0, 0, -2, 0)
    a = Detection("a1", "s", 1, 0, 0, 0, 0, 0, 0)
    b = Detection("b1", "s", 1, 0, 0, 0, 0, 2.2, 0)
    current = [Detection("c", "s", 2, 0, 0, 0, 0, 2.1, 0)]
    predecessors = {"a1": predecessor}

    motion_edges = link_adjacent_timepoints(
        [a, b], current, 5.0, strategy="motion", predecessor_by_node_id=predecessors
    )
    mutual_edges = link_adjacent_timepoints(
        [a, b], current, 5.0, strategy="motion_mutual", predecessor_by_node_id=predecessors
    )

    assert [(edge.source_id, edge.target_id) for edge in motion_edges] == [("a1", "c")]
    assert [(edge.source_id, edge.target_id) for edge in mutual_edges] == [("b1", "c")]


def test_motion_mutual_accepts_uncontested_prediction():
    predecessor = Detection("p0", "s", 0, 0, 0, 0, 0, 0, 0)
    source = Detection("p1", "s", 1, 0, 0, 0, 0, 2, 0)
    current = [
        Detection("near_source", "s", 2, 0, 0, 0, 0, 2.5, 0),
        Detection("predicted", "s", 2, 0, 0, 0, 0, 4.0, 0),
    ]

    edges = link_adjacent_timepoints(
        [source],
        current,
        5.0,
        strategy="motion_mutual",
        predecessor_by_node_id={"p1": predecessor},
    )

    assert [(edge.source_id, edge.target_id) for edge in edges] == [("p1", "predicted")]


def test_motion_mutual_latent_matches_motion_mutual_for_adjacent_linking():
    predecessor = Detection("p0", "s", 0, 0, 0, 0, 0, 0, 0)
    source = Detection("p1", "s", 1, 0, 0, 0, 0, 2, 0)
    current = [
        Detection("near_source", "s", 2, 0, 0, 0, 0, 2.5, 0),
        Detection("predicted", "s", 2, 0, 0, 0, 0, 4.0, 0),
    ]

    mutual_edges = link_adjacent_timepoints(
        [source],
        current,
        5.0,
        strategy="motion_mutual",
        predecessor_by_node_id={"p1": predecessor},
    )
    latent_edges = link_adjacent_timepoints(
        [source],
        current,
        5.0,
        strategy="motion_mutual_latent",
        predecessor_by_node_id={"p1": predecessor},
    )

    assert [(edge.source_id, edge.target_id) for edge in latent_edges] == [
        (edge.source_id, edge.target_id) for edge in mutual_edges
    ]


def test_motion_crowding_gates_only_contested_targets():
    predecessor = Detection("am", "s", 0, 0, 0, 0, 0, -1, 0)
    a = Detection("a", "s", 1, 0, 0, 0, 0, 0, 0)
    b = Detection("b", "s", 1, 0, 0, 0, 0, 2, 0)
    current = [Detection("c", "s", 2, 0, 0, 0, 0, 1.05, 0)]
    predecessors = {"a": predecessor}

    motion_edges = link_adjacent_timepoints(
        [a, b], current, 5.0, strategy="motion", predecessor_by_node_id=predecessors
    )
    crowding_edges = link_adjacent_timepoints(
        [a, b], current, 5.0, strategy="motion_crowding", predecessor_by_node_id=predecessors
    )

    # Crowded target: motion switches to the far predicted source, the crowding gate
    # reassigns it to the physical owner (same result as motion_mutual would give).
    assert [(edge.source_id, edge.target_id) for edge in motion_edges] == [("a", "c")]
    assert [(edge.source_id, edge.target_id) for edge in crowding_edges] == [("b", "c")]


def test_motion_crowding_ratio_one_reduces_to_motion():
    predecessor = Detection("am", "s", 0, 0, 0, 0, 0, -1, 0)
    a = Detection("a", "s", 1, 0, 0, 0, 0, 0, 0)
    b = Detection("b", "s", 1, 0, 0, 0, 0, 2, 0)
    current = [Detection("c", "s", 2, 0, 0, 0, 0, 1.05, 0)]
    predecessors = {"a": predecessor}

    # crowding_ratio == 1.0 marks nothing as contested, so the gate never fires and
    # the hybrid behaves exactly like permissive motion linking.
    edges = link_adjacent_timepoints_motion_crowding(
        [a, b], current, 5.0, predecessor_by_node_id=predecessors, crowding_ratio=1.0
    )

    assert [(edge.source_id, edge.target_id) for edge in edges] == [("a", "c")]


