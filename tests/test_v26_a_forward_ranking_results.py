import gzip
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "v26a_forward_ranking_ablation_results.json"


def _result() -> dict:
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def test_v26_a_result_applies_the_binding_interest_gate() -> None:
    result = _result()
    transitions = result["edge_transitions"]
    gate = result["interest_gate"]

    assert transitions["recovered_v19_credited_edges"] == 148
    assert "sparse ground truth" in transitions["incorrect_edge_semantics"]
    assert transitions["forward_prediction_ranking_loss"] == 108
    assert transitions["net_association_delta"] == 179 - 107 == 72
    assert transitions["net_incorrect_edge_delta"] == 1658 - 867 == 791
    assert gate["minimum_forward_ranking_recoveries"] is True
    assert gate["positive_net_association_delta"] is True
    assert gate["bounded_net_incorrect_edge_delta"] is False
    assert gate["bounded_new_incorrect_edge_ratio"] is False
    assert gate["passed"] is False
    assert result["decision"] == "NO_GO"


def test_v26_a_result_preserves_research_boundaries() -> None:
    result = _result()
    provenance = result["provenance"]

    assert provenance["sample_count"] == 16
    assert provenance["scientific_replay_deterministic"] is True
    assert provenance["production_tuning_authorized"] is False
    assert provenance["submission_authorized"] is False
    assert result["official_metric"]["samples_improved"] == 9
    assert result["official_metric"]["samples_regressed"] == 7


def test_v26_a_result_matches_local_archive_when_available() -> None:
    result = _result()
    archive_path = ROOT / result["source_archive"]["path"]
    if not archive_path.exists():
        return

    assert archive_path.stat().st_size == result["source_archive"]["bytes"]
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == result["source_archive"]["sha256"]
    with zipfile.ZipFile(archive_path) as archive:
        assert len(archive.namelist()) == result["source_archive"]["entries"]
        run_record = json.loads(archive.read("notebook_run_record.json"))
        summary = json.loads(archive.read("summary.json"))
        samples = [
            json.loads(gzip.decompress(archive.read(name)))
            for name in archive.namelist()
            if name.startswith("samples/") and name.endswith(".json.gz")
        ]

    assert run_record["decision"] == result["decision"]
    assert run_record["atabey_commit"] == result["provenance"]["atabey_commit"]
    assert len(samples) == summary["sample_count"] == 16
    assert summary["aggregate_edge_transitions"]["newly_incorrect_edges"] == 1658
    assert summary["interest_gate"]["observed"]["net_incorrect_edge_delta"] == 791
    assert all(sample["deterministic_replay"] for sample in samples)