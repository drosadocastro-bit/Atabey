import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))
from atabey.io.geff_reader import read_geff_graph
from atabey.baseline import build_baseline_graph

sample_path = project_root / "train/6bba_cdcfe533.zarr"
graph = build_baseline_graph(
    sample_path,
    threshold=4900,
    min_volume=18,
    max_link_distance_um=9.0,
    link_strategy="bipartite",
    detector="components",
    peak_min_distance_voxels=5,
)

pred_edges_out = {}
for edge in graph.edges:
    pred_edges_out.setdefault(edge.source_id, []).append(edge.target_id)
pred_divisions = [src for src, tgts in pred_edges_out.items() if len(tgts) >= 2]
print(f"Pred divisions total: {len(pred_divisions)}")
