import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks/V26A_forward_ranking_ablation_kaggle.ipynb"
CONTRACT_PATH = ROOT / "tests/fixtures/v26_a_forward_ranking_ablation.json"
EXPECTED_COMMIT = "dd2598dc3f5fb1dc7352f844749b307195b13c12"


def _notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else source


def test_v26_a_notebook_has_valid_python_and_clean_outputs() -> None:
    notebook = _notebook()

    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            ast.parse(_source(cell))
            assert cell.get("execution_count") is None
            assert cell.get("outputs", []) == []


def test_v26_a_notebook_pins_source_archive_runtime_and_cohort() -> None:
    notebook_source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert EXPECTED_COMMIT in notebook_source
    assert contract["frozen_v25_archive"]["sha256"] in notebook_source
    assert str(contract["frozen_v25_archive"]["bytes"]) in notebook_source.replace("_", "")
    alternate = contract["frozen_v25_archive"]["alternate_containers"][0]
    assert alternate["sha256"] in notebook_source
    assert str(alternate["bytes"]) in notebook_source.replace("_", "")
    assert "archive_identity in ACCEPTED_V25_ARCHIVES" in notebook_source
    assert "numpy==2.2.6" in notebook_source
    assert "scipy==1.16.3" in notebook_source
    assert "39dccf3a243e44274759468cb31b2ad9e7fc1d09" in notebook_source
    assert "075fc5f5a52d11077f9dc2b074644618f26939e2" in notebook_source
    assert all(sample_id in notebook_source for sample_id in contract["cohort"]["sample_ids"])
    assert '.rglob(f"{SAMPLE_IDS[0]}.geff")' in notebook_source


def test_v26_a_notebook_covers_audit_and_replay_contract() -> None:
    notebook_source = "\n".join(_source(cell) for cell in _notebook()["cells"])

    for section in (
        "## 1. Configure Repository Paths",
        "## 2. Load V25 Association Data",
        "## 3. Validate Data Integrity",
        "## 4. Compare Associations with Baseline",
        "## 5. Identify Orphaned and Duplicate Records",
        "## 6. Analyze Association Changes",
        "## 7. Export Audit Results",
    ):
        assert section in notebook_source
    assert "run_v26_a_forward_ranking_ablation.py" in notebook_source
    assert '"--output-dir", str(OUTPUT_A)' in notebook_source
    assert '"--output-dir", str(OUTPUT_B)' in notebook_source
    assert "scientific_payload" in notebook_source
    assert 'clean.pop("runtime_seconds", None)' in notebook_source
    assert 'clean.pop("peak_python_tracemalloc_bytes", None)' in notebook_source
    assert '"v25_archive_bytes": archive_identity[0]' in notebook_source
    assert '"v25_archive_sha256": archive_identity[1]' in notebook_source
    assert "interest_gate" in notebook_source
    assert "duplicate_or_orphan_records" in notebook_source


def test_v26_a_notebook_preserves_intervention_boundaries() -> None:
    notebook_source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    lower = notebook_source.lower()

    assert "candidate generation" in lower
    assert "reverse mutuality" in lower
    assert "pruning" in lower
    assert "no tuning" in lower
    assert "production_tuning_authorized" in notebook_source
    assert "submission_authorized" in notebook_source
    assert "predict_unet_transformer" not in notebook_source
    assert "torch.cuda" not in notebook_source