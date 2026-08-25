from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from atabey.detection.adaptive import choose_settings_for_sample
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS

try:
    from run_hybrid_train_evaluation import _should_use_cfar_route
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_hybrid_train_evaluation import _should_use_cfar_route


def _route_sample(sample_path: Path) -> dict[str, object]:
    profile, settings = choose_settings_for_sample(sample_path)
    if _should_use_cfar_route(
        profile=profile,
        adaptive_detector=settings.detector,
        cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
    ):
        detector = "cfar_sidelobe"
        link_strategy = "bipartite"
    else:
        detector = settings.detector
        link_strategy = (
            "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
        )

    sample_id = sample_path.stem
    return {
        "sample_id": sample_id,
        "family": sample_id.split("_", 1)[0],
        "detector": detector,
        "link_strategy": link_strategy,
        "route": f"{detector}/{link_strategy}",
        "sampled_timepoints": list(profile.sampled_timepoints),
        "median_largest_component_voxels": profile.median_largest_component_voxels,
        "median_foreground_fraction": profile.median_foreground_fraction,
    }


def _summarize(records: list[dict[str, object]]) -> dict[str, object]:
    route_counts = Counter(str(record["route"]) for record in records)
    family_route_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        family_route_counts[str(record["family"])][str(record["route"])] += 1

    total = len(records)
    local_route = "local_maxima/motion_mutual"
    local_records = [record for record in records if record["route"] == local_route]
    return {
        "status": "read_only_route_census",
        "cohort_samples": total,
        "cfar_route_policy": DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        "cfar_link_strategy": "bipartite",
        "profile_timepoints_per_sample": 5,
        "route_counts": dict(sorted(route_counts.items())),
        "route_percentages": {
            route: 100.0 * count / total for route, count in sorted(route_counts.items())
        },
        "family_route_counts": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(family_route_counts.items())
        },
        "local_maxima": {
            "route": local_route,
            "samples": len(local_records),
            "percentage": 100.0 * len(local_records) / total,
            "sample_ids": [str(record["sample_id"]) for record in local_records],
            "generalization_status": "unproven",
            "reporting_status": "separate_zero_shot_transfer_only",
        },
        "records": sorted(records, key=lambda record: str(record["sample_id"])),
    }


def _saved_route_parity(
    records: list[dict[str, object]], parity_dir: Path
) -> dict[str, object]:
    expected = {str(record["sample_id"]): str(record["route"]) for record in records}
    mismatches: list[dict[str, str]] = []
    summaries = sorted(parity_dir.glob("*.summary.json"))
    for path in summaries:
        saved = json.loads(path.read_text(encoding="utf-8"))
        sample_id = str(saved["sample_id"])
        actual_route = str(saved["route"])
        census_route = expected.get(sample_id)
        if census_route != actual_route:
            mismatches.append(
                {
                    "sample_id": sample_id,
                    "census_route": str(census_route),
                    "saved_actual_route": actual_route,
                }
            )
    return {
        "compared_samples": len(summaries),
        "mismatches": mismatches,
        "passed": bool(summaries) and not mismatches,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only census of frozen V19/V22 routes.")
    parser.add_argument("--train-dir", type=Path, default=Path("train"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--parity-dir",
        type=Path,
        default=Path("v22_continuation_reference_audit"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("v22_route_prevalence_199.json"),
    )
    args = parser.parse_args()

    sample_paths = sorted(args.train_dir.glob("*.zarr"))
    if len(sample_paths) != 199:
        raise RuntimeError(f"Expected 199 training samples, found {len(sample_paths)}")

    records: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, record in enumerate(executor.map(_route_sample, sample_paths), start=1):
            records.append(record)
            print(
                f"[{index:03d}/{len(sample_paths)}] {record['sample_id']}: {record['route']}",
                flush=True,
            )

    summary = _summarize(records)
    summary["development_actual_route_parity"] = _saved_route_parity(
        records, args.parity_dir
    )
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
