import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_continuation_audit_contract_freezes_strata_and_shadow_boundaries():
    path = ROOT / "tests/fixtures/v22_continuation_reference_audit.json"
    contract = json.loads(path.read_text(encoding="utf-8-sig"))
    source = ROOT / contract["source_semantic_contract"]

    assert hashlib.sha256(source.read_bytes()).hexdigest() == contract[
        "source_semantic_contract_sha256"
    ]
    assert contract["reporting"]["required_strata"] == [
        "fold",
        "family",
        "route",
        "sample",
        "parent_frame",
    ]
    assert contract["reporting"]["pooled_metrics_require_route_breakdown"] is True
    assert (
        contract["reporting"]["local_maxima_required_metric_caveat"]
        == "unproven generalization"
    )
    definition = contract["reference_definition"]
    assert definition["chain_frames"] == 3
    assert definition["single_in_single_out"] is True
    assert definition["mutual_nearest"] == (
        "motion_predicted_forward_raw_reverse"
    )
    assert definition["division_exclusion_scope"] == "any_chain_frame"
    assert definition["reference_is_ground_truth"] is False
    assert contract["semantic_scoring_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["production_graph_mutation_enabled"] is False
    assert contract["full_199_authorized"] is False


def test_continuation_audit_contract_freezes_concentration_gates():
    contract = json.loads(
        (
            ROOT
            / "tests/fixtures/v22_continuation_reference_audit.json"
        ).read_text(encoding="utf-8-sig")
    )
    decision = contract["decision_contract"]

    assert decision["minimum_references_per_fold"] == 200
    assert decision["minimum_references_with_alternatives_per_fold"] == 100
    assert decision["minimum_samples_with_references_per_fold"] == 7
    assert decision["maximum_top_sample_share"] == 0.2
    assert decision["maximum_top_three_sample_share"] == 0.45
    assert decision["both_families_required"] is True
    assert decision["all_source_graphs_zero_perturbation"] is True