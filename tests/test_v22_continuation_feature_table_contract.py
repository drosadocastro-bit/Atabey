import hashlib
import json
from pathlib import Path

from atabey.tracking.continuation_features import CONTINUATION_FEATURE_NAMES


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads(
        (
            ROOT / "tests/fixtures/v22_continuation_feature_table.json"
        ).read_text(encoding="utf-8-sig")
    )


def test_continuation_feature_contract_pins_sources_and_population():
    contract = _contract()
    reference_contract = ROOT / contract["source_reference_contract"]
    reference_summary = ROOT / contract["source_reference_summary"]

    assert hashlib.sha256(reference_contract.read_bytes()).hexdigest() == contract[
        "source_reference_contract_sha256"
    ]
    assert hashlib.sha256(reference_summary.read_bytes()).hexdigest() == contract[
        "source_reference_summary_sha256"
    ]
    population = contract["expected_population"]
    assert population["samples"] == 27
    assert population["references"] == 182996
    assert population["alternatives"] == 1024536
    assert population["candidate_rows"] == 1207532
    assert sum(population["candidate_rows_by_fold"].values()) == 1207532
    assert sum(population["candidate_rows_by_family"].values()) == 1207532
    assert sum(population["candidate_rows_by_route"].values()) == 1207532


def test_continuation_feature_contract_preserves_epistemic_boundaries():
    contract = _contract()
    candidates = contract["candidate_definition"]
    features = contract["feature_contract"]

    assert candidates["include_all_local_alternatives"] is True
    assert candidates["alternative_cap"] is None
    assert candidates["reference_is_ground_truth"] is False
    assert candidates["alternative_is_negative"] is False
    assert tuple(features["model_feature_allowlist"]) == CONTINUATION_FEATURE_NAMES
    assert features["route_is_model_feature"] is False
    assert features["family_is_model_feature"] is False
    assert features["appearance_enabled"] is False
    assert features["intensity_enabled"] is False
    assert features["volume_enabled"] is False
    assert contract["semantic_scoring_enabled"] is False
    assert contract["model_fitting_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["production_graph_mutation_enabled"] is False
    assert contract["locked_validation_opened"] is False
    assert contract["full_199_authorized"] is False


def test_continuation_feature_contract_requires_route_stratification():
    reporting = _contract()["reporting"]

    assert reporting["pooled_metrics_require_route_breakdown"] is True
    assert reporting["local_maxima_required_metric_caveat"] == (
        "unproven generalization"
    )
    assert reporting["local_maxima_development_samples"] == 1
    assert reporting["local_maxima_development_fold"] == 3
