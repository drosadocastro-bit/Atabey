import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = (
    ROOT / "notebooks/V25_upstream_association_forensics_cuda_kaggle.ipynb"
)
EXPECTED_COMMIT = "34e24aec4f1d53b387da978febda93a3aa863013"
EXPECTED_CHECKPOINT = (
    "02e1d65756c3dc5928f68a66a8b0ef99be2a6905fa7bc017aa1d87dbe632fd03"
)
EXPECTED_PREDICTOR = (
    "c44e771ba5980b820f93091e03a303c25dfe8f3232e501f54dc9565731c234b9"
)


def _notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _source(cell: dict) -> str:
    source = cell["source"]
    return "".join(source) if isinstance(source, list) else source


def _code_cell_containing(fragment: str) -> str:
    matches = [
        _source(cell)
        for cell in _notebook()["cells"]
        if cell["cell_type"] == "code" and fragment in _source(cell)
    ]
    assert len(matches) == 1
    return matches[0]


def test_v25_kaggle_notebook_is_clean_and_syntactically_valid() -> None:
    notebook = _notebook()
    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["kernelspec"] == {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    assert len(notebook["cells"]) == 17
    for index, cell in enumerate(notebook["cells"], start=1):
        expected_language = "python" if cell["cell_type"] == "code" else "markdown"
        assert cell["metadata"]["language"] == expected_language
        assert cell["metadata"]["id"] == cell["id"]
        assert cell.get("outputs", []) == []
        assert cell.get("execution_count") is None
        if cell["cell_type"] == "code":
            ast.parse(_source(cell), filename=f"{NOTEBOOK_PATH}:cell-{index}")


def test_v25_kaggle_notebook_preserves_frozen_observability_boundaries() -> None:
    source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    assert f'EXPECTED_COMMIT = "{EXPECTED_COMMIT}"' in source
    assert EXPECTED_CHECKPOINT in source
    assert EXPECTED_PREDICTOR in source
    assert "tracksdata.git@39dccf3a243e44274759468cb31b2ad9e7fc1d09" in source
    assert "kaggle-cell-tracking-competition.git@075fc5f5a52d11077f9dc2b074644618f26939e2" in source
    assert 'ROOT = Path("/tmp/Atabey")' in source
    assert "AUTHORIZE_V25_OBSERVABILITY = True" in source
    assert "run_v25_upstream_association_forensics.py" in source
    assert '"--resume"' in source
    assert '"--unet-batch-size", "4"' in source
    assert "--max-timepoints" not in source
    assert 'summary["completed_samples"] == 16' in source
    assert 'provenance["max_timepoints"] is None' in source
    assert '"score_claim": False' in source
    assert '"selector_enabled": False' in source
    assert '"graph_mutation": False' in source
    assert '"submission_authorized": False' in source
    assert "model.train(" not in source
    assert "optimizer.load_state_dict" not in source
    assert "submission.csv" not in source


def test_v25_kaggle_notebook_captures_cuda_hardware_telemetry() -> None:
    source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    assert '"torch==2.10.0+cu126"' in source
    assert '"numpy==2.2.6"' in source
    assert '"scipy==1.16.3"' in source
    assert '"nvidia-ml-py"' in source
    assert "torch.cuda.get_arch_list()" in source
    assert 'torch.ones(1, device="cuda").relu().cpu().item()' in source
    assert "pynvml.nvmlDeviceGetUtilizationRates" in source
    assert "pynvml.nvmlDeviceGetPowerUsage" in source
    assert "pynvml.nvmlDeviceGetClockInfo" in source
    assert "telemetry_thread.join(timeout=10)" in source
    assert "v25_cuda_telemetry.csv" in source
    assert "v25_cuda_telemetry.json" in source
    assert "v25_cuda_telemetry.png" in source
    assert '"hardware_telemetry_is_deterministic": False' in source


def test_v25_kaggle_notebook_finds_deep_auxiliary_mounts(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    train_dir = input_root / "competitions/biohub/train"
    train_dir.mkdir(parents=True)
    for index in range(199):
        (train_dir / f"sample_{index:03d}.zarr").mkdir()
        (train_dir / f"sample_{index:03d}.geff").mkdir()

    support_repo = input_root / "datasets/pilkwang/support/payload/repo"
    (support_repo / "scripts").mkdir(parents=True)
    predictor = support_repo / "scripts/predict_unet_transformer.py"
    predictor.write_text("# fixture\n", encoding="utf-8")
    predictor_hash = hashlib.sha256(predictor.read_bytes()).hexdigest()

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

    discovery = _code_cell_containing('INPUT_ROOT = Path("/kaggle/input")')
    discovery = discovery[discovery.index('INPUT_ROOT = Path("/kaggle/input")') :]
    discovery = (
        discovery.replace(
            'INPUT_ROOT = Path("/kaggle/input")',
            f"INPUT_ROOT = Path({str(input_root)!r})",
        )
        .replace(EXPECTED_CHECKPOINT, checkpoint_hash)
        .replace(EXPECTED_PREDICTOR, predictor_hash)
    )
    namespace = {"Path": Path, "hashlib": hashlib, "json": json}
    exec(compile(discovery, "<v25-kaggle-input-discovery>", "exec"), namespace)

    assert namespace["TRAIN_DIR"] == train_dir
    assert namespace["SUPPORT_REPO"] == support_repo
    assert namespace["WEIGHTS"] == weights