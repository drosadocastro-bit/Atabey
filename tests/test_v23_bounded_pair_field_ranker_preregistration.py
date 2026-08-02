import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads(
        (ROOT / "tests/fixtures/v23_bounded_pair_field_ranker.json").read_text(
            encoding="utf-8"
        )
    )


def test_bounded_pair_field_ranker_pins_successful_preflight_sources():
    contract = _contract()
    sources = contract["sources"]

    for path_key, hash_key in (
        ("metadata_preflight_summary", "metadata_preflight_summary_sha256"),
        ("extraction_validation_contract", "extraction_validation_contract_sha256"),
        ("pair_field_module", "pair_field_module_sha256"),
    ):
        path = ROOT / sources[path_key]
        canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical_bytes).hexdigest() == sources[hash_key]

    preflight = json.loads(
        (ROOT / sources["metadata_preflight_summary"]).read_text()
    )
    assert preflight["decision"] == "GO_TO_BOUNDED_PAIR_FIELD_MODEL_PREREGISTRATION"
    assert preflight["population"]["full_candidate_actions"] == 2264
    assert preflight["population"]["official_tp_action_variants"] == 90


def test_bounded_pair_field_ranker_architecture_is_fixed_and_small():
    architecture = _contract()["architecture"]
    blocks = architecture["blocks"]

    convolution_parameters = sum(
        block["in_channels"]
        * block["out_channels"]
        * block["kernel_size"] ** 3
        for block in blocks
    )
    groupnorm_parameters = sum(2 * block["out_channels"] for block in blocks)
    head_parameters = 48 * 16 + 16 + 16 * 1 + 1

    assert convolution_parameters + groupnorm_parameters + head_parameters == 20145
    assert architecture["exact_trainable_parameters"] == 20145
    assert architecture["trainable_parameter_max"] == 25000
    assert architecture["architecture_search_allowed"] is False
    assert architecture["pretrained_weights_allowed"] is False
    assert architecture["coordinate_family_route_sample_node_or_frame_inputs"] is False
    assert architecture["output"] == "unbounded_ranking_score_not_probability"


def test_bounded_pair_field_ranker_preserves_label_boundaries_and_weighting():
    contract = _contract()
    readiness = contract["dataset_readiness"]
    optimization = contract["optimization"]

    assert readiness["reliable_negative"] == "patched_official_fp"
    assert readiness["unknown_used_in_supervised_loss"] is False
    assert readiness["unknown_retained_in_heldout_ranking"] is True
    assert readiness["sparse_absence_is_negative"] is False
    assert readiness["exact_tp_event_count_required"] == 29
    assert readiness["exact_tp_action_variant_count_required"] == 90
    assert optimization["weighting_hierarchy"] == [
        "sample",
        "event",
        "label_side",
        "action",
    ]
    assert optimization["raw_pair_weighting_allowed"] is False
    assert optimization["fp_cap_per_event"] == 64


def test_bounded_pair_field_ranker_early_stopping_cannot_see_outer_fold():
    contract = _contract()
    stopping = contract["early_stopping"]
    validation = contract["outer_validation"]

    assert stopping["metric"] == "equal_event_weighted_pairwise_log_loss"
    assert stopping["recall_metric_used_for_early_stopping"] is False
    assert stopping["outer_heldout_fold_visible"] is False
    assert stopping["patience_epochs"] == 8
    assert stopping["final_refit_epochs"] == "floor_median_of_two_swap_best_epochs"
    assert validation["inner_selection"] == "swap_the_two_outer_training_folds"
    assert validation[
        "heldout_fold_never_guides_architecture_epoch_threshold_or_control_definition"
    ] is True
    assert validation["rank_tie_policy"] == (
        "pessimistic_all_equal_scores_count_ahead"
    )


def test_bounded_pair_field_ranker_controls_and_seed_stability_are_hard_gates():
    contract = _contract()
    controls = contract["controls"]
    gates = contract["hard_gates"]
    reproducibility = contract["reproducibility"]

    assert set(controls) >= {
        "nearest_distance",
        "geometry_only",
        "mask_only",
        "image_shuffled",
        "static_image",
    }
    assert contract["control_policy"]["definitions_locked_before_results"] is True
    assert controls["image_shuffled"]["minimum_moved_event_fraction"] == 0.8
    assert reproducibility["seeds"] == [314159, 271828, 161803]
    assert gates["minimum_seeds_passing_all_hard_gates"] == 2
    assert gates["catastrophic_seed_pooled_recall_at_10_below"] == 0.65
    assert gates["recall_at_10_margin_over_best_nonimage_control_min"] == 0.1
    assert gates["recall_at_10_margin_over_image_shuffled_min"] == 0.1
    assert gates["recall_at_10_margin_over_static_image_min"] == 0.05


def test_bounded_pair_field_ranker_remains_unimplemented_and_read_only():
    contract = _contract()
    interpretation = contract["interpretation"]

    assert interpretation["high_official_action_retrieval_is_biological_probability"] is False
    assert interpretation["image_gain_over_masks_proves_causal_mitosis_biology"] is False
    assert interpretation["temporal_gain_requires_static_image_margin"] is True
    assert contract["real_tensor_extraction_enabled"] is False
    assert contract["model_implementation_enabled"] is False
    assert contract["model_fitting_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["production_graph_mutation_enabled"] is False
    assert contract["locked_validation_opened"] is False
    assert contract["full_199_authorized"] is False
