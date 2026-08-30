import json
from pathlib import Path

from atabey.provenance import canonical_text_sha256


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests/fixtures/v22_route_robust_temporal_semantic_audit.json"


def _contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_temporal_audit_pins_all_sources():
    contract = _contract()
    for path_key, hash_key in [
        ("source_peaks", "source_peaks_sha256"),
        ("source_action_summary", "source_action_summary_sha256"),
        ("source_failed_ranker_summary", "source_failed_ranker_summary_sha256"),
        ("source_development_contract", "source_development_contract_sha256"),
    ]:
        actual = canonical_text_sha256(ROOT / contract[path_key])
        assert actual == contract[hash_key]


def test_all_positive_events_have_complete_temporal_windows():
    population = _contract()["population"]
    assert population["positive_events"] == 39
    assert population["positive_events_with_t_minus_1_through_t_plus_2"] == 39
    assert (
        population["cfar_positive_events"]
        + population["components_positive_events"]
        + population["local_maxima_positive_events"]
        == population["positive_events"]
    )


def test_temporal_sampling_is_fixed_and_teacher_independent():
    contract = _contract()
    frames = contract["temporal_frames"]
    assert frames["fixed_coordinate_sampling"] is True
    assert frames["future_peak_reassociation"] is False
    prohibited = set(contract["prohibited_predictive_inputs"])
    assert {
        "distance",
        "velocity",
        "ownership_margin",
        "teacher_score",
        "ground_truth_distance",
    } <= prohibited


def test_unknown_actions_remain_unknown():
    labels = _contract()["labels"]
    assert labels["unknown_used_as_negative"] is False
    assert labels["sparse_absence_is_negative"] is False


def test_generalization_gates_cover_routes_families_and_incremental_value():
    decision = _contract()["decision"]
    assert decision["same_feature_min_fold_auc"] >= 0.60
    assert decision["same_feature_min_family_auc"] >= 0.62
    assert decision["same_feature_cfar_auc_min"] >= 0.62
    assert decision["same_feature_components_auc_min"] >= 0.70
    assert decision["best_temporal_auc_advantage_over_static_baseline_min"] >= 0.03


def test_assignment_and_graph_mutation_remain_closed():
    contract = _contract()
    assert contract["feature_extraction_enabled"] is False
    assert contract["model_fitting_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["graph_mutation_enabled"] is False
    assert contract["locked_validation_opened"] is False
    assert contract["full_199_authorized"] is False
