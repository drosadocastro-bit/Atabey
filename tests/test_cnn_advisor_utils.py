from __future__ import annotations

import numpy as np

from atabey.experiments.cnn_advisor import (
    distance_match_metrics,
    draw_disk_instance_mask,
    instance_centroids_yx,
    instance_iou_metrics,
    select_timepoints,
)


def test_select_timepoints_spread_and_unique() -> None:
    points = select_timepoints(100, 10)
    assert points[0] == 0
    assert points[-1] == 99
    assert len(points) == len(set(points))
    assert len(points) == 10


def test_draw_disk_instance_mask_creates_instances() -> None:
    mask = draw_disk_instance_mask((32, 32), [(8, 8), (24, 24)], radius_px=3)
    labels = sorted(int(v) for v in np.unique(mask))
    assert labels == [0, 1, 2]


def test_instance_iou_metrics_perfect_match() -> None:
    gt = np.zeros((32, 32), dtype=np.int32)
    gt[5:10, 5:10] = 1
    pred = np.zeros((32, 32), dtype=np.int32)
    pred[5:10, 5:10] = 1

    metrics = instance_iou_metrics(gt, pred, iou_threshold=0.5)

    assert metrics.tp == 1
    assert metrics.fp == 0
    assert metrics.fn == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.matched_iou_values == (1.0,)
    assert metrics.best_iou_per_gt == (1.0,)
    assert metrics.iou_threshold == 0.5


def test_instance_iou_metrics_penalizes_fp_and_fn() -> None:
    gt = np.zeros((32, 32), dtype=np.int32)
    gt[5:10, 5:10] = 1
    pred = np.zeros((32, 32), dtype=np.int32)
    pred[20:24, 20:24] = 1

    metrics = instance_iou_metrics(gt, pred, iou_threshold=0.5)

    assert metrics.tp == 0
    assert metrics.fp == 1
    assert metrics.fn == 1
    assert metrics.recall == 0.0


def test_instance_centroids_yx_computes_centers() -> None:
    mask = np.zeros((10, 10), dtype=np.int32)
    mask[1:3, 1:3] = 1
    mask[6:8, 6:8] = 2

    centroids = instance_centroids_yx(mask)

    assert len(centroids) == 2
    assert centroids[0] == (1.5, 1.5)
    assert centroids[1] == (6.5, 6.5)


def test_distance_match_metrics_uses_physical_threshold() -> None:
    gt_points = [(10.0, 10.0)]
    pred_points = [(11.0, 10.0), (30.0, 30.0)]

    metrics = distance_match_metrics(
        gt_points,
        pred_points,
        distance_threshold_um=0.5,
        pixel_size_y_um=0.4,
        pixel_size_x_um=0.4,
    )

    assert metrics.tp == 1
    assert metrics.fp == 1
    assert metrics.fn == 0
    assert metrics.matched_distance_um == (0.4,)
    assert metrics.best_distance_um_per_gt == (0.4,)
