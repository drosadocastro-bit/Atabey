"""Build the leakage-free E016 secondary-training manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", type=Path, default=Path("v22_unet_official_action_development_46.csv"))
    parser.add_argument("--train-dir", type=Path, default=Path("train"))
    parser.add_argument("--output", type=Path, default=Path("v22_e016_clean_checkpoint_manifest.json"))
    args = parser.parse_args()

    import pandas as pd

    actions = pd.read_csv(args.actions)
    excluded = sorted(actions["sample_id"].dropna().unique().tolist())
    available = {
        path.name.removesuffix(".zarr")
        for path in args.train_dir.glob("*.zarr")
        if path.is_dir()
    }
    missing = sorted(set(excluded) - available)
    if missing:
        raise RuntimeError(f"Development samples missing from train directory: {missing}")
    if len(excluded) != 27:
        raise RuntimeError(f"Expected 27 development samples, found {len(excluded)}")

    train_samples = sorted(available - set(excluded))
    if len(available) != 199 or len(train_samples) != 172:
        raise RuntimeError(
            f"Expected 199 total and 172 clean-training samples; found "
            f"{len(available)} total and {len(train_samples)} clean"
        )

    result = {
        "name": "v22_e016_clean_secondary_checkpoint_v1",
        "status": "preregistered_training_manifest",
        "source_action_availability": str(args.actions),
        "source_action_availability_sha256": sha256(args.actions),
        "total_competition_samples": len(available),
        "clean_training_samples": len(train_samples),
        "held_out_development_samples": len(excluded),
        "held_out_development_events": int(len(actions)),
        "held_out_development_sample_ids": excluded,
        "training_sample_ids": train_samples,
        "training": {
            "base_seed": 314159,
            "effective_seed": 314159,
            "deterministic": True,
            "model_method": "unet_transformer_clean172_seed314159_v1",
            "selection_rule": "select only from non-development training evidence",
            "development_labels_used_for_fit_or_selection": False,
            "hidden_test_labels_used_for_fit_or_selection": False,
        },
        "evaluation": {
            "official_development_events": 46,
            "official_radius_um": 7.0,
            "graph_mutation": False,
            "assignment": False,
            "full_199_authorized": False,
        },
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
