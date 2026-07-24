import hashlib
import json
from collections import Counter
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent


def test_v22_semantic_assignment_folds_are_complete_blocked_and_balanced():
    fixture_path = (
        project_root
        / "tests/fixtures/v22_joint_semantic_assignment_development.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
    folds = fixture["folds"]
    samples = [sample for fold in folds for sample in fold["samples"]]

    assert len(folds) == 3
    assert len(samples) == 27
    assert len(set(samples)) == 27
    assert [fold["official_positive_events"] for fold in folds] == [13, 13, 13]
    assert [fold["registered_events"] for fold in folds] == [15, 16, 15]

    action_rows = _read_csv(
        project_root / fixture["source_action_availability_csv"]
    )
    by_sample = {}
    for row in action_rows:
        by_sample.setdefault(row["sample_id"], []).append(row)

    assert set(samples) == set(by_sample)
    for fold in folds:
        fold_rows = [row for sample in fold["samples"] for row in by_sample[sample]]
        assert len(fold_rows) == fold["registered_events"]
        assert sum(row["official_positive_available"] == "True" for row in fold_rows) == 13
        positive_44b6_samples = {
            row["sample_id"]
            for row in fold_rows
            if row["sample_id"].startswith("44b6_")
            and row["official_positive_available"] == "True"
        }
        assert len(positive_44b6_samples) == 1


def test_v22_semantic_assignment_sources_and_epistemic_guards_are_frozen():
    fixture_path = (
        project_root
        / "tests/fixtures/v22_joint_semantic_assignment_development.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))

    for path_key, hash_key in (
        ("source_action_availability_csv", "source_action_availability_sha256"),
        ("source_peak_csv", "source_peak_sha256"),
        ("source_contract", "source_contract_sha256"),
    ):
        source_path = project_root / fixture[path_key]
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == fixture[hash_key]

    labels = fixture["labels"]
    assert labels["negative"] == "patched_official_fp_only"
    assert labels["sparse_absence_is_negative"] is False
    assert labels["direct_official_scorer_required"] is True

    constraint = fixture["constraint_layer"]
    assert constraint["plain_one_to_one_lsap_allowed"] is False
    assert constraint["division_consumes_two_daughters_atomically"] is True
    assert constraint["continuation_action_required"] is True
    assert constraint["abstain_action_required"] is True
    assert constraint["assignment_bonus_allowed"] is False
    assert constraint["ground_truth_visible_to_solver"] is False
    assert constraint["solver"] == "scipy.optimize.milp"
    assert constraint["time_limit_seconds_per_component"] == 2.0
    assert constraint["timeout_outcome"] == "abstain"

    continuation = fixture["semantic_model"]["continuation_head"]
    assert continuation["reference_is_ground_truth"] is False
    assert continuation["missing_or_low_margin_outcome"] == "abstain"
    assert "sampling_weights" in fixture["semantic_model"]["calibration"]

    assert fixture["semantic_scoring_enabled"] is False
    assert fixture["assignment_enabled"] is False
    assert fixture["production_graph_mutation_enabled"] is False
    assert fixture["locked_validation_opened"] is False
    assert fixture["full_199_authorized"] is False


def test_v22_semantic_assignment_candidate_population_matches_frozen_result():
    fixture = json.loads(
        (
            project_root
            / "tests/fixtures/v22_joint_semantic_assignment_development.json"
        ).read_text(encoding="utf-8-sig")
    )
    rows = _read_csv(project_root / fixture["source_action_availability_csv"])

    assert len(rows) == 46
    assert sum(int(row["division_action_count"]) for row in rows) == 268822
    assert sum(int(row["official_tp_action_count"]) for row in rows) == 64
    assert sum(row["official_positive_available"] == "True" for row in rows) == 39
    assert Counter(row["cohort"] for row in rows) == {
        "baseline_unavailable": 25,
        "baseline_nonofficial_action": 8,
        "positive_control": 13,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))
