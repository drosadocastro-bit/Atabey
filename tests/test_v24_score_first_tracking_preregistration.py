import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "tests/fixtures/v24_score_first_tracking.json"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v24_sources_are_pinned_before_runner_implementation():
    contract = _contract()
    sources = contract["sources"]
    for path_key, hash_key in (
        ("development_fixture", "development_fixture_sha256"),
        ("checkpoint_contract", "checkpoint_contract_sha256"),
        ("official_tracking_metric", "official_tracking_metric_sha256"),
        ("v19_builder", "v19_builder_sha256"),
        ("hybrid_defaults", "hybrid_defaults_sha256"),
        ("atabey_linker", "atabey_linker_sha256"),
        ("unet_shadow_loader", "unet_shadow_loader_sha256"),
        ("unet_graph_module", "unet_graph_module_sha256"),
        ("runner", "runner_sha256"),
    ):
        assert _sha256(ROOT / sources[path_key]) == sources[hash_key]
    assert sources["predictor_runtime_sha256_required"] is True


def test_v24_cohort_is_exactly_the_checkpoint_held_out_set():
    contract = _contract()
    source = json.loads(
        (ROOT / contract["sources"]["development_fixture"]).read_text()
    )
    source_samples = sorted({case["sample_id"] for case in source["cases"]})
    cohort = contract["cohort"]
    assert source_samples == sorted(cohort["sample_ids"])
    assert len(source_samples) == cohort["sample_count"] == 27
    assert cohort["family_counts"] == {"44b6": 5, "6bba": 22}
    assert cohort["full_sequences"] is True

    checkpoint = contract["checkpoint"]
    checkpoint_contract = json.loads(
        (ROOT / contract["sources"]["checkpoint_contract"]).read_text()
    )
    assert checkpoint["training_samples"] == 172
    assert checkpoint["held_out_samples"] == 27
    assert checkpoint_contract["expected_clean_training_samples"] == 172
    assert checkpoint_contract["expected_held_out_development_samples"] == 27
    assert checkpoint["development_labels_used_for_fit_or_selection"] is False
    assert checkpoint_contract["development_labels_used_for_fit_or_selection"] is False


def test_v24_arms_separate_detector_and_linker_questions():
    contract = _contract()
    arms = {arm["name"]: arm for arm in contract["arms"]}
    assert set(arms) == {
        "v19_frozen_reference",
        "e016_atabey_relink",
        "e016_native_graph",
    }
    assert arms["e016_atabey_relink"]["linker"] == "motion_mutual_9um"
    assert arms["e016_atabey_relink"]["division_injection"] == "none"
    assert arms["e016_native_graph"]["linker"] == "pinned_public_native_edge_head"
    assert contract["boundaries"]["hybrid_enabled"] is False


def test_v24_uses_official_score_first_generalization_gates():
    contract = _contract()
    evaluation = contract["evaluation"]
    gates = contract["go_gates"]
    assert evaluation["primary_metric"] == "official_adjusted_edge_jaccard"
    assert evaluation["official_aggregation_required"] is True
    assert set(evaluation["report_by"]) == {
        "sample",
        "family",
        "v19_reference_route",
        "deterministic_fold",
    }
    assert gates["pooled_adjusted_edge_delta_min"] == 0.02
    assert gates["each_family_adjusted_edge_delta_min"] == -0.01
    assert gates["each_fold_adjusted_edge_delta_min"] == -0.02
    assert gates["completed_samples_required"] == 27
    assert gates["deterministic_replay_required"] is True


def test_v24_remains_preregistered_and_bounded():
    contract = _contract()
    assert contract["status"] == "runner_implemented_ready_for_smoke"
    assert contract["boundaries"] == {
        "runner_implemented": True,
        "hybrid_enabled": False,
        "threshold_tuning": False,
        "model_retraining": False,
        "full_199_authorized": False,
        "submission_authorized": False,
        "production_graph_mutation": False,
    }
