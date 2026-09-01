import json
from pathlib import Path

from atabey.provenance import canonical_text_sha256


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests/fixtures/v25_upstream_association_forensics.json"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_v25_contract_pins_frozen_sources() -> None:
    contract = _contract()

    for path, expected_hash in contract["sources"].values():
        assert canonical_text_sha256(ROOT / path) == expected_hash


def test_v25_contract_freezes_regression_cohort_and_telemetry() -> None:
    contract = _contract()
    cohort = contract["cohort"]

    assert cohort["sample_count"] == len(cohort["sample_ids"]) == 16
    assert len(set(cohort["sample_ids"])) == 16
    assert cohort["catastrophic_count"] == 4
    assert contract["frozen_baseline"]["sample_count"] == 199
    assert set(contract["telemetry"]) >= {
        "nearest_second_distance_margin_um",
        "candidate_count_per_source",
        "mutuality_conflict",
        "unmatched_detection",
        "edge_length_um",
        "velocity_um",
        "motion_prediction_error_um",
        "local_source_density",
        "local_target_density",
        "crossing_competitor_count",
        "candidate_edge_pruning_survival",
    }


def test_v25_contract_is_observability_only() -> None:
    boundaries = _contract()["boundaries"]

    assert boundaries["opened_labels_descriptive_only"] is True
    assert all(
        boundaries[key] is False
        for key in (
            "score_claim",
            "promotion_claim",
            "selector_claim",
            "automatic_v19_v24_routing",
            "threshold_or_penalty_tuning",
            "graph_mutation",
            "submission_authorized",
        )
    )


def test_v25_initial_taxonomy_accounts_for_every_regression() -> None:
    contract = _contract()
    taxonomy = contract["initial_taxonomy"]

    classified = taxonomy["adjustment_only"] + taxonomy["unresolved_pending_telemetry"]
    assert len(classified) == len(set(classified)) == 16
    assert set(classified) == set(contract["cohort"]["sample_ids"])