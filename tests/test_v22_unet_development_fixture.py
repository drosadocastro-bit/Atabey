import json
from collections import Counter
from pathlib import Path


def test_development_fixture_is_frozen_and_sample_blocked():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "v22_unet_detection_development_46.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = fixture["cases"]

    assert len(cases) == 46
    assert len({case["case_id"] for case in cases}) == 46
    assert len({case["sample_id"] for case in cases}) == 27
    assert Counter(case["cohort"] for case in cases) == {
        "baseline_unavailable": 25,
        "baseline_nonofficial_action": 8,
        "positive_control": 13,
    }
    assert Counter(case["sample_id"].split("_", 1)[0] for case in cases) == {
        "44b6": 6,
        "6bba": 40,
    }
    assert all(case["t"] >= 0 for case in cases)
    assert all(len(case["gt_child_ids"]) == 2 for case in cases)
    assert fixture["det_threshold"] == 0.97
    assert fixture["pool_kernel_um"] == 3.0
    assert fixture["tta"] == "xy_d4_8_view"
