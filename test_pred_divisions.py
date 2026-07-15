import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent

sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from scripts.run_hybrid_train_evaluation import _build_hybrid_graph
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS


sample_id = "6bba_cdcfe533"
sample_path = project_root / f"train/{sample_id}.zarr"
geff_path = project_root / f"train/{sample_id}.geff"
gt = read_geff_graph(geff_path)

graph_v19, profile, detector, strategy, reason, max_dist = _build_hybrid_graph(
    sample_path=sample_path,
    max_timepoints=100,
    cfar_threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
    cfar_training_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels,
    cfar_guard_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels,
    cfar_threshold_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode,
    cfar_k_sigma=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
    cfar_pfa=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
    sidelobe_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
    sidelobe_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels,
    sidelobe_axial_z_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
    sidelobe_axial_xy_tolerance_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels,
    sidelobe_floor_ratio=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
    max_detections_per_timepoint=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
    cfar_link_strategy="bipartite",
    cfar_max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
    cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
    enable_watershed_refinement=True
)
print(f"Strategy used: {strategy}")

pred_edges_out = {}
for edge in graph_v19.edges:
    pred_edges_out.setdefault(edge.source_id, []).append(edge.target_id)
pred_divisions = [src for src, tgts in pred_edges_out.items() if len(tgts) >= 2]
print(f"Pred divisions total: {len(pred_divisions)}")
