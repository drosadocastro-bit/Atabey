"""Standalone CNN-advisor evaluation (Cellpose + StarDist) on at-risk samples.

This script is intentionally isolated from production submission paths:
- Does not import or modify run.py / kernel defaults.
- Does not wire into run_hybrid_submission.py.
- Evaluates CNN detectors as standalone advisors against current CFAR detection.

Workflow discipline mirrors Atabey experiments:
1) Bounded data prep from at-risk cohort.
2) Zero-shot baselines (Cellpose / StarDist).
3) Bounded smoke fine-tune.
4) Held-out comparison: Cellpose vs StarDist vs CFAR.

Important caveat:
GEFF labels are sparse centroids, not dense segmentation masks. This script builds
pseudo-instance masks by rasterizing centroid disks on 2D max projections. Metrics
are therefore approximate advisor-screening metrics (not official competition score).
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
import zarr

from atabey.detection.baseline import robust_normalize, threshold_local_maxima_cfar_sidelobe
from atabey.experiments.cnn_advisor import (
    DetectionMetrics,
    DistanceMatchMetrics,
    FrameKey,
    detections_to_instance_mask,
    distance_match_metrics,
    draw_disk_instance_mask,
    instance_centroids_yx,
    instance_iou_metrics,
    load_at_risk_sample_ids,
    select_timepoints,
)
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as HFD
from atabey.io.geff_reader import GroundTruthNode, read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint


@dataclass(frozen=True)
class FrameDatum:
    key: FrameKey
    image_2d: np.ndarray
    gt_mask_2d: np.ndarray
    gt_centers_yx: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class MethodAggregate:
    method: str
    frames: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    mean_predicted_instances_per_frame: float
    mean_ground_truth_instances_per_frame: float
    mean_runtime_seconds_per_frame: float
    mean_best_iou_per_gt: float
    mean_match_iou: float
    mean_best_distance_um_per_gt: float
    mean_match_distance_um: float
    distance_threshold_um: float


@dataclass(frozen=True)
class FrameDiagnostic:
    sample_id: str
    t: int
    gt_instances: int
    pred_instances: int
    gt_points: int
    pred_points: int
    iou_tp: int
    iou_fp: int
    iou_fn: int
    iou_precision: float
    iou_recall: float
    iou_f1: float
    iou_threshold: float
    iou_matched_values: tuple[float, ...]
    iou_best_per_gt: tuple[float, ...]
    distance_tp: int
    distance_fp: int
    distance_fn: int
    distance_precision: float
    distance_recall: float
    distance_f1: float
    distance_threshold_um: float
    distance_matched_um: tuple[float, ...]
    distance_best_um_per_gt: tuple[float, ...]
    runtime_seconds: float


@dataclass(frozen=True)
class SplitSummary:
    train_samples: int
    val_samples: int
    test_samples: int
    train_frames: int
    val_frames: int
    test_frames: int


def _split_sample_ids(sample_ids: list[str], *, seed: int) -> tuple[list[str], list[str], list[str]]:
    rng = random.Random(seed)
    ordered = sample_ids[:]
    rng.shuffle(ordered)
    total = len(ordered)
    if total == 1:
        return [], [], [ordered[0]]
    if total == 2:
        return [ordered[0]], [], [ordered[1]]
    train_n = max(1, int(round(total * 0.6))) if total >= 3 else max(1, total - 2)
    val_n = max(1, int(round(total * 0.2))) if total >= 5 else 1
    if train_n + val_n >= total:
        val_n = max(1, total - train_n - 1)
    test_n = total - train_n - val_n
    if test_n <= 0:
        test_n = 1
        if train_n > 1:
            train_n -= 1
        else:
            val_n = max(1, val_n - 1)
    train_ids = sorted(ordered[:train_n])
    val_ids = sorted(ordered[train_n : train_n + val_n])
    test_ids = sorted(ordered[train_n + val_n :])
    return train_ids, val_ids, test_ids


def _gt_nodes_by_time(nodes: list[GroundTruthNode]) -> dict[int, list[GroundTruthNode]]:
    by_t: dict[int, list[GroundTruthNode]] = {}
    for node in nodes:
        by_t.setdefault(int(node.t), []).append(node)
    return by_t


def _mip_image(volume_zyx: np.ndarray) -> np.ndarray:
    normalized = robust_normalize(volume_zyx, upper=99.9)
    return np.max(normalized, axis=0).astype(np.float32, copy=False)


def _frame_from_sample(
    sample_path: Path,
    *,
    sample_id: str,
    t: int,
    nodes_by_t: dict[int, list[GroundTruthNode]],
    gt_radius_px: int,
) -> FrameDatum:
    array = open_competition_array(sample_path)
    volume = read_timepoint(array, int(t))
    image_2d = _mip_image(volume)
    gt_nodes = nodes_by_t.get(int(t), [])
    centers = [(int(round(float(node.y))), int(round(float(node.x)))) for node in gt_nodes]
    gt_mask = draw_disk_instance_mask(image_2d.shape, centers, radius_px=gt_radius_px)
    return FrameDatum(
        key=FrameKey(sample_id=sample_id, t=int(t)),
        image_2d=image_2d,
        gt_mask_2d=gt_mask,
        gt_centers_yx=tuple((float(node.y), float(node.x)) for node in gt_nodes),
    )


def _collect_frames(
    *,
    train_dir: Path,
    sample_ids: list[str],
    max_timepoints: int,
    gt_radius_px: int,
) -> list[FrameDatum]:
    frames: list[FrameDatum] = []
    for sample_id in sample_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        geff_path = train_dir / f"{sample_id}.geff"
        if not sample_path.exists() or not geff_path.exists():
            continue
        gt = read_geff_graph(geff_path)
        nodes_by_t = _gt_nodes_by_time(gt.nodes)
        array = open_competition_array(sample_path)
        timepoints = select_timepoints(int(array.shape[0]), max_timepoints)
        for t in timepoints:
            frames.append(
                _frame_from_sample(
                    sample_path,
                    sample_id=sample_id,
                    t=int(t),
                    nodes_by_t=nodes_by_t,
                    gt_radius_px=gt_radius_px,
                )
            )
    return frames


def _aggregate_method_metrics(
    method: str,
    metrics: list[DetectionMetrics],
    distance_metrics: list[DistanceMatchMetrics],
    runtimes: list[float],
) -> MethodAggregate:
    tp = sum(m.tp for m in metrics)
    fp = sum(m.fp for m in metrics)
    fn = sum(m.fn for m in metrics)
    precision = float(tp) / float(tp + fp) if (tp + fp) > 0 else 0.0
    recall = float(tp) / float(tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    mean_pred = float(np.mean([m.predicted_instances for m in metrics])) if metrics else 0.0
    mean_gt = float(np.mean([m.ground_truth_instances for m in metrics])) if metrics else 0.0
    mean_runtime = float(np.mean(runtimes)) if runtimes else 0.0
    best_ious: list[float] = []
    matched_ious: list[float] = []
    for metric in metrics:
        best_ious.extend(float(v) for v in metric.best_iou_per_gt)
        matched_ious.extend(float(v) for v in metric.matched_iou_values)

    best_distances: list[float] = []
    matched_distances: list[float] = []
    distance_threshold_um = 0.0
    for distance_metric in distance_metrics:
        distance_threshold_um = float(distance_metric.distance_threshold_um)
        best_distances.extend(
            float(v) for v in distance_metric.best_distance_um_per_gt if np.isfinite(float(v))
        )
        matched_distances.extend(float(v) for v in distance_metric.matched_distance_um)

    mean_best_iou = float(np.mean(best_ious)) if best_ious else 0.0
    mean_match_iou = float(np.mean(matched_ious)) if matched_ious else 0.0
    mean_best_distance = float(np.mean(best_distances)) if best_distances else 0.0
    mean_match_distance = float(np.mean(matched_distances)) if matched_distances else 0.0
    return MethodAggregate(
        method=method,
        frames=len(metrics),
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_predicted_instances_per_frame=mean_pred,
        mean_ground_truth_instances_per_frame=mean_gt,
        mean_runtime_seconds_per_frame=mean_runtime,
        mean_best_iou_per_gt=mean_best_iou,
        mean_match_iou=mean_match_iou,
        mean_best_distance_um_per_gt=mean_best_distance,
        mean_match_distance_um=mean_match_distance,
        distance_threshold_um=distance_threshold_um,
    )


def _build_frame_diagnostic(
    frame: FrameDatum,
    iou_metric: DetectionMetrics,
    distance_metric: DistanceMatchMetrics,
    runtime_seconds: float,
) -> FrameDiagnostic:
    return FrameDiagnostic(
        sample_id=frame.key.sample_id,
        t=int(frame.key.t),
        gt_instances=int(iou_metric.ground_truth_instances),
        pred_instances=int(iou_metric.predicted_instances),
        gt_points=int(distance_metric.ground_truth_points),
        pred_points=int(distance_metric.predicted_points),
        iou_tp=int(iou_metric.tp),
        iou_fp=int(iou_metric.fp),
        iou_fn=int(iou_metric.fn),
        iou_precision=float(iou_metric.precision),
        iou_recall=float(iou_metric.recall),
        iou_f1=float(iou_metric.f1),
        iou_threshold=float(iou_metric.iou_threshold),
        iou_matched_values=tuple(float(v) for v in iou_metric.matched_iou_values),
        iou_best_per_gt=tuple(float(v) for v in iou_metric.best_iou_per_gt),
        distance_tp=int(distance_metric.tp),
        distance_fp=int(distance_metric.fp),
        distance_fn=int(distance_metric.fn),
        distance_precision=float(distance_metric.precision),
        distance_recall=float(distance_metric.recall),
        distance_f1=float(distance_metric.f1),
        distance_threshold_um=float(distance_metric.distance_threshold_um),
        distance_matched_um=tuple(float(v) for v in distance_metric.matched_distance_um),
        distance_best_um_per_gt=tuple(float(v) for v in distance_metric.best_distance_um_per_gt),
        runtime_seconds=float(runtime_seconds),
    )


def _distance_metric_for_frame(
    frame: FrameDatum,
    pred_mask: np.ndarray,
    *,
    distance_threshold_um: float,
    pixel_size_y_um: float,
    pixel_size_x_um: float,
) -> DistanceMatchMetrics:
    pred_points = instance_centroids_yx(pred_mask)
    return distance_match_metrics(
        list(frame.gt_centers_yx),
        pred_points,
        distance_threshold_um=float(distance_threshold_um),
        pixel_size_y_um=float(pixel_size_y_um),
        pixel_size_x_um=float(pixel_size_x_um),
    )


def _eval_cfar(
    *,
    train_dir: Path,
    frames: list[FrameDatum],
    gt_radius_px: int,
    iou_threshold: float,
    distance_threshold_um: float,
    pixel_size_y_um: float,
    pixel_size_x_um: float,
) -> tuple[MethodAggregate, list[FrameDiagnostic]]:
    metrics: list[DetectionMetrics] = []
    distance_metrics: list[DistanceMatchMetrics] = []
    runtimes: list[float] = []
    diagnostics: list[FrameDiagnostic] = []
    array_cache: dict[str, object] = {}
    for frame in frames:
        sample_id = frame.key.sample_id
        t = int(frame.key.t)
        if sample_id not in array_cache:
            array_cache[sample_id] = open_competition_array(train_dir / f"{sample_id}.zarr")
        volume = read_timepoint(array_cache[sample_id], t)
        start = perf_counter()
        detections = threshold_local_maxima_cfar_sidelobe(
            sample_id=sample_id,
            t=t,
            volume=volume,
            threshold=HFD.cfar_threshold,
            min_distance_voxels=(1, 5, 5),
            max_detections=HFD.max_detections_per_timepoint,
            cfar_training_radius_voxels=HFD.cfar_training_radius_voxels,
            cfar_guard_radius_voxels=HFD.cfar_guard_radius_voxels,
            cfar_threshold_mode=HFD.cfar_threshold_mode,
            cfar_k_sigma=HFD.cfar_k_sigma,
            cfar_pfa=HFD.cfar_pfa,
            sidelobe_mode=HFD.sidelobe_mode,
            sidelobe_radius_voxels=HFD.sidelobe_radius_voxels,
            sidelobe_axial_z_radius_voxels=HFD.sidelobe_axial_z_radius_voxels,
            sidelobe_axial_xy_tolerance_voxels=HFD.sidelobe_axial_xy_tolerance_voxels,
            sidelobe_floor_ratio=HFD.sidelobe_floor_ratio,
        )
        pred_mask = detections_to_instance_mask(
            frame.gt_mask_2d.shape,
            [(float(det.y), float(det.x)) for det in detections],
            radius_px=gt_radius_px,
        )
        runtime_seconds = perf_counter() - start
        iou_metric = instance_iou_metrics(frame.gt_mask_2d, pred_mask, iou_threshold=iou_threshold)
        distance_metric = _distance_metric_for_frame(
            frame,
            pred_mask,
            distance_threshold_um=float(distance_threshold_um),
            pixel_size_y_um=float(pixel_size_y_um),
            pixel_size_x_um=float(pixel_size_x_um),
        )
        runtimes.append(runtime_seconds)
        metrics.append(iou_metric)
        distance_metrics.append(distance_metric)
        diagnostics.append(_build_frame_diagnostic(frame, iou_metric, distance_metric, runtime_seconds))
    return _aggregate_method_metrics("cfar_current", metrics, distance_metrics, runtimes), diagnostics


def _predict_cellpose_mask(model: object, image_2d: np.ndarray, *, diameter: float | None) -> np.ndarray:
    outputs = model.eval(image_2d, channels=[0, 0], diameter=diameter, normalize=True)
    if isinstance(outputs, tuple):
        return np.asarray(outputs[0], dtype=np.int32)
    return np.asarray(outputs, dtype=np.int32)


def _eval_cellpose(
    model: object,
    *,
    frames: list[FrameDatum],
    iou_threshold: float,
    method_name: str,
    diameter: float | None,
    distance_threshold_um: float,
    pixel_size_y_um: float,
    pixel_size_x_um: float,
) -> tuple[MethodAggregate, list[FrameDiagnostic]]:
    metrics: list[DetectionMetrics] = []
    distance_metrics: list[DistanceMatchMetrics] = []
    runtimes: list[float] = []
    diagnostics: list[FrameDiagnostic] = []
    for frame in frames:
        start = perf_counter()
        pred_mask = _predict_cellpose_mask(model, frame.image_2d, diameter=diameter)
        runtime_seconds = perf_counter() - start
        iou_metric = instance_iou_metrics(frame.gt_mask_2d, pred_mask, iou_threshold=iou_threshold)
        distance_metric = _distance_metric_for_frame(
            frame,
            pred_mask,
            distance_threshold_um=float(distance_threshold_um),
            pixel_size_y_um=float(pixel_size_y_um),
            pixel_size_x_um=float(pixel_size_x_um),
        )
        runtimes.append(runtime_seconds)
        metrics.append(iou_metric)
        distance_metrics.append(distance_metric)
        diagnostics.append(_build_frame_diagnostic(frame, iou_metric, distance_metric, runtime_seconds))
    return _aggregate_method_metrics(method_name, metrics, distance_metrics, runtimes), diagnostics


def _stardist_normalize(image_2d: np.ndarray) -> np.ndarray:
    from csbdeep.utils import normalize

    return normalize(image_2d.astype(np.float32), 1, 99.8, axis=None)


def _predict_stardist_mask(model: object, image_2d: np.ndarray) -> np.ndarray:
    labels, _details = model.predict_instances(_stardist_normalize(image_2d))
    return np.asarray(labels, dtype=np.int32)


def _eval_stardist(
    model: object,
    *,
    frames: list[FrameDatum],
    iou_threshold: float,
    method_name: str,
    distance_threshold_um: float,
    pixel_size_y_um: float,
    pixel_size_x_um: float,
) -> tuple[MethodAggregate, list[FrameDiagnostic]]:
    metrics: list[DetectionMetrics] = []
    distance_metrics: list[DistanceMatchMetrics] = []
    runtimes: list[float] = []
    diagnostics: list[FrameDiagnostic] = []
    for frame in frames:
        start = perf_counter()
        pred_mask = _predict_stardist_mask(model, frame.image_2d)
        runtime_seconds = perf_counter() - start
        iou_metric = instance_iou_metrics(frame.gt_mask_2d, pred_mask, iou_threshold=iou_threshold)
        distance_metric = _distance_metric_for_frame(
            frame,
            pred_mask,
            distance_threshold_um=float(distance_threshold_um),
            pixel_size_y_um=float(pixel_size_y_um),
            pixel_size_x_um=float(pixel_size_x_um),
        )
        runtimes.append(runtime_seconds)
        metrics.append(iou_metric)
        distance_metrics.append(distance_metric)
        diagnostics.append(_build_frame_diagnostic(frame, iou_metric, distance_metric, runtime_seconds))
    return _aggregate_method_metrics(method_name, metrics, distance_metrics, runtimes), diagnostics


def _read_pixel_spacing_um(train_dir: Path, sample_id: str) -> tuple[float, float, float]:
    sample_path = train_dir / f"{sample_id}.zarr"
    root = zarr.open_group(str(sample_path), mode="r")
    multiscales = root.attrs.get("multiscales", None)
    if isinstance(multiscales, list) and multiscales:
        datasets = multiscales[0].get("datasets", []) if isinstance(multiscales[0], dict) else []
        if datasets and isinstance(datasets[0], dict):
            transforms = datasets[0].get("coordinateTransformations", [])
            for transform in transforms:
                if not isinstance(transform, dict):
                    continue
                if transform.get("type") != "scale":
                    continue
                scale = transform.get("scale", [])
                if isinstance(scale, list) and len(scale) >= 4:
                    return float(scale[1]), float(scale[2]), float(scale[3])
    return 1.0, 1.0, 1.0


def _smoke_validity_warning(*, split_summary: SplitSummary, gt_instances_total: int) -> str | None:
    if split_summary.test_frames < 10:
        return "TEST_FRAMES_LT_10: smoke is too small for evidentiary model ranking."
    if gt_instances_total < 100:
        return "GT_INSTANCES_LT_100: sparse denominator too small for stable precision/recall interpretation."
    return None


def _prepare_cellpose_training_data(frames: list[FrameDatum]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    images = [frame.image_2d.astype(np.float32, copy=False) for frame in frames]
    labels = [frame.gt_mask_2d.astype(np.int32, copy=False) for frame in frames]
    return images, labels


def _prepare_stardist_training_data(frames: list[FrameDatum]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    x = [_stardist_normalize(frame.image_2d) for frame in frames]
    y = [frame.gt_mask_2d.astype(np.int32, copy=False) for frame in frames]
    return x, y


def _run_cellpose_finetune(
    *,
    train_frames: list[FrameDatum],
    val_frames: list[FrameDatum],
    model_type: str,
    use_gpu: bool,
    epochs: int,
    output_dir: Path,
) -> tuple[object, dict]:
    from cellpose import models as cp_models
    from cellpose import train as cp_train

    train_images, train_labels = _prepare_cellpose_training_data(train_frames)
    val_images, val_labels = _prepare_cellpose_training_data(val_frames)
    output_dir.mkdir(parents=True, exist_ok=True)
    non_empty_train_masks = sum(1 for label in train_labels if int(np.max(label)) > 0)
    if non_empty_train_masks <= 0:
        raise ValueError("Cellpose fine-tune requires at least one non-empty training mask frame.")

    model = cp_models.CellposeModel(gpu=bool(use_gpu), model_type=model_type)
    result = cp_train.train_seg(
        model.net,
        train_data=train_images,
        train_labels=train_labels,
        test_data=(val_images if val_images else None),
        test_labels=(val_labels if val_labels else None),
        normalize=True,
        n_epochs=max(1, int(epochs)),
        min_train_masks=1,
        save_path=str(output_dir),
        model_name="cellpose_atabey",
    )
    details = {"result_repr": repr(result)}
    return model, details


def _run_stardist_finetune(
    *,
    train_frames: list[FrameDatum],
    val_frames: list[FrameDatum],
    pretrained_name: str,
    use_gpu: bool,
    epochs: int,
    output_dir: Path,
) -> tuple[object, dict]:
    from stardist.models import Config2D, StarDist2D

    x_train, y_train = _prepare_stardist_training_data(train_frames)
    x_val, y_val = _prepare_stardist_training_data(val_frames)

    pretrained = StarDist2D.from_pretrained(pretrained_name)
    config = Config2D(
        axes="YX",
        n_rays=int(pretrained.config.n_rays),
        grid=tuple(int(v) for v in pretrained.config.grid),
        n_channel_in=1,
        use_gpu=bool(use_gpu),
        train_epochs=max(1, int(epochs)),
        train_steps_per_epoch=max(1, len(x_train)),
    )
    model = StarDist2D(config, name="stardist_atabey", basedir=str(output_dir))
    model.keras_model.set_weights(pretrained.keras_model.get_weights())
    history = model.train(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=max(1, int(epochs)),
    )
    hist = getattr(history, "history", {}) if history is not None else {}
    details = {k: [float(v) for v in vals] for k, vals in hist.items()}
    return model, details


def _run_stardist_finetune_from_scratch(
    *,
    train_frames: list[FrameDatum],
    val_frames: list[FrameDatum],
    use_gpu: bool,
    epochs: int,
    output_dir: Path,
) -> tuple[object, dict]:
    from stardist.models import Config2D, StarDist2D

    x_train, y_train = _prepare_stardist_training_data(train_frames)
    x_val, y_val = _prepare_stardist_training_data(val_frames)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = Config2D(
        axes="YX",
        n_rays=32,
        grid=(1, 1),
        n_channel_in=1,
        use_gpu=bool(use_gpu),
        train_epochs=max(1, int(epochs)),
        train_steps_per_epoch=max(1, len(x_train)),
    )
    model = StarDist2D(config, name="stardist_atabey_scratch", basedir=str(output_dir))
    history = model.train(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=max(1, int(epochs)),
    )
    hist = getattr(history, "history", {}) if history is not None else {}
    details = {k: [float(v) for v in vals] for k, vals in hist.items()}
    return model, details


def _runtime_environment() -> dict[str, object]:
    env: dict[str, object] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    try:
        import torch

        env["torch_version"] = torch.__version__
        env["torch_cuda_available"] = bool(torch.cuda.is_available())
    except Exception as exc:  # pragma: no cover - optional dependency runtime surface.
        env["torch_error"] = repr(exc)

    try:
        import tensorflow as tf

        env["tensorflow_version"] = tf.__version__
        env["tensorflow_gpu_count"] = len(tf.config.list_physical_devices("GPU"))
    except Exception as exc:  # pragma: no cover - optional dependency runtime surface.
        env["tensorflow_error"] = repr(exc)

    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone CNN advisor evaluation for at-risk samples.")
    parser.add_argument("--train-dir", default="train", help="Directory containing *.zarr and *.geff training samples.")
    parser.add_argument(
        "--scan-json",
        default="submissions/cfar_bounded_scan_fulltrain.json",
        help="CFAR bounded scan JSON containing the at-risk sample list.",
    )
    parser.add_argument("--pfa-key", default="1e-03", help="PFA key in real_failures_routed_and_at_risk.")
    parser.add_argument("--max-samples", type=int, default=12, help="Bounded sample cap from the at-risk cohort.")
    parser.add_argument("--max-timepoints", type=int, default=10, help="Timepoint cap per sample.")
    parser.add_argument("--split-seed", type=int, default=7, help="Random seed for sample-level split.")
    parser.add_argument("--gt-radius-px", type=int, default=4, help="Raster radius for sparse GEFF centroids.")
    parser.add_argument("--iou-threshold", type=float, default=0.3, help="IoU threshold for instance match.")
    parser.add_argument(
        "--distance-threshold-um",
        type=float,
        default=6.0,
        help="Centroid distance threshold in microns for physical-unit matching diagnostics.",
    )
    parser.add_argument("--use-gpu", action="store_true", default=False, help="Enable GPU for CNN models if available.")

    parser.add_argument("--cellpose-model-type", default="cyto3", help="Cellpose pretrained model type.")
    parser.add_argument("--cellpose-diameter", type=float, default=None, help="Cellpose diameter override.")
    parser.add_argument("--cellpose-epochs", type=int, default=2, help="Cellpose fine-tune epochs.")

    parser.add_argument("--stardist-pretrained", default="2D_versatile_fluo", help="StarDist pretrained model name.")
    parser.add_argument("--stardist-epochs", type=int, default=2, help="StarDist fine-tune epochs.")

    parser.add_argument(
        "--skip-finetune",
        action="store_true",
        default=False,
        help="Run only zero-shot + CFAR comparison.",
    )
    parser.add_argument(
        "--skip-cellpose",
        action="store_true",
        default=False,
        help="Skip Cellpose zero-shot/fine-tune stages.",
    )
    parser.add_argument(
        "--skip-stardist",
        action="store_true",
        default=False,
        help="Skip StarDist zero-shot/fine-tune stages.",
    )
    parser.add_argument(
        "--output-json",
        default="submissions/cnn_advisor_eval.json",
        help="Detailed output JSON path.",
    )
    parser.add_argument(
        "--output-summary-json",
        default="submissions/cnn_advisor_eval_summary.json",
        help="Summary output JSON path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    train_dir = Path(args.train_dir)
    output_json = Path(args.output_json)
    output_summary_json = Path(args.output_summary_json)

    at_risk_ids = load_at_risk_sample_ids(args.scan_json, pfa_key=str(args.pfa_key))
    if not at_risk_ids:
        raise SystemExit("No at-risk sample IDs found in scan JSON for the chosen pfa key.")
    if args.max_samples is not None:
        at_risk_ids = at_risk_ids[: max(1, int(args.max_samples))]

    train_ids, val_ids, test_ids = _split_sample_ids(at_risk_ids, seed=int(args.split_seed))
    train_frames = _collect_frames(
        train_dir=train_dir,
        sample_ids=train_ids,
        max_timepoints=int(args.max_timepoints),
        gt_radius_px=int(args.gt_radius_px),
    )
    val_frames = _collect_frames(
        train_dir=train_dir,
        sample_ids=val_ids,
        max_timepoints=int(args.max_timepoints),
        gt_radius_px=int(args.gt_radius_px),
    )
    test_frames = _collect_frames(
        train_dir=train_dir,
        sample_ids=test_ids,
        max_timepoints=int(args.max_timepoints),
        gt_radius_px=int(args.gt_radius_px),
    )

    if not test_frames:
        raise SystemExit("No test frames collected; widen max-samples or max-timepoints.")

    split_summary = SplitSummary(
        train_samples=len(train_ids),
        val_samples=len(val_ids),
        test_samples=len(test_ids),
        train_frames=len(train_frames),
        val_frames=len(val_frames),
        test_frames=len(test_frames),
    )

    method_results: list[MethodAggregate] = []
    per_method_frame_diagnostics: dict[str, list[dict[str, object]]] = {}
    method_errors: dict[str, str] = {}
    fine_tune_curves: dict[str, dict] = {}

    z_um, y_um, x_um = _read_pixel_spacing_um(train_dir, test_ids[0])
    gt_instances_total = int(sum(int(np.max(frame.gt_mask_2d)) for frame in test_frames))
    gt_points_total = int(sum(len(frame.gt_centers_yx) for frame in test_frames))
    smoke_warning = _smoke_validity_warning(split_summary=split_summary, gt_instances_total=gt_instances_total)

    # 1) Current CFAR baseline.
    cfar_result, cfar_diag = _eval_cfar(
        train_dir=train_dir,
        frames=test_frames,
        gt_radius_px=int(args.gt_radius_px),
        iou_threshold=float(args.iou_threshold),
        distance_threshold_um=float(args.distance_threshold_um),
        pixel_size_y_um=float(y_um),
        pixel_size_x_um=float(x_um),
    )
    method_results.append(cfar_result)
    per_method_frame_diagnostics[cfar_result.method] = [asdict(item) for item in cfar_diag]

    # 2) Cellpose zero-shot + optional fine-tune.
    if not bool(args.skip_cellpose):
        try:
            from cellpose import models as cp_models

            cp_zero = cp_models.CellposeModel(gpu=bool(args.use_gpu), model_type=str(args.cellpose_model_type))
            cp_zero_result, cp_zero_diag = _eval_cellpose(
                cp_zero,
                frames=test_frames,
                iou_threshold=float(args.iou_threshold),
                method_name="cellpose_zero_shot",
                diameter=(None if args.cellpose_diameter is None else float(args.cellpose_diameter)),
                distance_threshold_um=float(args.distance_threshold_um),
                pixel_size_y_um=float(y_um),
                pixel_size_x_um=float(x_um),
            )
            method_results.append(cp_zero_result)
            per_method_frame_diagnostics[cp_zero_result.method] = [asdict(item) for item in cp_zero_diag]

            if not bool(args.skip_finetune):
                cp_model_ft, cp_details = _run_cellpose_finetune(
                    train_frames=train_frames,
                    val_frames=val_frames,
                    model_type=str(args.cellpose_model_type),
                    use_gpu=bool(args.use_gpu),
                    epochs=int(args.cellpose_epochs),
                    output_dir=output_json.parent / "cnn_models" / "cellpose",
                )
                fine_tune_curves["cellpose"] = cp_details
                cp_ft_result, cp_ft_diag = _eval_cellpose(
                    cp_model_ft,
                    frames=test_frames,
                    iou_threshold=float(args.iou_threshold),
                    method_name="cellpose_finetuned",
                    diameter=(None if args.cellpose_diameter is None else float(args.cellpose_diameter)),
                    distance_threshold_um=float(args.distance_threshold_um),
                    pixel_size_y_um=float(y_um),
                    pixel_size_x_um=float(x_um),
                )
                method_results.append(cp_ft_result)
                per_method_frame_diagnostics[cp_ft_result.method] = [asdict(item) for item in cp_ft_diag]
        except Exception:
            method_errors["cellpose"] = traceback.format_exc(limit=3)

    # 3) StarDist zero-shot + optional fine-tune.
    if not bool(args.skip_stardist):
        pretrained_ok = False
        try:
            from stardist.models import StarDist2D

            sd_zero = StarDist2D.from_pretrained(str(args.stardist_pretrained))
            sd_zero_result, sd_zero_diag = _eval_stardist(
                sd_zero,
                frames=test_frames,
                iou_threshold=float(args.iou_threshold),
                method_name="stardist_zero_shot",
                distance_threshold_um=float(args.distance_threshold_um),
                pixel_size_y_um=float(y_um),
                pixel_size_x_um=float(x_um),
            )
            method_results.append(sd_zero_result)
            per_method_frame_diagnostics[sd_zero_result.method] = [asdict(item) for item in sd_zero_diag]
            pretrained_ok = True
        except Exception:
            method_errors["stardist_zero_shot_pretrained"] = traceback.format_exc(limit=3)

        if not bool(args.skip_finetune):
            try:
                if pretrained_ok:
                    sd_model_ft, sd_details = _run_stardist_finetune(
                        train_frames=train_frames,
                        val_frames=val_frames,
                        pretrained_name=str(args.stardist_pretrained),
                        use_gpu=bool(args.use_gpu),
                        epochs=int(args.stardist_epochs),
                        output_dir=output_json.parent / "cnn_models" / "stardist",
                    )
                    method_name = "stardist_finetuned"
                else:
                    sd_model_ft, sd_details = _run_stardist_finetune_from_scratch(
                        train_frames=train_frames,
                        val_frames=val_frames,
                        use_gpu=bool(args.use_gpu),
                        epochs=int(args.stardist_epochs),
                        output_dir=output_json.parent / "cnn_models" / "stardist_scratch",
                    )
                    method_name = "stardist_finetuned_scratch"

                fine_tune_curves["stardist"] = sd_details
                sd_ft_result, sd_ft_diag = _eval_stardist(
                    sd_model_ft,
                    frames=test_frames,
                    iou_threshold=float(args.iou_threshold),
                    method_name=method_name,
                    distance_threshold_um=float(args.distance_threshold_um),
                    pixel_size_y_um=float(y_um),
                    pixel_size_x_um=float(x_um),
                )
                method_results.append(sd_ft_result)
                per_method_frame_diagnostics[sd_ft_result.method] = [asdict(item) for item in sd_ft_diag]
            except Exception:
                method_errors["stardist_finetune"] = traceback.format_exc(limit=3)

    output_payload = {
        "scope": "standalone_cnn_advisor_evaluation",
        "guardrail": "No run.py or production runner wiring in this phase.",
        "environment": _runtime_environment(),
        "args": vars(args),
        "at_risk_sample_count_used": len(at_risk_ids),
        "splits": {
            "train": train_ids,
            "val": val_ids,
            "test": test_ids,
            "summary": asdict(split_summary),
        },
        "methods": [asdict(result) for result in method_results],
        "per_method_frame_diagnostics": per_method_frame_diagnostics,
        "fine_tune_curves": fine_tune_curves,
        "method_errors": method_errors,
        "metric_domains": {
            "iou_metric_domain": "2D YX pseudo-instance masks on MIP using disk-rasterized sparse GT centroids",
            "distance_metric_domain": "2D YX centroid distance on MIP with physical scaling",
            "units": {
                "pixel": "voxel-projected MIP pixel",
                "distance_um": "micron",
                "pixel_spacing_um": {
                    "z": float(z_um),
                    "y": float(y_um),
                    "x": float(x_um),
                },
            },
        },
        "raw_denominators": {
            "test_frames": int(len(test_frames)),
            "gt_instances_total": int(gt_instances_total),
            "gt_points_total": int(gt_points_total),
        },
        "smoke_validity_warning": smoke_warning,
        "metric_caveat": (
            "Metrics use pseudo-instance masks built from sparse GEFF centroid labels on 2D MIPs; "
            "use as bounded advisor-screening signals only."
        ),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    summary = {
        "at_risk_sample_count_used": len(at_risk_ids),
        "split_summary": asdict(split_summary),
        "methods": [
            {
                "method": item.method,
                "precision": round(float(item.precision), 5),
                "recall": round(float(item.recall), 5),
                "f1": round(float(item.f1), 5),
                "mean_best_iou_per_gt": round(float(item.mean_best_iou_per_gt), 5),
                "mean_match_iou": round(float(item.mean_match_iou), 5),
                "mean_best_distance_um_per_gt": round(float(item.mean_best_distance_um_per_gt), 5),
                "mean_match_distance_um": round(float(item.mean_match_distance_um), 5),
                "distance_threshold_um": round(float(item.distance_threshold_um), 5),
                "mean_runtime_seconds_per_frame": round(float(item.mean_runtime_seconds_per_frame), 5),
            }
            for item in method_results
        ],
        "method_errors": {k: v.splitlines()[-1] if v else "" for k, v in method_errors.items()},
        "raw_denominators": {
            "test_frames": int(len(test_frames)),
            "gt_instances_total": int(gt_instances_total),
            "gt_points_total": int(gt_points_total),
        },
        "metric_domains": {
            "iou": "2D YX pseudo-instance mask IoU on MIP",
            "distance": "2D YX centroid distance (micron-scaled)",
            "pixel_spacing_um": {
                "z": round(float(z_um), 6),
                "y": round(float(y_um), 6),
                "x": round(float(x_um), 6),
            },
        },
        "smoke_validity_warning": smoke_warning,
    }
    output_summary_json.parent.mkdir(parents=True, exist_ok=True)
    output_summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({"output_json": str(output_json), "output_summary_json": str(output_summary_json)}), flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
