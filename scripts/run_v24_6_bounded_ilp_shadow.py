from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atabey.tracking.bounded_ilp_shadow import audit_bounded_ilp_window
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections


DEFAULT_SAMPLES = ("6bba_2646afc7", "6bba_3c5691b6")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _minimum_margin(record: dict[str, Any]) -> float:
    margins = [
        float(value)
        for value in (record["forward_margin_um"], record["reverse_margin_um"])
        if value is not None
    ]
    return min(margins, default=float("inf"))


def _select_trigger(records: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    persistent = [
        record
        for record in records
        if int(record["changed_assignment_count"]) > 0 and not record["reconverged"]
    ]
    candidates = persistent or records
    trigger = min(
        candidates,
        key=lambda record: (
            _minimum_margin(record),
            record["source_id"],
            record["target_id"],
        ),
    )
    return ("persistent_commitment" if persistent else "minimum_margin_control"), trigger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay the bounded V24.6 ILP shadow on cached V24.5 coordinates."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "outputs/v24_5_commitment_shadow_local_2",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/v24_6_bounded_ilp_shadow_local_2/summary.json",
    )
    parser.add_argument("--sample-ids", nargs="+", default=list(DEFAULT_SAMPLES))
    parser.add_argument("--baseline-change-penalty-um", type=float, default=2.0)
    parser.add_argument("--minimum-improvement-um", type=float, default=0.5)
    parser.add_argument("--max-variables", type=int, default=512)
    parser.add_argument("--time-limit-seconds", type=float, default=5.0)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for sample_id in dict.fromkeys(args.sample_ids):
        sample_evidence = json.loads(
            (args.input_dir / "samples" / f"{sample_id}.json").read_text(
                encoding="utf-8"
            )
        )
        trigger_kind, trigger = _select_trigger(sample_evidence["shadow"]["records"])
        coordinates = np.load(
            args.input_dir / "coordinates" / f"{sample_id}.npy",
            allow_pickle=False,
        )
        graph = relink_predictor_detections(sample_id, coordinates)
        before = graph_signature(graph)
        common = {
            "trigger_source_id": trigger["source_id"],
            "trigger_target_id": trigger["target_id"],
            "max_variables": args.max_variables,
            "time_limit_seconds": args.time_limit_seconds,
        }
        primary = audit_bounded_ilp_window(
            graph,
            baseline_change_penalty_um=args.baseline_change_penalty_um,
            minimum_improvement_um=args.minimum_improvement_um,
            **common,
        )
        zero_penalty_diagnostic = audit_bounded_ilp_window(
            graph,
            baseline_change_penalty_um=0.0,
            minimum_improvement_um=0.0,
            **common,
        )
        if graph_signature(graph) != before:
            raise RuntimeError("ILP shadow mutated the relinked graph")
        results.append(
            {
                "sample_id": sample_id,
                "trigger_kind": trigger_kind,
                "trigger_record": trigger,
                "primary": asdict(primary),
                "zero_penalty_mechanism_diagnostic": asdict(zero_penalty_diagnostic),
                "graph_mutated": False,
            }
        )

    _atomic_json(
        args.output,
        {
            "status": "v24_6_bounded_ilp_shadow_local_2",
            "assignment_enabled": False,
            "selector_enabled": False,
            "production_graph_mutation": False,
            "primary_contract": {
                "baseline_change_penalty_um": args.baseline_change_penalty_um,
                "minimum_improvement_um": args.minimum_improvement_um,
                "max_variables": args.max_variables,
                "time_limit_seconds": args.time_limit_seconds,
            },
            "diagnostic_contract": {
                "baseline_change_penalty_um": 0.0,
                "minimum_improvement_um": 0.0,
                "interpretation": "Mechanism sensitivity only; not an eligible arm or tuned threshold.",
            },
            "results": results,
        },
    )


if __name__ == "__main__":
    main()