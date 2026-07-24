from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from atabey.evaluation.detection_availability import (
    DetectionPeak,
    audit_division_detection_availability,
)
from atabey.io.geff_reader import read_geff_graph


def _load_public_predict_module(support_repo: Path):
    script_dir = support_repo / "scripts"
    source_dir = support_repo / "src"
    sys.path[:0] = [str(script_dir), str(source_dir)]
    script_path = script_dir / "predict_unet_transformer.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Public inference script not found: {script_path}")
    spec = importlib.util.spec_from_file_location(
        "biohub_public_predict_unet_transformer", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import public inference script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _d4_detection_logits(model, images, torch):
    """Match the public 0.902 notebook's eight-view spatial TTA."""

    _, logits = model.encode(images)
    view_count = 1

    for dims in [(-1,), (-2,), (-2, -1)]:
        _, transformed = model.encode(images.flip(dims))
        for frame_index in range(len(logits)):
            logits[frame_index] += transformed[frame_index].flip(dims)
        view_count += 1

    for quarter_turns in (1, 3):
        rotated_images = torch.rot90(images, quarter_turns, dims=(-2, -1))
        _, transformed = model.encode(rotated_images)
        for frame_index in range(len(logits)):
            logits[frame_index] += torch.rot90(
                transformed[frame_index], -quarter_turns, dims=(-2, -1)
            )
        view_count += 1

    transposed_images = images.transpose(-1, -2)
    _, transformed = model.encode(transposed_images)
    for frame_index in range(len(logits)):
        logits[frame_index] += transformed[frame_index].transpose(-1, -2)
    view_count += 1

    anti_transposed_images = torch.rot90(images, 1, dims=(-2, -1)).transpose(-1, -2)
    _, transformed = model.encode(anti_transposed_images)
    for frame_index in range(len(logits)):
        restored = transformed[frame_index].transpose(-1, -2)
        logits[frame_index] += torch.rot90(restored, -1, dims=(-2, -1))
    view_count += 1

    return [frame_logits / view_count for frame_logits in logits]


def _predict_event_frames(
    *,
    public_module,
    model,
    sample_path: Path,
    parent_t: int,
    downsample: tuple[int, ...],
    threshold: float,
    pool_kernel_um: float,
    device,
) -> list[DetectionPeak]:
    import torch
    import zarr

    dataset = public_module.open_dataset(
        sample_path, normalize=False, load_image=False, downsample=downsample
    )
    q_low = float(dataset.quantiles["0.001"])
    q_high = float(dataset.quantiles["0.999"])
    zarr_array = zarr.open_group(str(dataset.zarr_path), mode="r")["0"]
    target_shape = list(dataset.image_shape[1:])

    def infer_window(start_t: int):
        images = torch.stack(
            [
                public_module._load_frame(
                    zarr_array, t, target_shape, downsample
                )
                for t in (start_t, start_t + 1)
            ]
        )
        images = ((images - q_low) / (q_high - q_low + 1e-6)).clamp(0.0)
        images = images.unsqueeze(0).to(device)
        return _d4_detection_logits(model, images, torch)

    if parent_t == 0:
        daughter_window_logits = infer_window(0)
        role_logits = [daughter_window_logits[0], daughter_window_logits[1]]
    else:
        parent_window_logits = infer_window(parent_t - 1)
        daughter_window_logits = infer_window(parent_t)
        role_logits = [parent_window_logits[1], daughter_window_logits[1]]

    voxel_size = tuple(
        float(spacing) * factor
        for spacing, factor in zip(dataset.scale, downsample, strict=True)
    )
    pool_kernel = public_module.pool_kernel_from_um(
        pool_kernel_um, voxel_size
    )

    peaks: list[DetectionPeak] = []
    for frame_index, t in enumerate((parent_t, parent_t + 1)):
        coordinates = public_module._detect_cells_pooled(
            role_logits[frame_index][0],
            t,
            threshold,
            pool_kernel,
        )
        probabilities = torch.sigmoid(role_logits[frame_index][0, 0])
        for _, z_ds, y_ds, x_ds in coordinates:
            z = int(z_ds) * downsample[0]
            y = int(y_ds) * downsample[1]
            x = int(x_ds) * downsample[2]
            peaks.append(
                DetectionPeak(
                    t=int(t),
                    z_um=float(z * dataset.scale[0]),
                    y_um=float(y * dataset.scale[1]),
                    x_um=float(x * dataset.scale[2]),
                    confidence=float(
                        probabilities[int(z_ds), int(y_ds), int(x_ds)].item()
                    ),
                )
            )
    return peaks


def _node_lookup(ground_truth) -> dict[int, Any]:
    return {node.node_id: node for node in ground_truth.nodes}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targets = [row for row in rows if row["cohort"] == "target"]
    controls = [row for row in rows if row["cohort"] == "positive_control"]
    recovered = [row for row in targets if row["complete_triplet"]]
    preserved = [row for row in controls if row["complete_triplet"]]
    recovered_families = sorted(
        {str(row["sample_id"]).split("_", 1)[0] for row in recovered}
    )
    go = (
        len(recovered) >= 3
        and recovered_families == ["44b6", "6bba"]
        and len(preserved) == len(controls)
    )
    return {
        "decision": "GO_TO_LARGER_SHADOW" if go else "NO_GO_OR_INCONCLUSIVE",
        "target_complete_triplets": len(recovered),
        "target_cases": len(targets),
        "positive_controls_preserved": len(preserved),
        "positive_controls": len(controls),
        "recovered_families": recovered_families,
        "graph_mutation": False,
        "edge_inference_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the public temporal U-Net as a detector-only V22 shadow."
    )
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--support-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/v22_unet_detection_shadow.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("v22_unet_detection_shadow.csv"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("v22_unet_detection_shadow_summary.json"),
    )
    parser.add_argument("--allow-cpu", action="store_true")
    args = parser.parse_args()

    import torch

    if not torch.cuda.is_available() and not args.allow_cpu:
        raise RuntimeError("CUDA GPU required; pass --allow-cpu only for a tiny smoke.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    expected_hash = fixture.get("expected_weight_sha256")
    if expected_hash:
        actual_hash = hashlib.sha256(args.weights.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Checkpoint SHA-256 mismatch: {actual_hash} != {expected_hash}"
            )
    threshold = float(fixture["det_threshold"])
    pool_kernel_um = float(fixture["pool_kernel_um"])
    public_module = _load_public_predict_module(args.support_repo)
    model, window_size, downsample = public_module.load_model(args.weights, device)
    if window_size != 2:
        raise RuntimeError(f"Expected temporal window size 2, found {window_size}")

    grouped_cases: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for case in fixture["cases"]:
        grouped_cases[(case["sample_id"], int(case["t"]))].append(case)

    rows: list[dict[str, Any]] = []
    peak_cache: dict[tuple[str, int], list[DetectionPeak]] = {}
    gt_cache: dict[str, Any] = {}

    for (sample_id, parent_t), cases in grouped_cases.items():
        print(f"[{sample_id}] frames {parent_t}:{parent_t + 1}", flush=True)
        peaks = _predict_event_frames(
            public_module=public_module,
            model=model,
            sample_path=args.train_dir / f"{sample_id}.zarr",
            parent_t=parent_t,
            downsample=downsample,
            threshold=threshold,
            pool_kernel_um=pool_kernel_um,
            device=device,
        )
        peak_cache[(sample_id, parent_t)] = peaks
        ground_truth = gt_cache.setdefault(
            sample_id,
            read_geff_graph(args.train_dir / f"{sample_id}.geff"),
        )
        nodes = _node_lookup(ground_truth)

        for case in cases:
            parent = nodes[int(case["gt_parent_id"])]
            child_1 = nodes[int(case["gt_child_ids"][0])]
            child_2 = nodes[int(case["gt_child_ids"][1])]
            result = audit_division_detection_availability(
                peaks,
                parent_t=parent_t,
                parent_position_um=parent.position_um,
                daughter_positions_um=(
                    child_1.position_um,
                    child_2.position_um,
                ),
                match_radius_um=float(fixture["official_match_radius_um"]),
            )
            rows.append(
                {
                    "case_id": case["case_id"],
                    "sample_id": sample_id,
                    "t": parent_t,
                    "cohort": case["cohort"],
                    "baseline_status": case["baseline_status"],
                    "unet_parent_candidates": result.parent_candidate_count,
                    "unet_daughter_1_candidates": result.daughter_1_candidate_count,
                    "unet_daughter_2_candidates": result.daughter_2_candidate_count,
                    "parent_distance_um": result.parent_distance_um,
                    "daughter_1_distance_um": result.daughter_1_distance_um,
                    "daughter_2_distance_um": result.daughter_2_distance_um,
                    "parent_frame_peak_count": sum(
                        peak.t == parent_t for peak in peaks
                    ),
                    "daughter_frame_peak_count": sum(
                        peak.t == parent_t + 1 for peak in peaks
                    ),
                    "distinct_daughter_pair": result.distinct_daughter_pair,
                    "complete_triplet": result.complete_triplet,
                    "det_threshold": threshold,
                    "pool_kernel_um": pool_kernel_um,
                    "tta": fixture["tta"],
                    "graph_mutated": False,
                    "edges_inferred": False,
                }
            )

    rows.sort(key=lambda row: row["case_id"])
    _write_csv(args.output_csv, rows)
    summary = _summary(rows)
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    print(f"Wrote {args.output_csv} and {args.output_summary}", flush=True)


if __name__ == "__main__":
    main()
