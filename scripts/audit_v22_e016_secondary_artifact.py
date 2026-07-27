"""Audit provenance and offline loadability of the E016 secondary checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_WEIGHT_SHA256 = (
    "9bac2fa0dadc4a6fc1899e0caf187f4b553e0a7cd90ba1261a68b35ffe9e305f"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.artifact_dir
    manifest_path = root / "ARTIFACT_MANIFEST.json"
    weight_path = root / "edge_predictor_best.pth"
    config_path = root / "config.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    weight_hash = sha256(weight_path)
    manifest_hash = sha256(manifest_path)
    expected_manifest_weight = manifest["model"]["weight_sha256"]
    training = manifest["model"]["training"]
    config = json.loads(config_path.read_text(encoding="utf-8"))

    load_ok = False
    state_dict_keys = None
    load_error = None
    try:
        import torch

        state = torch.load(weight_path, map_location="cpu", weights_only=True)
        state_dict_keys = len(state)
        load_ok = isinstance(state, dict) and state_dict_keys > 0
    except Exception as exc:  # pragma: no cover - environment-dependent
        load_error = f"{type(exc).__name__}: {exc}"

    # The public artifact explicitly says it was fit over the entire competition
    # training cohort. That makes it unsuitable for unbiased development labels
    # drawn from the same cohort, even though the file itself is authentic.
    cohort_overlap = training.get("train_datasets") == 199
    development_eligible = not cohort_overlap
    result = {
        "artifact": manifest["artifact_name"],
        "checkpoint_sha256": weight_hash,
        "manifest_sha256": manifest_hash,
        "manifest_weight_sha256": expected_manifest_weight,
        "expected_public_weight_sha256": EXPECTED_WEIGHT_SHA256,
        "weight_hash_matches_manifest": weight_hash == expected_manifest_weight,
        "weight_hash_matches_contract": weight_hash == EXPECTED_WEIGHT_SHA256,
        "architecture_config": config,
        "training": {
            "method": training.get("method"),
            "base_seed": training.get("base_seed"),
            "effective_seed": training.get("effective_seed"),
            "train_datasets": training.get("train_datasets"),
            "validation_datasets": training.get("validation_datasets"),
            "splits_file_sha256": training.get("splits_file_sha256"),
        },
        "offline_load": {
            "ok": load_ok,
            "state_dict_keys": state_dict_keys,
            "error": load_error,
        },
        "development_label_overlap_risk": cohort_overlap,
        "development_shadow_eligible": development_eligible,
        "decision": (
            "HOLD_ARTIFACT_TRAINED_ON_EVALUATION_COHORT"
            if cohort_overlap
            else "PROVENANCE_ELIGIBLE_FOR_BOUNDED_SHADOW"
        ),
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
