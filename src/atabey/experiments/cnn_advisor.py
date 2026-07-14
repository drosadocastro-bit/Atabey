from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class FrameKey:
    sample_id: str
    t: int


@dataclass(frozen=True)
class DetectionMetrics:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    predicted_instances: int
    ground_truth_instances: int
    matched_iou_values: tuple[float, ...] = ()
    best_iou_per_gt: tuple[float, ...] = ()
    iou_threshold: float = 0.0


@dataclass(frozen=True)
class DistanceMatchMetrics:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    predicted_points: int
    ground_truth_points: int
    matched_distance_um: tuple[float, ...] = ()
    best_distance_um_per_gt: tuple[float, ...] = ()
    distance_threshold_um: float = 0.0


def load_at_risk_sample_ids(scan_json: str | Path, *, pfa_key: str = "1e-03") -> list[str]:
    import json

    payload = json.loads(Path(scan_json).read_text(encoding="utf-8"))
    failures = payload.get("real_failures_routed_and_at_risk", {})
    ids = failures.get(pfa_key, []) if isinstance(failures, dict) else []
    return sorted(str(sample_id) for sample_id in ids)


def select_timepoints(total_timepoints: int, max_timepoints: int | None) -> list[int]:
    if total_timepoints <= 0:
        return []
    if max_timepoints is None or max_timepoints >= total_timepoints:
        return list(range(total_timepoints))
    if max_timepoints <= 1:
        return [0]
    anchors = np.linspace(0, total_timepoints - 1, num=max_timepoints, dtype=int)
    return sorted(set(int(t) for t in anchors))


def draw_disk_instance_mask(
    shape_yx: tuple[int, int],
    centers_yx: list[tuple[int, int]],
    *,
    radius_px: int,
) -> np.ndarray:
    height, width = shape_yx
    if height <= 0 or width <= 0:
        raise ValueError("Mask shape must be positive")
    radius = max(1, int(radius_px))
    yy, xx = np.ogrid[:height, :width]
    mask = np.zeros((height, width), dtype=np.int32)
    for instance_id, (cy, cx) in enumerate(centers_yx, start=1):
        circle = (yy - int(cy)) ** 2 + (xx - int(cx)) ** 2 <= radius * radius
        # Last writer wins for overlaps; this keeps instance IDs contiguous.
        mask[circle] = instance_id
    return mask


def detections_to_instance_mask(
    shape_yx: tuple[int, int],
    detections_yx: list[tuple[float, float]],
    *,
    radius_px: int,
) -> np.ndarray:
    centers = [(int(round(y)), int(round(x))) for y, x in detections_yx]
    return draw_disk_instance_mask(shape_yx, centers, radius_px=radius_px)


def instance_centroids_yx(mask: np.ndarray) -> list[tuple[float, float]]:
    labels = [int(v) for v in np.unique(mask) if int(v) > 0]
    centroids: list[tuple[float, float]] = []
    for label in labels:
        points = np.argwhere(mask == label)
        if points.size == 0:
            continue
        center = points.mean(axis=0)
        centroids.append((float(center[0]), float(center[1])))
    return centroids


def instance_iou_metrics(
    gt_mask: np.ndarray,
    pred_mask: np.ndarray,
    *,
    iou_threshold: float,
) -> DetectionMetrics:
    if gt_mask.shape != pred_mask.shape:
        raise ValueError("Ground-truth and prediction masks must share the same shape")

    gt_ids = [int(v) for v in np.unique(gt_mask) if int(v) > 0]
    pred_ids = [int(v) for v in np.unique(pred_mask) if int(v) > 0]
    if not gt_ids and not pred_ids:
        return DetectionMetrics(
            tp=0,
            fp=0,
            fn=0,
            precision=1.0,
            recall=1.0,
            f1=1.0,
            predicted_instances=0,
            ground_truth_instances=0,
            matched_iou_values=(),
            best_iou_per_gt=(),
            iou_threshold=float(iou_threshold),
        )

    used_pred: set[int] = set()
    tp = 0
    threshold = float(iou_threshold)
    matched_ious: list[float] = []
    best_iou_per_gt: list[float] = []

    for gt_id in gt_ids:
        gt_region = gt_mask == gt_id
        best_pred = None
        best_iou = 0.0
        for pred_id in pred_ids:
            if pred_id in used_pred:
                continue
            pred_region = pred_mask == pred_id
            intersection = int(np.count_nonzero(gt_region & pred_region))
            if intersection == 0:
                continue
            union = int(np.count_nonzero(gt_region | pred_region))
            iou = float(intersection) / float(union) if union > 0 else 0.0
            if iou > best_iou:
                best_iou = iou
                best_pred = pred_id
        best_iou_per_gt.append(float(best_iou))
        if best_pred is not None and best_iou >= threshold:
            used_pred.add(best_pred)
            tp += 1
            matched_ious.append(float(best_iou))

    fp = len(pred_ids) - tp
    fn = len(gt_ids) - tp
    precision = float(tp) / float(tp + fp) if (tp + fp) > 0 else 0.0
    recall = float(tp) / float(tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return DetectionMetrics(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        predicted_instances=len(pred_ids),
        ground_truth_instances=len(gt_ids),
        matched_iou_values=tuple(matched_ious),
        best_iou_per_gt=tuple(best_iou_per_gt),
        iou_threshold=threshold,
    )


def distance_match_metrics(
    gt_points_yx: list[tuple[float, float]],
    pred_points_yx: list[tuple[float, float]],
    *,
    distance_threshold_um: float,
    pixel_size_y_um: float,
    pixel_size_x_um: float,
) -> DistanceMatchMetrics:
    if not gt_points_yx and not pred_points_yx:
        return DistanceMatchMetrics(
            tp=0,
            fp=0,
            fn=0,
            precision=1.0,
            recall=1.0,
            f1=1.0,
            predicted_points=0,
            ground_truth_points=0,
            matched_distance_um=(),
            best_distance_um_per_gt=(),
            distance_threshold_um=float(distance_threshold_um),
        )

    used_pred: set[int] = set()
    tp = 0
    matched_distances: list[float] = []
    best_distances: list[float] = []

    threshold_um = float(distance_threshold_um)
    y_scale = float(pixel_size_y_um)
    x_scale = float(pixel_size_x_um)

    for gt_y, gt_x in gt_points_yx:
        best_pred_index = None
        best_distance = float("inf")
        for index, (pred_y, pred_x) in enumerate(pred_points_yx):
            if index in used_pred:
                continue
            dy_um = (float(pred_y) - float(gt_y)) * y_scale
            dx_um = (float(pred_x) - float(gt_x)) * x_scale
            distance_um = float(np.hypot(dy_um, dx_um))
            if distance_um < best_distance:
                best_distance = distance_um
                best_pred_index = index

        if np.isfinite(best_distance):
            best_distances.append(float(best_distance))
        else:
            best_distances.append(float("inf"))

        if best_pred_index is not None and best_distance <= threshold_um:
            used_pred.add(best_pred_index)
            tp += 1
            matched_distances.append(float(best_distance))

    fp = len(pred_points_yx) - tp
    fn = len(gt_points_yx) - tp
    precision = float(tp) / float(tp + fp) if (tp + fp) > 0 else 0.0
    recall = float(tp) / float(tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return DistanceMatchMetrics(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        predicted_points=len(pred_points_yx),
        ground_truth_points=len(gt_points_yx),
        matched_distance_um=tuple(matched_distances),
        best_distance_um_per_gt=tuple(best_distances),
        distance_threshold_um=threshold_um,
    )
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Tuple

class SparsePeakLoss(nn.Module):
    """
    Sparse-Annotation-Aware Peak-Detection Loss.
    
    Computes a local Softmax / CrossEntropy loss only around annotated ground-truth centers.
    Unannotated regions are ignored (zero loss gradient).
    """
    def __init__(self, window_shape: Tuple[int, int, int] = (5, 3, 3)):
        super().__init__()
        self.window_shape = window_shape
        self.depth, self.height, self.width = window_shape
        
        # We expect window_shape to be odd so there is a defined center
        assert self.depth % 2 == 1
        assert self.height % 2 == 1
        assert self.width % 2 == 1
        
        self.target_idx = (self.depth * self.height * self.width) // 2
        
    def forward(
        self, 
        predictions: torch.Tensor, 
        gt_centers: List[Tuple[int, int, int, int]]
    ) -> torch.Tensor:
        """
        predictions: Tensor of shape (B, 1, Z, Y, X) containing raw logits
        gt_centers: List of tuples (batch_idx, z, y, x) indicating annotated cell centers
        """
        B, C, Z, Y, X = predictions.shape
        assert C == 1, "Expected single-channel predictions"
        
        if not gt_centers:
            return predictions.sum() * 0.0  # Zero loss, but keeps grad graph
            
        dz = self.depth // 2
        dy = self.height // 2
        dx = self.width // 2
        
        windows = []
        for b, z, y, x in gt_centers:
            # Extract window, padding if near the edge
            # To handle edges, we pad the prediction tensor first, or dynamically pad
            z_min = max(0, z - dz)
            z_max = min(Z, z + dz + 1)
            y_min = max(0, y - dy)
            y_max = min(Y, y + dy + 1)
            x_min = max(0, x - dx)
            x_max = min(X, x + dx + 1)
            
            # For simplicity in this smoke test, we'll assume centers are strictly inside the volume 
            # by at least the margin, or we pad if necessary.
            
            # Let's do dynamic padding
            pad_z_before = max(0, dz - z)
            pad_z_after = max(0, z + dz + 1 - Z)
            pad_y_before = max(0, dy - y)
            pad_y_after = max(0, y + dy + 1 - Y)
            pad_x_before = max(0, dx - x)
            pad_x_after = max(0, x + dx + 1 - X)
            
            # PyTorch pad format: (pad_left, pad_right, pad_top, pad_bottom, pad_front, pad_back)
            pad = (pad_x_before, pad_x_after, pad_y_before, pad_y_after, pad_z_before, pad_z_after)
            
            # Extract the actual valid region
            region = predictions[b, 0, z_min:z_max, y_min:y_max, x_min:x_max]
            
            if sum(pad) > 0:
                region = F.pad(region, pad, value=-1e9)  # Large negative logits for padded areas
                
            windows.append(region.reshape(-1))
            
        if not windows:
            return predictions.sum() * 0.0
            
        windows_tensor = torch.stack(windows)  # Shape (N, D*H*W)
        
        # Target is always the center index
        targets = torch.full((len(windows),), self.target_idx, dtype=torch.long, device=predictions.device)
        
        # Cross entropy computes Softmax and then NLLLoss
        loss = F.cross_entropy(windows_tensor, targets)
        
        return loss

class SimplePeakCNN(nn.Module):
    """
    A minimal, memory-conscious 3D CNN for peak detection.
    """
    def __init__(self, in_channels: int = 1, base_filters: int = 16):
        super().__init__()
        # Very simple fully convolutional network (not even a full U-Net) to keep memory low
        self.net = nn.Sequential(
            nn.Conv3d(in_channels, base_filters, kernel_size=3, padding=1),
            nn.BatchNorm3d(base_filters),
            nn.ReLU(inplace=True),
            
            nn.Conv3d(base_filters, base_filters * 2, kernel_size=3, padding=1),
            nn.BatchNorm3d(base_filters * 2),
            nn.ReLU(inplace=True),
            
            nn.Conv3d(base_filters * 2, base_filters, kernel_size=3, padding=1),
            nn.BatchNorm3d(base_filters),
            nn.ReLU(inplace=True),
            
            nn.Conv3d(base_filters, 1, kernel_size=1)
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

def train_cnn_advisor_smoke():
    # Will be implemented in cnn_advisor.py 
    pass

def detect_cnn_peaks():
    pass
import torch
import torch.nn.functional as F
import psutil
import os
import time

def get_memory_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 10**6

def train_cnn_advisor_smoke(
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    loss_fn: torch.nn.Module,
    volume: torch.Tensor,
    gt_centers: list,
    epochs: int = 5
) -> list:
    """
    Minimal, memory-conscious training loop for bounded smoke test.
    Only trains on a single timepoint volume due to memory constraints.
    Returns the list of loss values per epoch.
    """
    print(f"Starting bounded smoke test on volume shape {volume.shape} with {len(gt_centers)} GT centers.")
    print(f"Initial RAM: {get_memory_mb():.2f} MB")
    
    model.train()
    loss_history = []
    
    for epoch in range(epochs):
        t0 = time.time()
        optimizer.zero_grad()
        
        # Forward pass
        predictions = model(volume)
        
        # Compute loss
        loss = loss_fn(predictions, gt_centers)
        
        if torch.isnan(loss) or (hasattr(loss, "item") and loss.item() == 0.0 and len(gt_centers) > 0):
            print(f"Epoch {epoch}: WARNING - Loss is {loss.item()}!")
            
        # Backward pass
        loss.backward()
        optimizer.step()
        
        loss_val = loss.item()
        loss_history.append(loss_val)
        
        t1 = time.time()
        print(f"Epoch {epoch+1}/{epochs} | Loss: {loss_val:.6f} | Time: {t1-t0:.2f}s | RAM: {get_memory_mb():.2f} MB")
        
    return loss_history

def detect_cnn_peaks(
    model: torch.nn.Module,
    volume: torch.Tensor,
    threshold: float = 0.5
) -> list:
    """
    Extract candidate peaks from the CNN advisor.
    Returns list of (z, y, x) tuples for predicted centers.
    """
    model.eval()
    with torch.no_grad():
        logits = model(volume)
        probs = torch.sigmoid(logits)
        
    probs_np = probs.squeeze(0).squeeze(0).cpu().numpy() # Shape: (Z, Y, X)
    
    from atabey.detection.baseline import threshold_local_maxima
    # Use the existing local maxima extraction on the CNN probabilities
    # We pass a dummy sample_id and t
    detections = threshold_local_maxima(
        sample_id="cnn_temp", t=0, volume=probs_np, threshold=threshold, min_distance_voxels=(1, 3, 3)
    )
    
    return [(d.z, d.y, d.x) for d in detections]
