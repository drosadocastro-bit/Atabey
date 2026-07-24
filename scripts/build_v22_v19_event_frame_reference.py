from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


def _read_completed(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    rows.sort(key=lambda row: str(row["case_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count frozen V19 detections in V22 event frames."
    )
    parser.add_argument("--train-dir", type=Path, default=project_root / "train")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=project_root
        / "tests"
        / "fixtures"
        / "v22_unet_detection_development_46.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "v22_v19_event_frame_reference.csv",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    cases_by_sample: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case in fixture["cases"]:
        cases_by_sample[str(case["sample_id"])].append(case)

    rows: list[dict[str, object]] = (
        list(_read_completed(args.output)) if args.resume else []
    )
    completed = {str(row["case_id"]) for row in rows}

    for sample_index, sample_id in enumerate(sorted(cases_by_sample), start=1):
        pending = [
            case
            for case in cases_by_sample[sample_id]
            if str(case["case_id"]) not in completed
        ]
        if not pending:
            continue
        max_timepoints = max(int(case["t"]) for case in pending) + 2
        print(
            f"[{sample_index}/{len(cases_by_sample)}] {sample_id} "
            f"through {max_timepoints} timepoints",
            flush=True,
        )
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr",
            max_timepoints=max_timepoints,
        )
        frame_counts = Counter(detection.t for detection in graph.detections)
        for case in pending:
            parent_t = int(case["t"])
            rows.append(
                {
                    "case_id": case["case_id"],
                    "sample_id": sample_id,
                    "t": parent_t,
                    "source_detector": detector,
                    "source_link_strategy": link_strategy,
                    "v19_parent_frame_count": frame_counts[parent_t],
                    "v19_daughter_frame_count": frame_counts[parent_t + 1],
                }
            )
            completed.add(str(case["case_id"]))
        _write_rows(args.output, rows)

    print(f"Wrote {len(rows)} rows to {args.output}", flush=True)


if __name__ == "__main__":
    main()
