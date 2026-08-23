import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_v22_route_robust_temporal_semantic_audit.py"
SPEC = importlib.util.spec_from_file_location("temporal_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_auc_uses_tie_aware_ranks():
    assert MODULE.auc([1, 0], [1.0, 0.0]) == 1.0
    assert MODULE.auc([1, 0], [0.0, 1.0]) == 0.0
    assert MODULE.auc([1, 0], [1.0, 1.0]) == 0.5


def test_event_mean_auc_weights_events_equally():
    frame = pd.DataFrame(
        {
            "event_id": ["small", "small", "large", "large", "large", "large"],
            "official_label": [
                "official_tp",
                "official_fp",
                "official_tp",
                "official_fp",
                "official_fp",
                "official_fp",
            ],
            "feature": [1.0, 0.0, 0.0, 1.0, 2.0, 3.0],
        }
    )
    assert MODULE.event_mean_auc(frame, "feature", 1.0) == 0.5
