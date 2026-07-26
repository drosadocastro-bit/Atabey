import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests/fixtures/v22_e016_dual_seed_detector_shadow.json"


def contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_dual_seed_shadow_pins_available_sources():
    c = contract()
    for path_key, hash_key in [
        ("source_action_availability", "source_action_availability_sha256"),
        ("source_action_contract", "source_action_contract_sha256"),
        ("source_peak_csv", "source_peak_sha256"),
    ]:
        actual = hashlib.sha256((ROOT / c[path_key]).read_bytes()).hexdigest()
        assert actual == c[hash_key]


def test_route_policy_is_asymmetric_and_non_destructive():
    policy = contract()["route_policy"]
    assert policy["44b6"] == "primary_unchanged"
    assert "secondary" in policy["6bba"]
    assert policy["secondary_can_delete_primary_detection"] is False


def test_decision_requires_both_families_and_load_guardrails():
    decision = contract()["decision"]
    assert decision["both_families_required"] is True
    assert decision["new_complete_triplets_min"] >= 1
    assert decision["median_union_primary_peak_ratio_max"] <= 2.0
    assert decision["p90_union_primary_peak_ratio_max"] <= 3.0


def test_external_artifact_and_graph_boundaries_are_closed():
    c = contract()
    artifact = c["artifact_provenance"]
    assert artifact["checkpoint_sha256_required"] is True
    assert artifact["manifest_sha256_required"] is True
    assert artifact["hidden_test_labels_allowed"] is False
    assert artifact["development_labels_allowed"] is False
    assert c["secondary_artifact"]["accepted"] is False
    assert c["inference_enabled"] is False
    assert c["pairing_shadow_enabled"] is False
    assert c["assignment_enabled"] is False
    assert c["graph_mutation_enabled"] is False
    assert c["full_199_authorized"] is False
