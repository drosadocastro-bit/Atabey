import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks/V24_3_full_199_score_validation_kaggle.ipynb"
EXPECTED_COMMIT = "2af9cbf3f192171e669db223967f8ba8eedb6d81"
EXPECTED_CHECKPOINT = (
    "02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03"
)


def _notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _source(cell: dict) -> str:
    source = cell["source"]
    return "\n".join(source) if isinstance(source, list) else source


def test_full_199_notebook_is_clean_and_syntactically_valid():
    notebook = _notebook()
    assert notebook["nbformat"] == 4
    assert len(notebook["cells"]) == 11
    for index, cell in enumerate(notebook["cells"], start=1):
        assert cell["cell_type"] in {"code", "markdown"}
        assert cell.get("id"), index
        assert cell["metadata"]["language"] == (
            "python" if cell["cell_type"] == "code" else "markdown"
        )
        assert cell["metadata"]["id"] == cell["id"]
        assert cell.get("outputs", []) == []
        assert cell.get("execution_count") is None
        if cell["cell_type"] == "code":
            ast.parse(_source(cell), filename=f"{NOTEBOOK_PATH}:cell-{index}")


def test_full_199_notebook_preserves_frozen_shard_contract():
    source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    assert f'EXPECTED_COMMIT = "{EXPECTED_COMMIT}"' in source
    assert EXPECTED_CHECKPOINT in source
    assert 'SHARD_INDEX = 0  # Run 0 first; then change only this value to 1.' in source
    assert "SHARD_COUNT = 2" in source
    assert "AUTHORIZE_FULL_199_SCORE_VALIDATION = True" in source
    assert "run_v24_3_full_199_score_validation.py" in source
    assert "v24_3_full_199_score_validation.json" in source
    assert "v24_3_short_fragment_shadow_full_27_report.json" in source
    assert 'expected_count = 100 if SHARD_INDEX == 0 else 99' in source
    assert '"--verify-determinism"' in source
    assert '"--resume"' in source
    assert "--max-timepoints" not in source
    assert 'summary["submission_authorized"] is False' in source
    assert '"no_training": True' in source
    assert "The 172 checkpoint-training samples provide population context" in source
