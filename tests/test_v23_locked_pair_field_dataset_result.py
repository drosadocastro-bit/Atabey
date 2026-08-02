import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "v23_locked_pair_field_dataset_summary.json"


def test_locked_pair_field_dataset_result_is_pinned():
    result = json.loads(SUMMARY.read_text(encoding="utf-8"))

    assert result["status"] == "v23_locked_pair_field_dataset_result"
    assert result["decision"] == "GO_TO_BOUNDED_PAIR_FIELD_MODEL_IMPLEMENTATION"
    assert result["parent_fields"] == 54
    assert result["events"] == 29
    assert result["actions"] == 2264
    assert result["labels"] == {
        "official_fp": 2174,
        "official_tp": 90,
        "official_unsupported": 0,
    }
    assert result["selected_training_actions"] == 1603
    assert result["dataset_readiness"]["events_with_tp_and_fp"] == 29
    assert result["dataset_readiness"]["by_family"] == {
        "44b6": 9,
        "6bba": 20,
    }
    assert result["dataset_readiness"]["by_outer_training_complement"] == {
        "1": 20,
        "2": 17,
        "3": 21,
    }
    assert all(result["prewrite_gates"].values())

    manifest = result["tensor_manifest"]
    assert manifest["all_parent_tensors_valid"] is True
    assert manifest["parents_sha256"] == (
        "d81aeb498135e87caf6ebffa05d7d6d3d3e8b50359762ff418e81c0b3c8c981d"
    )
    assert manifest["actions_sha256"] == (
        "39c49efdf3c93d2ac6c791e85db4c26fe79bf13bf34c76b27107ffa54096a72f"
    )
    assert manifest["events_sha256"] == (
        "d09275c827126adf869815d8c907c09f1e143a2f1d3f57cf70721110b4bcb1c2"
    )
    assert result["model_fitted"] is False
    assert result["assignment_enabled"] is False
