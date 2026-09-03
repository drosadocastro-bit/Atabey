import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "v25_upstream_association_forensics_results.json"


def _result() -> dict:
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def test_v25_result_taxonomy_is_complete_and_internally_consistent() -> None:
    result = _result()
    taxonomy = result["lost_edge_taxonomy"]
    classified = sum(value for key, value in taxonomy.items() if key != "total")
    assert classified == taxonomy["total"] == 1069
    assert taxonomy["unresolved_insufficient_telemetry"] == 0
    assert sum(result["candidate_generation_decomposition"].values()) == 243

    selection = result["candidate_selection_decomposition"]
    assert (
        selection["forward_prediction_ranking_loss"]
        + selection["reverse_mutuality_conflict"]
        == taxonomy["candidate_selection_ranking_failure"]
        == 704
    )


def test_v25_result_accounts_for_all_samples_and_lost_edges() -> None:
    result = _result()
    class_keys = {
        "candidate_generation_failure",
        "candidate_selection_ranking_failure",
        "post_link_pruning_interaction",
        "metric_node_adjustment_only_effect",
    }
    assert len(result["per_sample"]) == 16
    assert (
        sum(
            sum(sample.get(key, 0) for key in class_keys)
            for sample in result["per_sample"].values()
        )
        == result["lost_edge_taxonomy"]["total"]
    )


def test_v25_result_preserves_observability_boundaries() -> None:
    result = _result()
    provenance = result["provenance"]
    assert provenance["sample_count"] == 16
    assert provenance["complete_sequences"] is True
    assert provenance["graph_mutation"] is False
    assert provenance["score_claim"] is False
    assert provenance["selector_claim"] is False
    assert provenance["submission_authorized"] is False
    assert result["decision"] == "OBSERVABILITY_COMPLETE_NO_INTERVENTION_AUTHORIZED"
    assert result["replay_validation"]["recorded_edges"] == 86778
    assert result["replay_validation"]["replayed_edges"] == 86778
    assert result["replay_validation"]["missing_from_replay"] == 0
    assert result["replay_validation"]["extra_in_replay"] == 0


def test_v25_result_matches_local_archive_when_available() -> None:
    result = _result()
    archive = ROOT / result["source_archive"]["path"]
    if not archive.exists():
        return
    assert archive.stat().st_size == result["source_archive"]["bytes"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == result["source_archive"]["sha256"]