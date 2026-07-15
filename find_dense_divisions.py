import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))
from atabey.io.geff_reader import read_geff_graph
from atabey.detection.adaptive import choose_settings_for_sample

train_dir = project_root / "train"
for geff_path in train_dir.glob("*.geff"):
    sample_id = geff_path.stem
    gt = read_geff_graph(geff_path)
    
    gt_edges_out = {}
    for src, tgt in gt.edges:
        gt_edges_out.setdefault(src, []).append(tgt)
        
    divs = [src for src, tgts in gt_edges_out.items() if len(tgts) >= 2]
    if len(divs) > 0:
        sample_path = train_dir / f"{sample_id}.zarr"
        if sample_path.exists():
            profile, settings = choose_settings_for_sample(sample_path)
            if settings.detector == "local_maxima":
                print(f"Sample {sample_id} is dense and has {len(divs)} divisions!")
