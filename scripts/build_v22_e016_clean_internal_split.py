"""Build and validate the internal split for clean E016 checkpoint training."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def rank(sample_id: str) -> str:
    return hashlib.sha256(f"v22-e016-internal-split:{sample_id}".encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/v22_unet_detection_development_46.json"))
    parser.add_argument("--train-dir", type=Path, default=Path("train"))
    parser.add_argument("--output", type=Path, default=Path("v22_e016_clean_internal_split.json"))
    parser.add_argument("--validation-fraction", type=float, default=0.20)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    excluded = {case["sample_id"] for case in fixture["cases"]}
    available = {
        path.name.removesuffix(".zarr")
        for path in args.train_dir.glob("*.zarr")
        if path.is_dir()
    }
    clean = sorted(available - excluded)
    if len(available) != 199 or len(excluded) != 27 or len(clean) != 172:
        raise RuntimeError(
            f"Expected 199 total, 27 excluded, 172 clean; got "
            f"{len(available)}, {len(excluded)}, {len(clean)}"
        )

    ordered = sorted(clean, key=rank)
    validation_count = round(len(ordered) * args.validation_fraction)
    validation = sorted(ordered[:validation_count])
    training = sorted(ordered[validation_count:])
    if set(training) & set(validation) or set(training) & excluded or set(validation) & excluded:
        raise RuntimeError("Internal split overlap detected")

    family_counts = {
        "training": {family: sum(s.startswith(family + "_") for s in training) for family in ("44b6", "6bba")},
        "validation": {family: sum(s.startswith(family + "_") for s in validation) for family in ("44b6", "6bba")},
        "development_excluded": {family: sum(s.startswith(family + "_") for s in excluded) for family in ("44b6", "6bba")},
    }
    if any(count == 0 for count in family_counts["validation"].values()):
        raise RuntimeError(f"Internal validation lost a family: {family_counts}")

    result = {
        "name": "v22_e016_clean_internal_split_v1",
        "status": "validated_no_development_overlap",
        "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        "total_samples": len(available),
        "development_excluded_samples": len(excluded),
        "clean_pool_samples": len(clean),
        "fit_samples": len(training),
        "internal_validation_samples": len(validation),
        "development_excluded_sample_ids": sorted(excluded),
        "fit_sample_ids": training,
        "internal_validation_sample_ids": validation,
        "family_counts": family_counts,
        "seed_rule": "sha256(v22-e016-internal-split:<sample_id>)",
        "development_overlap": False,
        "hidden_test_overlap": False,
        "graph_mutation": False,
        "assignment": False,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
