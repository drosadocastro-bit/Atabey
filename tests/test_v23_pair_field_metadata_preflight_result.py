import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _summary() -> dict:
    return json.loads(
        (ROOT / "v23_pair_field_metadata_preflight_summary.json").read_text(
            encoding="utf-8"
        )
    )


def test_pair_field_metadata_preflight_reproduces_population_and_tp_parity():
    summary = _summary()
    population = summary["population"]
    events = summary["events"]

    assert summary["decision"] == "GO_TO_BOUNDED_PAIR_FIELD_MODEL_PREREGISTRATION"
    assert population == {
        "events": 29,
        "full_candidate_actions": 2264,
        "max_actions_per_event": 199,
        "official_tp_action_variants": 90,
        "parent_fields": 54,
        "samples": 22,
    }
    assert len(events) == 29
    assert len({event["event_id"] for event in events}) == 29
    assert sum(event["full_candidate_actions"] for event in events) == 2264
    assert sum(event["observed_tp_actions"] for event in events) == 90
    assert all(event["official_label_parity"] for event in events)


def test_pair_field_metadata_preflight_passes_all_locked_gates():
    summary = _summary()

    assert all(summary["integrity_gates"].values())
    assert all(summary["resource_gates"].values())
    assert all(summary["synthetic_tensor_checks"].values())
    assert summary["fold_family_events"] == {
        "1": {"44b6": 2, "6bba": 7},
        "2": {"44b6": 4, "6bba": 8},
        "3": {"44b6": 3, "6bba": 5},
    }


def test_pair_field_metadata_preflight_keeps_real_extraction_disabled():
    summary = _summary()
    storage = summary["storage"]

    assert storage["cached_uncompressed_gib"] < 0.03
    assert storage["naive_assembled_uncompressed_gib"] > 1.5
    assert storage["cache_reduction_fraction"] > 0.98
    assert summary["tensor_writes_enabled"] is False
    assert summary["tensors_written"] == 0
    assert summary["model_fitted"] is False
    assert summary["assignment_enabled"] is False
    assert summary["graph_mutation"] is False
    assert summary["full_199_authorized"] is False
    assert all(not event["tensor_written"] for event in summary["events"])
    assert all(not event["graph_mutated"] for event in summary["events"])
