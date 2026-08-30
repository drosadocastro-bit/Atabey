import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks/V24_7_route_90_commitment_ilp_kaggle.ipynb"
EXPECTED_COMMIT = "b5fc79582c9ce713587fa94aa8cf73fd0aa68e40"
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


def _code_cell_starting(prefix: str) -> str:
    matches = [
        _source(cell)
        for cell in _notebook()["cells"]
        if cell["cell_type"] == "code" and _source(cell).startswith(prefix)
    ]
    assert len(matches) == 1
    return matches[0]


def test_route_90_notebook_is_clean_and_syntactically_valid() -> None:
    notebook = _notebook()
    assert notebook["nbformat"] == 4
    kernelspec = notebook["metadata"]["kernelspec"]
    assert kernelspec["language"] == "python"
    assert kernelspec["name"] == "python3"
    assert kernelspec["display_name"]
    assert len(notebook["cells"]) == 11
    for index, cell in enumerate(notebook["cells"], start=1):
        assert cell["cell_type"] in {"code", "markdown"}
        assert cell.get("id"), index
        assert cell.get("outputs", []) == []
        assert cell.get("execution_count") is None
        if cell["cell_type"] == "code":
            ast.parse(_source(cell), filename=f"{NOTEBOOK_PATH}:cell-{index}")


def test_route_90_notebook_preserves_frozen_shadow_gates() -> None:
    source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    assert f'EXPECTED_COMMIT = "{EXPECTED_COMMIT}"' in source
    assert EXPECTED_CHECKPOINT in source
    assert EXPECTED_PREDICTOR in source
    assert "tracksdata.git@39dccf3a243e44274759468cb31b2ad9e7fc1d09" in source
    assert "kaggle-cell-tracking-competition.git@075fc5f5a52d11077f9dc2b074644618f26939e2" in source
    assert 'ROOT = Path("/tmp/Atabey")' in source
    assert "from scipy.optimize import milp" in source
    assert "AUTHORIZE_ROUTE_90_SHADOW = True" in source
    assert "run_v24_7_route_90_shadow.py" in source
    assert '"--resume"' in source
    assert '"--verify-determinism"' in source
    assert "--max-timepoints" not in source
    assert 'summary["sample_count"] == 90' in source
    assert 'summary["threshold_tuning"] is False' in source
    assert '"no_training": True' in source
    assert "optimizer.load_state_dict" not in source
    assert "model.train(" not in source
    assert "submission.csv" not in source


def test_route_90_notebook_runs_canary_before_full_cohort() -> None:
    source = "\n".join(_source(cell) for cell in _notebook()["cells"])
    assert '"--preflight-only"' in source
    assert 'preflight_summary["status"] == "v24_7_route_90_preflight_complete"' in source
    assert 'preflight_summary["sample_count"] == 1' in source
    assert 'preflight_summary["graph_mutated"] is False' in source
    assert source.index('"--preflight-only"') < source.index("subprocess.run(command")


def test_route_90_notebook_probes_compiled_runtime_in_fresh_process() -> None:
    install_source = _code_cell_starting("pinned_official_packages = [")
    assert '"https://download.pytorch.org/whl/cu126"' in install_source
    assert '"torch==2.10.0+cu126"' in install_source
    assert '"torchvision==0.25.0+cu126"' in install_source
    assert '"numpy==2.2.6"' in install_source
    assert '"scipy==1.16.3"' in install_source
    assert "runtime_probe = subprocess.run(" in install_source
    assert "from scipy.optimize import milp" in install_source
    assert "torch.cuda.get_arch_list()" in install_source
    assert 'torch.ones(1, device="cuda").relu().cpu().item()' in install_source
    assert "runtime_probe.stdout" in install_source
    tree = ast.parse(install_source)
    top_level_imports = {
        alias.name
        for statement in tree.body
        if isinstance(statement, ast.Import)
        for alias in statement.names
    }
    top_level_from_imports = {
        statement.module
        for statement in tree.body
        if isinstance(statement, ast.ImportFrom)
    }
    assert top_level_imports.isdisjoint({"numpy", "scipy", "torch"})
    assert "scipy.optimize" not in top_level_from_imports


def test_route_90_notebook_finds_deep_auxiliary_mounts(tmp_path: Path) -> None:
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

    source = _code_cell_starting('INPUT_ROOT = Path("/kaggle/input")')
    source = (
        source.replace(
            'INPUT_ROOT = Path("/kaggle/input")',
            f"INPUT_ROOT = Path({str(input_root)!r})",
        )
        .replace(EXPECTED_CHECKPOINT, checkpoint_hash)
        .replace(EXPECTED_PREDICTOR, predictor_hash)
    )
    namespace = {"Path": Path, "hashlib": hashlib, "json": json}
    exec(compile(source, "<route-90-input-discovery>", "exec"), namespace)

    assert namespace["TRAIN_DIR"] == train_dir
    assert namespace["SUPPORT_REPO"] == support_repo
    assert namespace["WEIGHTS"] == weights