from pathlib import Path
import sys

import pytest

from atabey.tracking.division_firewall import prune_invalid_divisions
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id, t, y, x=0.0):
    return Detection(node_id, "s", t, 0.0, y, x, 0.0, y, x)


def _add(graph, *detections):
    for detection in detections:
        graph.add_detection(detection)


def test_prune_invalid_divisions_removes_only_invalid_two_child_branch():
    graph = LineageGraph("s")

    valid_parent = _d("valid_parent", 0, 0.0)
    valid_a1 = _d("valid_a1", 1, -1.0)
    valid_b1 = _d("valid_b1", 1, 1.0)
    valid_a2 = _d("valid_a2", 2, -3.0)
    valid_b2 = _d("valid_b2", 2, 3.0)
    valid_a3 = _d("valid_a3", 3, -5.0)
    valid_b3 = _d("valid_b3", 3, 5.0)

    invalid_parent = _d("invalid_parent", 0, 20.0)
    invalid_primary = _d("invalid_primary", 1, 21.0)
    invalid_orphan = _d("invalid_orphan", 1, 22.0)

    _add(
        graph,
        valid_parent,
        valid_a1,
        valid_b1,
        valid_a2,
        valid_b2,
        valid_a3,
        valid_b3,
        invalid_parent,
        invalid_primary,
        invalid_orphan,
    )
    for edge in [
        LineageEdge("valid_parent", "valid_a1", relation="division"),
        LineageEdge("valid_parent", "valid_b1", relation="division"),
        LineageEdge("valid_a1", "valid_a2"),
        LineageEdge("valid_b1", "valid_b2"),
        LineageEdge("valid_a2", "valid_a3"),
        LineageEdge("valid_b2", "valid_b3"),
        LineageEdge("invalid_parent", "invalid_primary", relation="division"),
        LineageEdge("invalid_parent", "invalid_orphan", relation="division"),
    ]:
        graph.add_edge(edge)

    prune_invalid_divisions(graph)

    relations = {(edge.source_id, edge.target_id): edge.relation for edge in graph.edges}
    assert relations[("valid_parent", "valid_a1")] == "division"
    assert relations[("valid_parent", "valid_b1")] == "division"
    assert ("invalid_parent", "invalid_orphan") not in relations
    assert relations[("invalid_parent", "invalid_primary")] == "spatial_nearest_neighbor"


@pytest.mark.slow
def test_v20_bipartite_builder_completes_on_cfar_routed_sample():
    project_root = Path(__file__).resolve().parents[1]
    train_dir = project_root / "train"
    sample_path = train_dir / "6bba_05db0fb1.zarr"
    weights_path = project_root / "weights" / "v20_cnn_best.pth"
    if not sample_path.exists() or not weights_path.exists():
        pytest.skip("local Atabey train data and V20 weights are required for this smoke test")

    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
    from run_v20_quality_score_ablation import _build_v20_graph

    graph, _profile, detector, link_strategy, _reason, _distance = _build_v20_graph(
        sample_path=sample_path,
        max_timepoints=2,
        cfar_threshold=defaults.cfar_threshold,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
        cfar_threshold_mode=defaults.cfar_threshold_mode,
        cfar_k_sigma=defaults.cfar_k_sigma,
        cfar_pfa=defaults.cfar_pfa,
        sidelobe_mode=defaults.sidelobe_mode,
        sidelobe_radius_voxels=defaults.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=defaults.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=defaults.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=defaults.sidelobe_floor_ratio,
        max_detections_per_timepoint=defaults.max_detections_per_timepoint,
        cfar_link_strategy="bipartite",
        cfar_max_link_distance_um=defaults.cfar_max_link_distance_um,
        cfar_route_policy=defaults.cfar_route_policy,
        cnn_weights_path=weights_path,
    )

    assert detector == "v20_firewall"
    assert link_strategy == "bipartite"
    assert len(graph.detections) > 0
