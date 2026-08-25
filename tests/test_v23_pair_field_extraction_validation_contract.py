import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads(
        (ROOT / "tests/fixtures/v23_cfar_pair_field_extraction_validation.json").read_text(
            encoding="utf-8"
        )
    )


def test_pair_field_contract_pins_official_availability_sources():
    contract = _contract()
    sources = contract["sources"]

    for path_key, hash_key in (
        ("availability_summary", "availability_summary_sha256"),
        ("availability_audit_script", "availability_audit_script_sha256"),
    ):
        path = ROOT / sources[path_key]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sources[hash_key]

    summary = json.loads((ROOT / sources["availability_summary"]).read_text())
    assert summary["decision"] == "GO_TO_CFAR_PAIR_FIELD_EXTRACTION_CONTRACT"
    assert summary["official_positive"] == {
        "events": 29,
        "official_tp_actions": 90,
        "samples": 22,
    }
    assert contract["sources"]["official_metric_commit"] == (
        "075fc5f5a52d11077f9dc2b074644618f26939e2"
    )


def test_pair_field_contract_freezes_sample_blocked_population():
    population = _contract()["population"]
    folds = population["folds"]
    samples = [sample for fold in folds for sample in fold["samples"]]

    assert len(folds) == 3
    assert len(samples) == 22
    assert len(set(samples)) == 22
    assert [fold["events"] for fold in folds] == [9, 12, 8]
    assert [fold["44b6_events"] for fold in folds] == [2, 4, 3]
    assert [fold["6bba_events"] for fold in folds] == [7, 8, 5]
    assert population["action_variants_are_independent_events"] is False
    assert population["unavailable_events_are_training_negatives"] is False
    assert population["fold_assignment_may_be_rebalanced_after_extraction"] is False


def test_pair_field_tensor_and_storage_contract_are_explicit():
    contract = _contract()
    tensor = contract["tensor"]
    storage = contract["storage"]

    assert tensor["assembled_shape_czyx"] == [5, 33, 33, 33]
    assert tensor["spacing_um"] == [1.0, 1.0, 1.0]
    assert tensor["channels"] == [
        "image_t",
        "image_t_plus_1",
        "parent_mask",
        "symmetric_daughter_pair_mask",
        "crop_coverage_mask",
    ]
    assert tensor["coordinate_scalar_inputs"] is False
    assert tensor["family_route_sample_or_node_id_inputs"] is False
    assert tensor["child_order_visible"] is False
    assert storage["duplicate_dense_parent_field_per_action"] is False
    assert storage["preflight_before_tensor_write"] is True
    assert storage["output_root_must_remain_out_of_git"] is True


def test_pair_field_label_and_weighting_boundaries_are_frozen():
    contract = _contract()
    candidates = contract["candidate_universe"]
    weighting = contract["weighting"]

    assert candidates["supervised_negative"] == "patched_official_fp_only"
    assert candidates["unknown_in_supervised_loss"] is False
    assert candidates["unknown_retained_in_full_candidate_ranking"] is True
    assert candidates["sparse_absence_is_negative"] is False
    assert candidates["canonical_positive_receives_priority"] is False
    assert candidates["gates_are_distinct"] is True
    assert weighting["hierarchy"] == ["sample", "event", "label_side", "action"]
    assert weighting["raw_action_weighting_allowed"] is False
    assert weighting["multi_positive_event_success_counted_once"] is True


def test_pair_field_controls_and_generalization_gates_are_mandatory():
    contract = _contract()
    controls = contract["mandatory_controls"]
    gates = contract["future_model_evidence_gates"]
    validation = contract["outer_validation"]

    assert set(controls) >= {
        "nearest_distance",
        "geometry_only",
        "mask_only",
        "image_shuffled",
        "static_image",
    }
    assert contract["control_policy"]["definitions_locked_before_outcomes"] is True
    assert validation["heldout_fold_never_guides_model_or_threshold_selection"] is True
    assert validation["single_calibration_fold_allowed"] is False
    assert validation["full_ranking_includes_unknown_candidates"] is True
    assert validation["unknown_candidates_count_as_false_positives"] is False
    assert gates["pooled_recall_at_10_min"] == 0.8
    assert gates["each_fold_recall_at_10_min"] == 0.625
    assert gates["each_family_recall_at_10_min"] == 0.65
    assert gates["recall_at_10_margin_over_best_nonimage_control_min"] == 0.1
    assert gates["recall_at_10_margin_over_image_shuffled_min"] == 0.1
    assert gates["recall_at_10_margin_over_static_image_min"] == 0.05


def test_pair_field_contract_remains_pre_extraction_and_zero_perturbation():
    contract = _contract()
    integrity = contract["extraction_integrity"]
    states = contract["decision_states"]

    assert integrity["source_graph_mutation"] is False
    assert integrity["official_metric_relabel_parity_required"] is True
    assert integrity["repeated_extraction_hash_match_required"] is True
    assert integrity["expected_positive_events"] == 29
    assert integrity["expected_positive_action_variants"] == 90
    assert states["NO_GO_EXTRACTION"].startswith("any_leakage")
    assert contract["extraction_enabled"] is False
    assert contract["tensor_writes_enabled"] is False
    assert contract["model_fitting_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["production_graph_mutation_enabled"] is False
    assert contract["full_199_authorized"] is False
