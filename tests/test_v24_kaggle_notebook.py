import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks/V24_score_first_tracking_kaggle.ipynb"
EXPECTED_COMMIT = "3ef5190ceaf6180096dc6893563944fc42cfd98b"
EXPECTED_CHECKPOINT = (
    "02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03"
)


def _notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _source(cell: dict) -> str:
    source = cell["source"]
    return "".join(source) if isinstance(source, list) else source


def test_v24_kaggle_notebook_is_clean_and_syntactically_valid():
    notebook = _notebook()
    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["kernelspec"] == {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    assert len(notebook["cells"]) == 11
    for index, cell in enumerate(notebook["cells"], start=1):
        assert cell["cell_type"] in {"code", "markdown"}
        assert cell.get("id"), index
        expected_language = "python" if cell["cell_type"] == "code" else "markdown"
        assert cell["metadata"]["language"] == expected_language
        assert cell["metadata"]["id"] == cell["id"]
        assert cell.get("outputs", []) == []
        assert cell.get("execution_count") is None
        if cell["cell_type"] == "code":
            ast.parse(_source(cell), filename=f"{NOTEBOOK_PATH}:cell-{index}")


def test_v24_kaggle_notebook_preserves_frozen_execution_gates():
    source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    assert f'EXPECTED_COMMIT = "{EXPECTED_COMMIT}"' in source
    assert EXPECTED_CHECKPOINT in source
    assert 'RUN_MODE = "smoke"' in source
    assert "AUTHORIZE_FULL_27 = False" in source
    assert 'SAMPLE_SELECTOR = "smoke" if RUN_MODE == "smoke" else "all"' in source
    assert '"--verify-determinism"' in source
    assert "--max-timepoints" not in source
    assert '"no_training": True' in source
    assert 'boundaries["model_retraining"] is False' in source
    assert 'boundaries["hybrid_enabled"] is False' in source
    assert 'boundaries["submission_authorized"] is False' in source