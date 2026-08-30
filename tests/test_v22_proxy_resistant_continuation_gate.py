import json
from pathlib import Path

from atabey.provenance import canonical_text_sha256

ROOT = Path(__file__).resolve().parents[1]


def _contract():
    return json.loads((ROOT / "tests/fixtures/v22_proxy_resistant_continuation_gate.json").read_text(encoding="utf-8-sig"))


def test_proxy_gate_pins_opened_sources():
    contract = _contract()
    for path_key, hash_key in [
        ("source_head_contract", "source_head_contract_sha256"),
        ("source_head_summary", "source_head_summary_sha256"),
        ("source_proxy_audit", "source_proxy_audit_sha256"),
    ]:
        path = ROOT / contract[path_key]
        assert canonical_text_sha256(path) == contract[hash_key]


def test_proxy_gate_removes_teacher_and_complete_motion_reconstruction_set():
    contract = _contract()
    removed = set(contract["direct_teacher_features_removed"]) | set(contract["motion_reconstruction_features_removed"])
    retained = set(contract["density_ownership_features"])
    assert len(removed) == 10
    assert removed.isdisjoint(retained)
    assert retained == {
        "parent_density_10um", "child_density_10um",
        "local_target_count_14um", "local_competing_source_count_14um",
    }
    assert "anchor_parent_distance_um" in removed
    assert "parent_child_distance_um" in removed
    assert "turn_angle_deg" in removed


def test_proxy_gate_freezes_three_way_comparison_and_incremental_thresholds():
    contract = _contract()
    assert set(contract["models"]) == {"density_only", "nearest_distance_baseline", "distance_plus_density"}
    assert contract["models"]["nearest_distance_baseline"]["fitted"] is False
    decision = contract["decision"]
    assert decision["pooled_top1_delta_over_nearest_min"] == 0.005
    assert decision["pooled_pairwise_delta_over_nearest_min"] == 0.0025
    assert decision["minimum_fold_top1_delta"] == -0.0025
    assert decision["minimum_route_top1_delta"] == -0.0025
    assert decision["folds_with_positive_top1_delta_min"] == 2
    assert decision["routes_with_nonnegative_top1_delta_min"] == 2


def test_proxy_gate_preserves_scope_and_epistemic_boundary():
    contract = _contract()
    assert contract["validation"]["sample_blocked"] is True
    assert contract["validation"]["local_maxima_decision_eligible"] is False
    assert contract["interpretation"]["weak_reference_prediction_is_biological_validation"] is False
    assert contract["model_fitting_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["graph_mutation_enabled"] is False
    assert contract["results_opened"] is False
