import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads(
        (
            ROOT / "tests/fixtures/v22_continuation_head_preregistration.json"
        ).read_text(encoding="utf-8-sig")
    )


def test_continuation_head_contract_pins_completed_feature_table():
    contract = _contract()
    feature_contract = ROOT / contract["source_feature_contract"]
    feature_summary = ROOT / contract["source_feature_summary"]

    assert hashlib.sha256(feature_contract.read_bytes()).hexdigest() == contract[
        "source_feature_contract_sha256"
    ]
    assert hashlib.sha256(feature_summary.read_bytes()).hexdigest() == contract[
        "source_feature_summary_sha256"
    ]
    assert contract["outer_validation"]["folds"] == [1, 2, 3]
    assert contract["outer_validation"]["single_calibration_fold_allowed"] is False
    assert contract["evaluation"]["stratum_weighting"] == (
        "equal_sample_within_each_reported_fold_family_route"
    )
    assert (
        contract["outer_validation"]["heldout_fold_never_guides_model_selection"]
        is True
    )


def test_continuation_head_contract_freezes_fold_generalization_gates():
    generalization = _contract()["generalization"]
    hard = generalization["fold_hard_gates"]
    flagged = generalization["fold_flagged_concerns"]

    assert hard["each_fold_reference_top1_min"] == 0.8
    assert hard["reference_top1_max_fold_spread"] == 0.1
    assert hard["each_fold_pairwise_accuracy_min"] == 0.85
    assert hard["pairwise_accuracy_max_fold_spread"] == 0.08
    assert hard["maximum_fold_drop_from_other_two_mean"] == 0.1
    assert flagged["reference_top1_fold_spread_above"] == 0.05
    assert flagged["pairwise_accuracy_fold_spread_above"] == 0.04
    assert flagged["fold_drop_from_other_two_mean_above"] == 0.05


def test_continuation_head_contract_requires_cfar_and_components_independently():
    generalization = _contract()["generalization"]
    hard = generalization["route_hard_gates"]
    flagged = generalization["route_flagged_concerns"]

    assert hard["decision_routes"] == [
        "cfar_sidelobe/bipartite",
        "components/greedy",
    ]
    assert hard["each_route_reference_top1_min"] == 0.8
    assert hard["reference_top1_max_route_gap"] == 0.1
    assert hard["each_route_fold_reference_top1_min"] == 0.7
    assert hard["maximum_route_fold_drop_from_route_oof"] == 0.15
    assert flagged["reference_top1_route_gap_above"] == 0.05
    assert flagged["route_fold_drop_from_route_oof_above"] == 0.1


def test_continuation_head_contract_preserves_local_maxima_and_label_boundaries():
    contract = _contract()
    population = contract["training_population"]
    local_maxima = contract["generalization"]["local_maxima"]

    assert population["reference_is_ground_truth"] is False
    assert population["alternative_is_biological_negative"] is False
    assert population["singleton_groups_used_for_decision_metrics"] is False
    assert local_maxima["decision_eligible"] is False
    assert local_maxima["required_metric_caveat"] == "unproven generalization"
    assert local_maxima["may_carry_pooled_go"] is False
    assert contract["diagnostics"]["teacher_derived_feature_ablation_required"] is True
    assert (
        contract["diagnostics"][
            "high_weak_reference_recovery_is_biological_validation"
        ]
        is False
    )
    assert contract["semantic_scoring_enabled"] is False
    assert contract["model_fitting_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["production_graph_mutation_enabled"] is False
    assert contract["locked_validation_opened"] is False
    assert contract["full_199_authorized"] is False


def test_continuation_head_decision_states_do_not_promote_flagged_results():
    states = _contract()["decision_states"]

    assert states["GO_TO_JOINT_SEMANTIC_SHADOW"] == (
        "all_hard_gates_pass_and_no_flagged_concern"
    )
    assert states["HOLD_GENERALIZATION_CONCERN"] == (
        "all_hard_gates_pass_but_any_flagged_concern_fires"
    )
    assert states["NO_GO"] == "any_hard_gate_fails"
