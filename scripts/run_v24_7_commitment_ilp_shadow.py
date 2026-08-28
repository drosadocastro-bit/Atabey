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

from atabey.tracking.commitment_ilp_shadow import audit_commitment_ilp_funnel
from atabey.tracking.commitment_shadow import audit_motion_mutual_commitment
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the combined commitment-to-ILP shadow on cached coordinates."
    )
    parser.add_argument(
        "--coordinate-dir",
        type=Path,
        default=ROOT / "outputs/v24_5_commitment_shadow_local_2/coordinates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/v24_7_commitment_ilp_shadow_local_2/summary.json",
    )
    parser.add_argument("--sample-ids", nargs="+", default=list(DEFAULT_SAMPLES))
    parser.add_argument("--max-counterfactual-edges", type=int, default=64)
    parser.add_argument("--commitment-horizon-frames", type=int, default=2)
    parser.add_argument("--max-ilp-windows", type=int, default=16)
    parser.add_argument("--baseline-change-penalty-um", type=float, default=2.0)
    parser.add_argument("--minimum-improvement-um", type=float, default=0.5)
    parser.add_argument("--max-variables", type=int, default=512)
    parser.add_argument("--time-limit-seconds", type=float, default=5.0)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for sample_id in dict.fromkeys(args.sample_ids):
        coordinates = np.load(
            args.coordinate_dir / f"{sample_id}.npy",
            allow_pickle=False,
        )
        graph = relink_predictor_detections(sample_id, coordinates)
        before = graph_signature(graph)
        commitment = audit_motion_mutual_commitment(
            graph,
            horizon_frames=args.commitment_horizon_frames,
            max_counterfactual_edges=args.max_counterfactual_edges,
        )
        funnel = audit_commitment_ilp_funnel(
            graph,
            commitment,
            baseline_change_penalty_um=args.baseline_change_penalty_um,
            minimum_improvement_um=args.minimum_improvement_um,
            max_ilp_windows=args.max_ilp_windows,
            max_variables=args.max_variables,
            time_limit_seconds=args.time_limit_seconds,
        )
        if graph_signature(graph) != before:
            raise RuntimeError("Combined shadow mutated the relinked graph")
        results.append(
            {
                "sample_id": sample_id,
                "coordinate_count": len(coordinates),
                "commitment": asdict(commitment),
                "funnel": asdict(funnel),
                "graph_mutated": False,
            }
        )

    _atomic_json(
        args.output,
        {
            "status": "v24_7_commitment_ilp_shadow_local_2",
            "assignment_enabled": False,
            "selector_enabled": False,
            "production_graph_mutation": False,
            "contract": {
                "max_counterfactual_edges": args.max_counterfactual_edges,
                "commitment_horizon_frames": args.commitment_horizon_frames,
                "max_ilp_windows": args.max_ilp_windows,
                "baseline_change_penalty_um": args.baseline_change_penalty_um,
                "minimum_improvement_um": args.minimum_improvement_um,
                "max_variables": args.max_variables,
                "time_limit_seconds": args.time_limit_seconds,
            },
            "interpretation": {
                "commitment": "Intervention-based stability trigger, not an error label.",
                "primary_ilp": "Contained assignment hypothesis, not an authorized rewrite.",
                "zero_penalty_ilp": "Mechanism diagnostic only, not an eligible arm.",
            },
            "results": results,
        },
    )


if __name__ == "__main__":
    main()