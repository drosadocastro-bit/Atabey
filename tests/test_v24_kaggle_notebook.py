import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks/V24_score_first_tracking_kaggle.ipynb"
EXPECTED_COMMIT = "905671f0ad1b7e2ab868e5a84a322c565d52f273"
EXPECTED_CHECKPOINT = (
    "02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03"
)


def _notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _source(cell: dict) -> str:
    source = cell["source"]
    return "".join(source) if isinstance(source, list) else source


def _code_cell_starting(prefix: str) -> str:
    matches = [
        _source(cell)
        for cell in _notebook()["cells"]
        if cell["cell_type"] == "code" and _source(cell).startswith(prefix)
    ]
    assert len(matches) == 1
    return matches[0]


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
    assert "tracksdata.git@39dccf3a243e44274759468cb31b2ad9e7fc1d09" in source
    assert (
        "kaggle-cell-tracking-competition.git@075fc5f5a52d11077f9dc2b074644618f26939e2"
        in source
    )
    assert 'ROOT = Path("/tmp/Atabey")' in source
    assert 'ROOT = Path("/kaggle/working/Atabey")' not in source
    assert '"--no-deps", *pinned_official_packages' in source
    assert 'f"{ROOT}[official-metrics]"' not in source
    assert 'RUN_MODE = "full_27"' in source
    assert "AUTHORIZE_FULL_27 = True" in source
    assert "v24_score_first_tracking_v24_3_" in source
    assert 'SAMPLE_SELECTOR = "smoke" if RUN_MODE == "smoke" else "all"' in source
    assert '"--verify-determinism"' in source
    assert "--max-timepoints" not in source
    assert '"no_training": True' in source
    assert 'boundaries["model_retraining"] is False' in source
    assert 'boundaries["hybrid_enabled"] is False' in source
    assert 'boundaries["submission_authorized"] is False' in source


def test_v24_kaggle_notebook_finds_deep_auxiliary_mounts(tmp_path):
    input_root = tmp_path / "input"
    train_dir = input_root / "competitions/biohub/train"
    train_dir.mkdir(parents=True)
    for index in range(199):
        (train_dir / f"sample_{index:03d}.zarr").mkdir()
        (train_dir / f"sample_{index:03d}.geff").mkdir()

    support_repo = input_root / "datasets/pilkwang/support/payload/repo"
    (support_repo / "scripts").mkdir(parents=True)
    (support_repo / "scripts/predict_unet_transformer.py").write_text(
        "# fixture\n", encoding="utf-8"
    )
    checkpoint_dir = input_root / "datasets/drakus74/checkpoint/artifact"
    checkpoint_dir.mkdir(parents=True)
    weights = checkpoint_dir / "edge_predictor_best.pth"
    weights.write_bytes(b"frozen-checkpoint-fixture")
    checkpoint_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    (checkpoint_dir / "config.json").write_text(
        json.dumps(
            {
                "window_size": 2,
                "downsample": [1, 4, 4],
                "unet_out_channels": 32,
                "pool_kernel_um": 5.0,
            }
        ),
        encoding="utf-8",
    )

    source = _code_cell_starting('INPUT_ROOT = Path("/kaggle/input")')
    source = source.replace(
        'INPUT_ROOT = Path("/kaggle/input")', f"INPUT_ROOT = Path({str(input_root)!r})"
    ).replace(EXPECTED_CHECKPOINT, checkpoint_hash)
    namespace = {"Path": Path, "hashlib": hashlib, "json": json}
    exec(compile(source, "<v24-input-discovery>", "exec"), namespace)

    assert namespace["TRAIN_DIR"] == train_dir
    assert namespace["SUPPORT_REPO"] == support_repo
    assert namespace["WEIGHTS"] == weights