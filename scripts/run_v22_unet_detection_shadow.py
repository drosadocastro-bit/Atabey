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

    with torch.inference_mode():
        _, logits = model.encode(images)
        view_count = 1

        for dims in [(-1,), (-2,), (-2, -1)]:
            _, transformed = model.encode(images.flip(dims))
            for frame_index in range(len(logits)):
                logits[frame_index] += transformed[frame_index].flip(dims)
            del transformed
            view_count += 1

        for quarter_turns in (1, 3):
            rotated_images = torch.rot90(images, quarter_turns, dims=(-2, -1))
            _, transformed = model.encode(rotated_images)
            for frame_index in range(len(logits)):
                logits[frame_index] += torch.rot90(
                    transformed[frame_index], -quarter_turns, dims=(-2, -1)
                )
            del rotated_images, transformed
            view_count += 1

        transposed_images = images.transpose(-1, -2)
        _, transformed = model.encode(transposed_images)
        for frame_index in range(len(logits)):
            logits[frame_index] += transformed[frame_index].transpose(-1, -2)
        del transposed_images, transformed
        view_count += 1

        anti_transposed_images = torch.rot90(images, 1, dims=(-2, -1)).transpose(
            -1, -2
        )
        _, transformed = model.encode(anti_transposed_images)
        for frame_index in range(len(logits)):
            restored = transformed[frame_index].transpose(-1, -2)
            logits[frame_index] += torch.rot90(restored, -1, dims=(-2, -1))
        del anti_transposed_images, transformed
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

    def infer_window_frame(start_t: int, frame_index: int):
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
        logits = _d4_detection_logits(model, images, torch)
        selected = logits[frame_index]
        del images, logits
        return selected

    voxel_size = tuple(
        float(spacing) * factor
        for spacing, factor in zip(dataset.scale, downsample, strict=True)
    )
    pool_kernel = public_module.pool_kernel_from_um(
        pool_kernel_um, voxel_size
    )

    def extract_peaks(frame_logits, t: int) -> list[DetectionPeak]:
        coordinates = public_module._detect_cells_pooled(
            frame_logits[0],
            t,
            threshold,
            pool_kernel,
        )
        probabilities = torch.sigmoid(frame_logits[0, 0])
        frame_peaks: list[DetectionPeak] = []
        for _, z_ds, y_ds, x_ds in coordinates:
            z = int(z_ds) * downsample[0]
            y = int(y_ds) * downsample[1]
            x = int(x_ds) * downsample[2]
            frame_peaks.append(
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
        return frame_peaks

    parent_start = 0 if parent_t == 0 else parent_t - 1
    parent_index = 0 if parent_t == 0 else 1
    parent_logits = infer_window_frame(parent_start, parent_index)
    peaks = extract_peaks(parent_logits, parent_t)
    del parent_logits
    torch.cuda.empty_cache()

    daughter_logits = infer_window_frame(parent_t, 1)
    peaks.extend(extract_peaks(daughter_logits, parent_t + 1))
    del daughter_logits
    torch.cuda.empty_cache()
    return peaks


def _node_lookup(ground_truth) -> dict[int, Any]:
    return {node.node_id: node for node in ground_truth.nodes}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _peak_rows(
    peaks_by_location: dict[tuple[str, int, float, float, float], float | None],
    *,
    threshold: float,
    pool_kernel_um: float,
    tta: str,
) -> list[dict[str, Any]]:
    """Create deterministic, deduplicated peak records for downstream shadows."""

    grouped: dict[tuple[str, int], list[tuple[float, float, float, float | None]]] = (
        defaultdict(list)
    )
    for (sample_id, t, z_um, y_um, x_um), confidence in peaks_by_location.items():
        grouped[(sample_id, t)].append((z_um, y_um, x_um, confidence))

    rows: list[dict[str, Any]] = []
    for (sample_id, t), frame_peaks in sorted(grouped.items()):
        frame_peaks.sort(
            key=lambda peak: (
                peak[0],
                peak[1],
                peak[2],
                -(peak[3] if peak[3] is not None else -1.0),
            )
        )
        for index, (z_um, y_um, x_um, confidence) in enumerate(frame_peaks):
            rows.append(
                {
                    "peak_id": f"unet:{sample_id}:t{t}:p{index:05d}",
                    "sample_id": sample_id,
                    "t": t,
                    "z_um": z_um,
                    "y_um": y_um,
                    "x_um": x_um,
                    "confidence": confidence,
                    "det_threshold": threshold,
                    "pool_kernel_um": pool_kernel_um,
                    "tta": tta,
                }
            )
    return rows


def _is_true(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def _summary(
    rows: list[dict[str, Any]],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    expected_cases = len(fixture["cases"])
    if any(row["cohort"] == "baseline_unavailable" for row in rows):
        unavailable = [
            row for row in rows if row["cohort"] == "baseline_unavailable"
        ]
        nonofficial = [
            row
            for row in rows
            if row["cohort"] == "baseline_nonofficial_action"
        ]
        controls = [
            row for row in rows if row["cohort"] == "positive_control"
        ]
        recovered = [
            row for row in unavailable if _is_true(row["complete_triplet"])
        ]
        preserved = [
            row for row in controls if _is_true(row["complete_triplet"])
        ]
        recovered_families = sorted(
            {str(row["sample_id"]).split("_", 1)[0] for row in recovered}
        )
        contract = fixture["decision_contract"]
        availability_pass = len(recovered) >= int(
            contract["baseline_unavailable_min_complete"]
        )
        control_pass = len(preserved) >= int(
            contract["positive_control_min_preserved"]
        )
        family_pass = recovered_families == sorted(
            contract["required_recovered_families"]
        )
        complete = len(rows) == expected_cases
        go = complete and availability_pass and control_pass and family_pass
        return {
            "decision": (
                "GO_PENDING_FRAME_INFLATION_AUDIT"
                if go
                else "IN_PROGRESS"
                if not complete
                else "NO_GO"
            ),
            "completed_cases": len(rows),
            "expected_cases": expected_cases,
            "baseline_unavailable_complete_triplets": len(recovered),
            "baseline_unavailable_cases": len(unavailable),
            "baseline_nonofficial_complete_triplets": sum(
                _is_true(row["complete_triplet"]) for row in nonofficial
            ),
            "baseline_nonofficial_cases": len(nonofficial),
            "positive_controls_preserved": len(preserved),
            "positive_controls": len(controls),
            "recovered_families": recovered_families,
            "availability_gate_pass": availability_pass,
            "control_gate_pass": control_pass,
            "family_gate_pass": family_pass,
            "graph_mutation": False,
            "edge_inference_used": False,
        }

    targets = [row for row in rows if row["cohort"] == "target"]
    controls = [row for row in rows if row["cohort"] == "positive_control"]
    recovered = [row for row in targets if _is_true(row["complete_triplet"])]
    preserved = [row for row in controls if _is_true(row["complete_triplet"])]
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
    parser.add_argument(
        "--output-peaks",
        type=Path,
        default=None,
        help=(
            "Optional deterministic CSV of all U-Net peaks in the evaluated "
            "parent/daughter frames for downstream read-only shadows."
        ),
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
    peaks_by_location: dict[
        tuple[str, int, float, float, float],
        float | None,
    ] = {}
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
        for peak in peaks:
            location = (
                sample_id,
                int(peak.t),
                float(peak.z_um),
                float(peak.y_um),
                float(peak.x_um),
            )
            previous_confidence = peaks_by_location.get(location)
            if (
                location not in peaks_by_location
                or previous_confidence is None
                or (
                    peak.confidence is not None
                    and float(peak.confidence) > previous_confidence
                )
            ):
                peaks_by_location[location] = (
                    float(peak.confidence)
                    if peak.confidence is not None
                    else None
                )
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
    summary = _summary(rows, fixture)
    if args.output_peaks is not None:
        peak_rows = _peak_rows(
            peaks_by_location,
            threshold=threshold,
            pool_kernel_um=pool_kernel_um,
            tta=str(fixture["tta"]),
        )
        _write_csv(args.output_peaks, peak_rows)
        summary["exported_peak_count"] = len(peak_rows)
        summary["exported_peak_frames"] = len(
            {(row["sample_id"], row["t"]) for row in peak_rows}
        )
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    outputs = [str(args.output_csv), str(args.output_summary)]
    if args.output_peaks is not None:
        outputs.append(str(args.output_peaks))
    print(f"Wrote {', '.join(outputs)}", flush=True)


if __name__ == "__main__":
    main()
