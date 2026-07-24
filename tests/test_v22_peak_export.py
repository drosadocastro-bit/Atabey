import hashlib
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
scripts_dir = project_root / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from run_v22_unet_detection_shadow import _peak_rows
from run_v22_unet_official_action_availability import _read_checkpoint, _summarize


def test_peak_export_is_deterministic_across_frame_and_coordinate_order():
    locations = {
        ("sample_b", 2, 0.0, 2.0, 0.0): 0.98,
        ("sample_a", 2, 0.0, 3.0, 0.0): 0.99,
        ("sample_a", 2, 0.0, 1.0, 0.0): 0.97,
        ("sample_a", 1, 0.0, 4.0, 0.0): None,
    }

    rows = _peak_rows(
        locations,
        threshold=0.97,
        pool_kernel_um=3.0,
        tta="xy_d4_8_view",
    )

    assert [row["peak_id"] for row in rows] == [
        "unet:sample_a:t1:p00000",
        "unet:sample_a:t2:p00000",
        "unet:sample_a:t2:p00001",
        "unet:sample_b:t2:p00000",
    ]
    assert [row["y_um"] for row in rows] == [4.0, 1.0, 3.0, 2.0]


def test_official_action_contract_pins_the_unchanged_development_fixture():
    contract_path = (
        project_root
        / "tests/fixtures/v22_unet_official_action_development_46.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    fixture_path = project_root / contract["source_fixture"]

    assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == contract[
        "source_fixture_sha256"
    ]
    assert contract["expected_cases"] == 46
    assert contract["decision_contract"]["minimum_official_positive_divisions"] == 20
    assert contract["semantic_scoring_enabled"] is False
    assert contract["assignment_enabled"] is False
    assert contract["graph_mutation_enabled"] is False

def test_official_action_go_requires_all_46_rows():
    contract = json.loads(
        (
            project_root
            / "tests/fixtures/v22_unet_official_action_development_46.json"
        ).read_text(encoding="utf-8-sig")
    )
    rows = [
        {
            "sample_id": (
                "44b6_sample" if index == 0 else "6bba_sample"
            ),
            "cohort": "positive_control" if index < 13 else "baseline_unavailable",
            "official_positive_available": index < 20,
            "source_zero_perturbation": True,
        }
        for index in range(46)
    ]

    assert _summarize(rows, contract)["decision"] == "GO_FOR_SEMANTIC_SCORE_DEVELOPMENT"
    partial = _summarize(rows[:20], contract)
    assert partial["gates"]["complete"] is False
    assert partial["decision"] == "NO_GO"

def test_checkpoint_reader_restores_numeric_and_boolean_types(tmp_path):
    checkpoint = tmp_path / "checkpoint.csv"
    checkpoint.write_text(
        "case_id,sample_id,t,anchor_count,parent_peak_count,anchored_parent_count,"
        "division_action_count,registered_geometric_action_count,official_tp_action_count,"
        "official_positive_available,source_zero_perturbation,semantic_scoring_enabled,"
        "assignment_enabled,graph_mutated\n"
        "case,sample,2,3,4,2,5,1,1,True,True,False,False,False\n",
        encoding="utf-8",
    )

    row = _read_checkpoint(checkpoint)[0]

    assert row["t"] == 2
    assert row["division_action_count"] == 5
    assert row["official_positive_available"] is True
    assert row["semantic_scoring_enabled"] is False
    assert row["graph_mutated"] is False
