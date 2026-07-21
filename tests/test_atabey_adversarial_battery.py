import json
from pathlib import Path

from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.tracking.division_recovery_shadow import TRACK_B_CONFIDENCE_THRESHOLD


BATTERY_PATH = Path(__file__).parent / "fixtures" / "atabey_adversarial_battery.json"
REQUIRED_CASE_IDS = {
    "COLLISION-DRIFT-090",
    "COLLISION-DRIFT-100",
    "COLLISION-DRIFT-110",
    "V19-TP-05DB",
    "V19-TP-B329",
    "V19-TP-EBDF",
    "V21-FN-EBDF-PAIRING",
    "LINK-GATE-14-REGRESSION-05DB",
}


def _battery():
    return json.loads(BATTERY_PATH.read_text(encoding="utf-8"))


def test_adversarial_battery_is_append_only_and_ids_are_unique():
    battery = _battery()
    case_ids = [case["case_id"] for case in battery["cases"]]

    assert battery["policy"]["append_only"] is True
    assert len(case_ids) == len(set(case_ids))
    assert REQUIRED_CASE_IDS <= set(case_ids)


def test_adversarial_battery_preserves_frozen_track_a_and_9um_formation_gate():
    battery = _battery()
    pairing_case = next(case for case in battery["cases"] if case["case_id"] == "V21-FN-EBDF-PAIRING")

    assert battery["policy"]["track_a_frozen"] is True
    assert DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um == 9.0
    assert pairing_case["formation_gate_um"] == 9.0
    assert pairing_case["evaluation_separation_gate_um"] == 15.0
    assert pairing_case["expected"] == "upstream_missing_candidate"


def test_adversarial_battery_requires_uncalibrated_candidates_to_stay_flagged():
    battery = _battery()
    known_true_divisions = [
        case for case in battery["cases"] if case["category"] == "known_true_division"
    ]

    assert battery["policy"]["confidence_threshold"] == TRACK_B_CONFIDENCE_THRESHOLD
    assert battery["policy"]["uncalibrated_candidates"] == "extractive_flagged"
    assert len(known_true_divisions) == 3
    assert all(case["expected"] == "extractive_flagged" for case in known_true_divisions)


def test_collision_band_cases_remain_rejected():
    collision_cases = [
        case for case in _battery()["cases"] if case["category"] == "collision_noise"
    ]

    assert {case["max_drift_deg"] for case in collision_cases} == {90.0, 100.0, 110.0}
    assert all(case["expected"] == "rejected" for case in collision_cases)
