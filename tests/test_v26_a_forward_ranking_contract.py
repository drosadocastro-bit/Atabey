import json
from pathlib import Path

from atabey.provenance import canonical_text_sha256


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "tests/fixtures/v26_a_forward_ranking_ablation.json"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_v26_a_contract_pins_all_sources() -> None:
    for path, expected_hash in _contract()["sources"].values():
        assert canonical_text_sha256(ROOT / path) == expected_hash


def test_v26_a_freezes_one_intervention_and_the_v25_cohort() -> None:
    contract = _contract()
    cohort = contract["cohort"]
    intervention = contract["intervention"]

    assert cohort["sample_count"] == len(cohort["sample_ids"]) == 16
    assert len(set(cohort["sample_ids"])) == 16
    assert contract["v25_attribution"] == {
        "selection_losses": 704,
        "forward_prediction_ranking_losses": 436,
        "reverse_mutuality_conflicts": 268,
        "method": "exact_pinned_scipy_ckdtree_replay",
    }
    assert intervention["baseline_forward_rank_key"] == "motion_prediction_error_um"
    assert intervention["ablation_forward_rank_key"] == "physical_step_distance_um"
    assert intervention["max_prediction_error_um"] == 9.0
    assert intervention["max_step_distance_um"] == 9.0
    assert intervention["parameter_sweep"] is False


def test_v26_a_interest_gate_is_stronger_than_score_improvement() -> None:
    gate = _contract()["interest_gate"]

    assert gate["minimum_forward_ranking_recoveries"] == 44
    assert gate["require_positive_net_association_delta"] is True
    assert gate["maximum_net_incorrect_edge_delta"] == 0
    assert gate["maximum_new_incorrect_edges_per_forward_recovery"] == 0.25
    assert gate["maximum_per_sample_adjusted_edge_jaccard_regression"] == 0.10
    assert gate["require_deterministic_replay"] is True
    assert gate["passing_authorizes_production"] is False


def test_v26_a_preserves_research_boundaries() -> None:
    boundaries = _contract()["boundaries"]

    assert boundaries["opened_labels_descriptive_only"] is True
    assert all(
        boundaries[key] is False
        for key in (
            "independent_generalization_claim",
            "production_tuning_authorized",
            "selector_claim",
            "automatic_routing",
            "threshold_or_weight_tuning",
            "candidate_expansion",
            "mutuality_change",
            "pruning_change",
            "submission_authorized",
        )
    )