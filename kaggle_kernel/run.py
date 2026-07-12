import csv
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import median

import numpy as np


@dataclass(frozen=True)
class VoxelScale:
    z: float
    y: float
    x: float

    def voxel_to_um(self, z, y, x):
        return z * self.z, y * self.y, x * self.x


DEFAULT_VOXEL_SCALE_UM = VoxelScale(z=1.625, y=0.40625, x=0.40625)


@dataclass(frozen=True)
class Detection:
    node_id: str
    sample_id: str
    t: int
    z: float
    y: float
    x: float
    z_um: float
    y_um: float
    x_um: float
    intensity_mean: float | None = None
    intensity_max: float | None = None
    component_volume: int | None = None
    detection_confidence: float | None = None

    @property
    def position_um(self):
        return self.z_um, self.y_um, self.x_um


@dataclass(frozen=True)
class LineageEdge:
    source_id: str
    target_id: str
    confidence: float | None = None
    relation: str = "continuation"


@dataclass
class LineageGraph:
    sample_id: str
    detections: list[Detection] = field(default_factory=list)
    edges: list[LineageEdge] = field(default_factory=list)

    def add_detection(self, detection):
        self.detections.append(detection)

    def add_edge(self, edge):
        self.edges.append(edge)


@dataclass(frozen=True)
class ForegroundProfile:
    sampled_timepoints: tuple[int, ...]
    median_largest_component_voxels: float
    median_foreground_fraction: float
    median_component_count: float
    median_kept_component_count: float


@dataclass(frozen=True)
class AdaptiveBaselineSettings:
    detector: str
    threshold: float
    min_volume: int
    peak_min_distance_voxels: tuple[int, int, int]
    link_strategy: str
    max_link_distance_um: float
    reason: str


@dataclass(frozen=True)
class SampleRunRecord:
    sample_id: str
    sample_path: str
    route: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    detector: str
    threshold: float
    min_volume: int
    peak_min_distance_voxels: tuple[int, int, int]
    link_strategy: str
    max_link_distance_um: float
    median_largest_component_voxels: float
    median_foreground_fraction: float
    reason: str
    cfar_training_radius_voxels: tuple[int, int, int] | None = None
    cfar_guard_radius_voxels: tuple[int, int, int] | None = None
    cfar_k_sigma: float | None = None
    sidelobe_radius_voxels: tuple[int, int, int] | None = None
    sidelobe_floor_ratio: float | None = None
    max_detections_per_timepoint: int | None = None
    cfar_spike_fallback_count: int | None = None
    max_timepoints: int | None = None


@dataclass(frozen=True)
class GuardrailSettings:
    spike_multiplier: float
    min_history: int
    history_window: int
    min_absolute_count: int
    fallback_threshold: float


try:
    from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS as _SHARED_GUARDRAIL_SETTINGS
except Exception:  # pragma: no cover - Kaggle self-contained mode can run without local src package.
    _SHARED_GUARDRAIL_SETTINGS = None


if _SHARED_GUARDRAIL_SETTINGS is None:
    DEFAULT_GUARDRAIL_SETTINGS = GuardrailSettings(
        spike_multiplier=1.8,
        min_history=6,
        history_window=12,
        min_absolute_count=1200,
        fallback_threshold=0.65,
    )
else:
    DEFAULT_GUARDRAIL_SETTINGS = GuardrailSettings(
        spike_multiplier=float(_SHARED_GUARDRAIL_SETTINGS.spike_multiplier),
        min_history=int(_SHARED_GUARDRAIL_SETTINGS.min_history),
        history_window=int(_SHARED_GUARDRAIL_SETTINGS.history_window),
        min_absolute_count=int(_SHARED_GUARDRAIL_SETTINGS.min_absolute_count),
        fallback_threshold=float(_SHARED_GUARDRAIL_SETTINGS.fallback_threshold),
    )


def robust_normalize(volume, lower=1.0, upper=99.5):
    low, high = np.percentile(volume, [lower, upper])
    if high <= low:
        return np.zeros_like(volume, dtype=np.float32)
    normalized = (volume.astype(np.float32) - low) / (high - low)
    return np.clip(normalized, 0.0, 1.0)


class ManualZarrV3Array:
    def __init__(self, array_path):
        self.array_path = Path(array_path)
        metadata = json.loads((self.array_path / "zarr.json").read_text(encoding="utf-8"))
        self.shape = tuple(int(value) for value in metadata["shape"])
        self.chunk_shape = tuple(int(value) for value in metadata["chunk_grid"]["configuration"]["chunk_shape"])
        self.dtype = np.dtype("<u2")
        if metadata.get("data_type") != "uint16":
            raise ValueError(f"Unsupported Zarr dtype: {metadata.get('data_type')}")
        codec_names = [codec.get("name") for codec in metadata.get("codecs", [])]
        if codec_names != ["bytes", "blosc"]:
            raise ValueError(f"Unsupported Zarr codecs: {codec_names}")

    def __getitem__(self, t):
        import blosc2

        if not isinstance(t, int):
            raise TypeError("Manual reader supports integer timepoint indexing only")
        chunk_path = self.array_path / "c" / str(int(t)) / "0" / "0" / "0"
        compressed = chunk_path.read_bytes()
        decompressed = blosc2.decompress(compressed)
        chunk = np.frombuffer(decompressed, dtype=self.dtype).reshape(self.chunk_shape)
        return chunk[0]


def open_competition_array(sample_path):
    array_path = Path(sample_path) / "0"
    if not array_path.exists():
        raise FileNotFoundError(f"Expected competition array at {array_path}")
    try:
        import zarr
        return zarr.open(str(array_path), mode="r")
    except ModuleNotFoundError:
        return ManualZarrV3Array(array_path)


def read_timepoint(array, t):
    return array[t]


def sample_id_from_zarr_path(path):
    return Path(path).name.removesuffix(".zarr")


def detections_from_components(sample_id, t, labels, image, voxel_scale=DEFAULT_VOXEL_SCALE_UM, min_volume=1):
    from scipy import ndimage

    flat_labels = labels.ravel()
    if flat_labels.size == 0:
        return []
    max_label = int(flat_labels.max())
    if max_label <= 0:
        return []

    z_idx, y_idx, x_idx = np.nonzero(labels)
    component_labels = labels[z_idx, y_idx, x_idx].astype(np.int64)
    counts = np.bincount(component_labels, minlength=max_label + 1)
    valid_labels = [int(label_id) for label_id in range(1, max_label + 1) if counts[label_id] >= min_volume]
    if not valid_labels:
        return []

    z_sums = np.bincount(component_labels, weights=z_idx, minlength=max_label + 1)
    y_sums = np.bincount(component_labels, weights=y_idx, minlength=max_label + 1)
    x_sums = np.bincount(component_labels, weights=x_idx, minlength=max_label + 1)
    values = image[z_idx, y_idx, x_idx].astype(float)
    intensity_sums = np.bincount(component_labels, weights=values, minlength=max_label + 1)
    intensity_maxima = ndimage.maximum(image, labels=labels, index=valid_labels)

    detections = []
    for label_id, intensity_max in zip(valid_labels, intensity_maxima):
        count = int(counts[label_id])
        z = float(z_sums[label_id] / count)
        y = float(y_sums[label_id] / count)
        x = float(x_sums[label_id] / count)
        z_um, y_um, x_um = voxel_scale.voxel_to_um(z, y, x)
        detections.append(Detection(
            node_id=f"{sample_id}:t{t}:c{label_id}", sample_id=sample_id, t=t,
            z=z, y=y, x=x, z_um=z_um, y_um=y_um, x_um=x_um,
            intensity_mean=float(intensity_sums[label_id] / count), intensity_max=float(intensity_max),
            component_volume=count,
        ))
    return detections


def threshold_connected_components(sample_id, t, volume, threshold=0.65, min_volume=4):
    from scipy import ndimage

    normalized = robust_normalize(volume)
    labels, _ = ndimage.label(normalized >= threshold)
    return detections_from_components(sample_id, t, labels, volume, min_volume=min_volume)


def threshold_local_maxima(sample_id, t, volume, threshold=0.65, min_distance_voxels=(1, 3, 3), max_detections=None):
    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    size = tuple(2 * max(0, int(radius)) + 1 for radius in min_distance_voxels)
    peak_source = volume.astype(np.float32)
    local_max = ndimage.maximum_filter(peak_source, size=size, mode="nearest")
    peak_mask = (normalized >= threshold) & (peak_source == local_max)
    coords = np.argwhere(peak_mask)
    if coords.size == 0:
        return []

    confidences = normalized[peak_mask]
    raw_values = volume[peak_mask]
    order = np.argsort(confidences)[::-1]
    if max_detections is not None:
        order = order[: int(max_detections)]

    detections = []
    for output_idx, coord_idx in enumerate(order, start=1):
        z, y, x = coords[int(coord_idx)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(zf, yf, xf)
        raw_value = float(raw_values[int(coord_idx)])
        detections.append(Detection(
            node_id=f"{sample_id}:t{t}:p{output_idx}", sample_id=sample_id, t=t,
            z=zf, y=yf, x=xf, z_um=z_um, y_um=y_um, x_um=x_um,
            intensity_mean=raw_value, intensity_max=raw_value, component_volume=1,
            detection_confidence=float(confidences[int(coord_idx)]),
        ))
    detections.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return detections


def threshold_local_maxima_cfar(sample_id, t, volume, threshold=0.50, min_distance_voxels=(1, 3, 3),
                                max_detections=None, cfar_training_radius_voxels=(1, 7, 7),
                                cfar_guard_radius_voxels=(0, 1, 1), cfar_k_sigma=1.0):
    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    peak_source = volume.astype(np.float32)
    peak_size = tuple(2 * max(0, int(radius)) + 1 for radius in min_distance_voxels)
    local_max = ndimage.maximum_filter(peak_source, size=peak_size, mode="nearest")
    peak_mask = peak_source == local_max

    background_mean, background_std = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
    )
    adaptive_threshold = background_mean + float(cfar_k_sigma) * background_std
    keep_mask = peak_mask & (normalized >= float(threshold)) & (normalized >= adaptive_threshold)
    coords = np.argwhere(keep_mask)
    if coords.size == 0:
        return []

    confidences = normalized[keep_mask]
    adaptive_at_peaks = adaptive_threshold[keep_mask]
    margin_confidences = np.maximum(
        0.0,
        (confidences - adaptive_at_peaks) / np.maximum(adaptive_at_peaks, 1e-6),
    )
    raw_values = volume[keep_mask]
    order = np.argsort(margin_confidences)[::-1]
    if max_detections is not None:
        order = order[: int(max_detections)]

    detections = []
    for output_idx, coord_idx in enumerate(order, start=1):
        z, y, x = coords[int(coord_idx)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(zf, yf, xf)
        raw_value = float(raw_values[int(coord_idx)])
        confidence = _cfar_margin_confidence(
            float(confidences[int(coord_idx)]),
            float(adaptive_at_peaks[int(coord_idx)]),
        )
        detections.append(Detection(
            node_id=f"{sample_id}:t{t}:cf{output_idx}", sample_id=sample_id, t=t,
            z=zf, y=yf, x=xf, z_um=z_um, y_um=y_um, x_um=x_um,
            intensity_mean=raw_value, intensity_max=raw_value, component_volume=1,
            detection_confidence=confidence,
        ))
    detections.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return detections


def threshold_local_maxima_cfar_sidelobe(sample_id, t, volume, threshold=0.50,
                                         min_distance_voxels=(1, 3, 3), max_detections=None,
                                         cfar_training_radius_voxels=(1, 7, 7),
                                         cfar_guard_radius_voxels=(0, 1, 1), cfar_k_sigma=1.0,
                                         sidelobe_radius_voxels=(0, 2, 2), sidelobe_floor_ratio=0.85):
    detections = threshold_local_maxima_cfar(
        sample_id,
        t,
        volume,
        threshold=threshold,
        min_distance_voxels=min_distance_voxels,
        max_detections=max_detections,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
        cfar_k_sigma=cfar_k_sigma,
    )
    if not detections:
        return []
    kept = _sidelobe_suppress_detections(
        detections,
        sidelobe_radius_voxels=sidelobe_radius_voxels,
        sidelobe_floor_ratio=sidelobe_floor_ratio,
    )
    kept.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return kept


def refine_detections_watershed(
    detections: list[Detection], 
    volume: np.ndarray, 
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM
) -> list[Detection]:
    """
    Refines CFAR detection coordinates using global marker-based watershed segmentation.
    
    CFAR is excellent at detecting peaks (sensitivity), but the raw intensity peak
    is structurally biased in Z due to PSF artifacts. This function:
    1. Thresholds the volume globally (normalized >= 0.65) to find all biological blobs.
    2. Uses the CFAR peaks as markers to watershed-segment the global mask, resolving dense clusters.
    3. Snaps each CFAR peak's coordinate to the unweighted geometric centroid of its watershed region.
    4. Leaves any CFAR peak that falls outside the global mask exactly as-is (preserving dim cell detections).
    """
    if not detections:
        return []

    try:
        from scipy import ndimage
        from skimage.segmentation import watershed
    except ImportError as exc:
        raise RuntimeError("scipy and skimage are required for watershed refinement") from exc

    norm_vol = robust_normalize(volume)
    global_mask = norm_vol >= 0.65
    
    Z_MAX, Y_MAX, X_MAX = global_mask.shape

    # 1. Place CFAR markers
    markers = np.zeros(global_mask.shape, dtype=np.int32)
    for i, d in enumerate(detections, start=1):
        z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
        z = max(0, min(z, Z_MAX - 1))
        y = max(0, min(y, Y_MAX - 1))
        x = max(0, min(x, X_MAX - 1))
        markers[z, y, x] = i

    # 2. Watershed
    # Basin is inverted raw intensity to find topological boundaries between peaks inside the mask
    labeled_cells = watershed(image=-norm_vol, markers=markers, mask=global_mask)
    
    unique_labels = np.unique(labeled_cells)
    unique_labels = unique_labels[unique_labels > 0]
    
    centroids_by_label = {}
    if len(unique_labels) > 0:
        # returns a list of tuples in the same order as unique_labels
        centroids = ndimage.center_of_mass(global_mask, labeled_cells, unique_labels)
        for label_id, centroid in zip(unique_labels, centroids):
            centroids_by_label[label_id] = centroid
            
    # 3. Refine detections
    refined = []
    for i, d in enumerate(detections, start=1):
        z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
        z = max(0, min(z, Z_MAX - 1))
        y = max(0, min(y, Y_MAX - 1))
        x = max(0, min(x, X_MAX - 1))
        
        label_id = labeled_cells[z, y, x]
        if label_id > 0 and label_id in centroids_by_label:
            # Snap to global watershed centroid
            cz, cy, cx = centroids_by_label[label_id]
            cz_um, cy_um, cx_um = voxel_scale.voxel_to_um(float(cz), float(cy), float(cx))
            refined.append(
                replace(
                    d,
                    z=float(cz),
                    y=float(cy),
                    x=float(cx),
                    z_um=float(cz_um),
                    y_um=float(cy_um),
                    x_um=float(cx_um)
                )
            )
        else:
            # Explicit fallback: if outside global mask, keep as-is
            refined.append(d)
            
    return refined


def threshold_local_maxima_cfar_watershed(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 7, 7),
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    cfar_k_sigma: float = 1.0,
) -> list[Detection]:
    """CFAR detections with Watershed-based sub-voxel centroid refinement."""
    
    detections = threshold_local_maxima_cfar(
        sample_id=sample_id,
        t=t,
        volume=volume,
        threshold=threshold,
        min_distance_voxels=min_distance_voxels,
        max_detections=max_detections,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
        cfar_k_sigma=cfar_k_sigma,
    )
    
    if not detections:
        return []
        
    refined = refine_detections_watershed(detections, volume, voxel_scale)
    refined.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return refined


def threshold_local_maxima_cfar_sidelobe_watershed(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 7, 7),
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    cfar_k_sigma: float = 1.0,
    sidelobe_radius_voxels: tuple[int, int, int] = (0, 2, 2),
    sidelobe_floor_ratio: float = 0.85,
) -> list[Detection]:
    """CFAR detections with Watershed centroid refinement, followed by sidelobe suppression."""
    
    detections = threshold_local_maxima_cfar_watershed(
        sample_id=sample_id,
        t=t,
        volume=volume,
        threshold=threshold,
        min_distance_voxels=min_distance_voxels,
        max_detections=max_detections,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
        cfar_k_sigma=cfar_k_sigma,
    )
    
    if not detections:
        return []

    kept = _sidelobe_suppress_detections(
        detections,
        sidelobe_radius_voxels=sidelobe_radius_voxels,
        sidelobe_floor_ratio=sidelobe_floor_ratio,
    )

    kept.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return kept


def _cfar_background_stats_box(normalized, cfar_training_radius_voxels, cfar_guard_radius_voxels):
    from scipy import ndimage

    tz, ty, tx = (max(0, int(v)) for v in cfar_training_radius_voxels)
    gz, gy, gx = (max(0, int(v)) for v in cfar_guard_radius_voxels)
    if gz > tz or gy > ty or gx > tx:
        raise ValueError("CFAR guard radius must not exceed training radius")

    training_size = (2 * tz + 1, 2 * ty + 1, 2 * tx + 1)
    guard_size = (2 * gz + 1, 2 * gy + 1, 2 * gx + 1)
    training_count = float(np.prod(training_size))
    guard_count = float(np.prod(guard_size))
    ring_count = training_count - guard_count
    if ring_count <= 0.0:
        raise ValueError("CFAR ring must contain at least one training voxel")

    signal = normalized.astype(np.float32, copy=False)
    signal_sq = signal * signal
    mean_training = ndimage.uniform_filter(signal, size=training_size, mode="nearest")
    mean_guard = ndimage.uniform_filter(signal, size=guard_size, mode="nearest")
    mean_sq_training = ndimage.uniform_filter(signal_sq, size=training_size, mode="nearest")
    mean_sq_guard = ndimage.uniform_filter(signal_sq, size=guard_size, mode="nearest")

    sum_training = mean_training * training_count
    sum_guard = mean_guard * guard_count
    sum_sq_training = mean_sq_training * training_count
    sum_sq_guard = mean_sq_guard * guard_count
    background_mean = (sum_training - sum_guard) / ring_count
    background_sq_mean = (sum_sq_training - sum_sq_guard) / ring_count
    background_var = np.clip(background_sq_mean - background_mean * background_mean, 0.0, None)
    return background_mean, np.sqrt(background_var)


def _sidelobe_suppress_detections(detections, sidelobe_radius_voxels, sidelobe_floor_ratio):
    ordered = sorted(detections, key=lambda detection: float(detection.detection_confidence or 0.0), reverse=True)
    kept = []
    rz, ry, rx = (max(0, int(v)) for v in sidelobe_radius_voxels)
    floor_ratio = float(np.clip(sidelobe_floor_ratio, 0.0, 1.0))
    kept_by_voxel = {}
    for detection in ordered:
        confidence = float(detection.detection_confidence or 0.0)
        z0, y0, x0 = int(round(detection.z)), int(round(detection.y)), int(round(detection.x))
        suppressed = False
        for z in range(z0 - rz, z0 + rz + 1):
            for y in range(y0 - ry, y0 + ry + 1):
                for x in range(x0 - rx, x0 + rx + 1):
                    for stronger in kept_by_voxel.get((z, y, x), []):
                        stronger_confidence = float(stronger.detection_confidence or 0.0)
                        if confidence >= stronger_confidence * floor_ratio:
                            continue
                        if (
                            abs(detection.z - stronger.z) <= rz
                            and abs(detection.y - stronger.y) <= ry
                            and abs(detection.x - stronger.x) <= rx
                        ):
                            suppressed = True
                            break
                    if suppressed:
                        break
                if suppressed:
                    break
            if suppressed:
                break
        if suppressed:
            continue
        kept.append(detection)
        kept_by_voxel.setdefault((z0, y0, x0), []).append(detection)
    return kept


def _cfar_margin_confidence(signal, adaptive_threshold):
    denominator = max(adaptive_threshold, 1e-6)
    return max(0.0, (signal - adaptive_threshold) / denominator)


def _edge(source, target, distance, max_link_distance_um):
    confidence = max(0.0, 1.0 - distance / max_link_distance_um)
    return LineageEdge(source.node_id, target.node_id, confidence=confidence)


def _greedy_assign(candidate_pairs, max_link_distance_um):
    candidate_pairs.sort(key=lambda item: item[0])
    used_sources = set()
    used_targets = set()
    edges = []
    for distance, source, target in candidate_pairs:
        if source.node_id in used_sources or target.node_id in used_targets:
            continue
        used_sources.add(source.node_id)
        used_targets.add(target.node_id)
        edges.append(_edge(source, target, distance, max_link_distance_um))
    return edges


def _predicted_position(source, predecessor):
    source_position = np.array(source.position_um, dtype=float)
    if predecessor is None:
        return source_position
    predecessor_position = np.array(predecessor.position_um, dtype=float)
    return source_position + (source_position - predecessor_position)


def _distance_um(source, target):
    return float(np.linalg.norm(np.array(source.position_um) - np.array(target.position_um)))


def _division_assign(candidate_pairs, max_link_distance_um, used_targets):
    candidate_pairs.sort(key=lambda item: item[0])
    used_sources = set()
    edges = []
    for distance, source, target in candidate_pairs:
        if source.node_id in used_sources or target.node_id in used_targets:
            continue
        used_sources.add(source.node_id)
        used_targets.add(target.node_id)
        confidence = max(0.0, 1.0 - distance / max_link_distance_um)
        edges.append(LineageEdge(source.node_id, target.node_id, confidence=confidence, relation="division"))
    return edges


def _append_division_candidate(candidate_pairs, source, target, distance, source_to_primary_target,
                               source_to_primary_distance, current_by_id, daughter_distance_ratio,
                               separation_limit):
    primary_target_id = source_to_primary_target.get(source.node_id)
    if primary_target_id is None:
        return
    primary_target = current_by_id[primary_target_id]
    primary_distance = source_to_primary_distance[source.node_id]
    if distance > max(primary_distance, 1e-6) * daughter_distance_ratio:
        return
    if _distance_um(primary_target, target) > separation_limit:
        return
    candidate_pairs.append((distance, source, target))


def link_adjacent_timepoints_motion(previous, current, max_link_distance_um, predecessor_by_node_id=None):
    if not previous or not current:
        return []
    predecessor_by_node_id = predecessor_by_node_id or {}
    current_positions = np.array([d.position_um for d in current], dtype=float)
    candidate_pairs = []

    from scipy.spatial import cKDTree

    tree = cKDTree(current_positions)
    for source in previous:
        source_position = np.array(source.position_um, dtype=float)
        query_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
        distance, idx = tree.query(query_position, k=1)
        target = current[int(idx)]
        step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
        if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um and step_distance <= max_link_distance_um:
            candidate_pairs.append((float(distance), source, target))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


def link_adjacent_timepoints_motion_division(previous, current, max_link_distance_um, predecessor_by_node_id=None,
                                             daughter_distance_ratio=1.75, max_daughter_separation_um=None):
    continuation_edges = link_adjacent_timepoints_motion(
        previous,
        current,
        max_link_distance_um,
        predecessor_by_node_id=predecessor_by_node_id,
    )
    if not continuation_edges:
        return []

    previous_by_id = {detection.node_id: detection for detection in previous}
    current_by_id = {detection.node_id: detection for detection in current}
    source_to_primary_target = {edge.source_id: edge.target_id for edge in continuation_edges}
    used_targets = {edge.target_id for edge in continuation_edges}
    source_to_primary_distance = {
        edge.source_id: _distance_um(previous_by_id[edge.source_id], current_by_id[edge.target_id])
        for edge in continuation_edges
    }
    separation_limit = max_daughter_separation_um or max_link_distance_um
    previous_positions = np.array([detection.position_um for detection in previous], dtype=float)
    candidate_pairs = []

    from scipy.spatial import cKDTree

    previous_tree = cKDTree(previous_positions)
    for target in current:
        if target.node_id in used_targets:
            continue
        distance, source_idx = previous_tree.query(target.position_um, k=1)
        if not math.isfinite(float(distance)) or float(distance) > max_link_distance_um:
            continue
        source = previous[int(source_idx)]
        _append_division_candidate(
            candidate_pairs,
            source,
            target,
            float(distance),
            source_to_primary_target,
            source_to_primary_distance,
            current_by_id,
            daughter_distance_ratio,
            separation_limit,
        )
    return continuation_edges + _division_assign(candidate_pairs, max_link_distance_um, used_targets)


def link_adjacent_timepoints_motion_mutual(previous, current, max_link_distance_um, predecessor_by_node_id=None):
    if not previous or not current:
        return []
    predecessor_by_node_id = predecessor_by_node_id or {}
    previous_positions = np.array([d.position_um for d in previous], dtype=float)
    current_positions = np.array([d.position_um for d in current], dtype=float)

    source_to_target = {}
    target_to_source = {}

    from scipy.spatial import cKDTree

    current_tree = cKDTree(current_positions)
    previous_tree = cKDTree(previous_positions)
    for source_idx, source in enumerate(previous):
        source_position = np.array(source.position_um, dtype=float)
        predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
        prediction_error, target_idx = current_tree.query(predicted_position, k=1)
        target = current[int(target_idx)]
        step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
        if (
            math.isfinite(float(prediction_error))
            and float(prediction_error) <= max_link_distance_um
            and step_distance <= max_link_distance_um
        ):
            source_to_target[source_idx] = (int(target_idx), float(prediction_error))
    for target_idx, target in enumerate(current):
        distance, source_idx = previous_tree.query(target.position_um, k=1)
        if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
            target_to_source[target_idx] = int(source_idx)

    candidate_pairs = []
    for source_idx, (target_idx, prediction_error) in source_to_target.items():
        if target_to_source.get(target_idx) != source_idx:
            continue
        candidate_pairs.append((prediction_error, previous[source_idx], current[target_idx]))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


def link_adjacent_timepoints_motion_crowding(previous, current, max_link_distance_um, predecessor_by_node_id=None,
                                             crowding_ratio=0.8):
    if not previous or not current:
        return []
    predecessor_by_node_id = predecessor_by_node_id or {}
    previous_positions = np.array([d.position_um for d in previous], dtype=float)
    current_positions = np.array([d.position_um for d in current], dtype=float)

    source_to_target = {}
    target_to_source = {}
    target_contested = {}

    from scipy.spatial import cKDTree

    current_tree = cKDTree(current_positions)
    previous_tree = cKDTree(previous_positions)
    for source_idx, source in enumerate(previous):
        source_position = np.array(source.position_um, dtype=float)
        predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
        prediction_error, target_idx = current_tree.query(predicted_position, k=1)
        target = current[int(target_idx)]
        step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
        if (
            math.isfinite(float(prediction_error))
            and float(prediction_error) <= max_link_distance_um
            and step_distance <= max_link_distance_um
        ):
            source_to_target[source_idx] = (int(target_idx), float(prediction_error))
    neighbor_count = min(2, len(previous))
    for target_idx, target in enumerate(current):
        distances, source_indices = previous_tree.query(target.position_um, k=neighbor_count)
        distances = np.atleast_1d(distances)
        source_indices = np.atleast_1d(source_indices)
        nearest_distance = float(distances[0])
        if not math.isfinite(nearest_distance) or nearest_distance > max_link_distance_um:
            continue
        second_distance = float(distances[1]) if distances.size > 1 else math.inf
        target_to_source[target_idx] = int(source_indices[0])
        target_contested[target_idx] = _is_contested(nearest_distance, second_distance, crowding_ratio)

    candidate_pairs = []
    for source_idx, (target_idx, prediction_error) in source_to_target.items():
        if target_contested.get(target_idx, False) and target_to_source.get(target_idx) != source_idx:
            continue
        candidate_pairs.append((prediction_error, previous[source_idx], current[target_idx]))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


def _is_contested(nearest_distance, second_distance, crowding_ratio):
    if not math.isfinite(second_distance) or second_distance <= 0.0:
        return False
    return (nearest_distance / second_distance) > crowding_ratio


def link_adjacent_timepoints(previous, current, max_link_distance_um, strategy="greedy", predecessor_by_node_id=None):
    if strategy == "motion":
        return link_adjacent_timepoints_motion(previous, current, max_link_distance_um, predecessor_by_node_id)
    if strategy == "motion_division":
        return link_adjacent_timepoints_motion_division(previous, current, max_link_distance_um, predecessor_by_node_id)
    if strategy == "motion_mutual":
        return link_adjacent_timepoints_motion_mutual(previous, current, max_link_distance_um, predecessor_by_node_id)
    if strategy == "motion_mutual_latent":
        # Latent gap-bridging is handled by build_baseline_graph where time context exists.
        return link_adjacent_timepoints_motion_mutual(previous, current, max_link_distance_um, predecessor_by_node_id)
    if strategy == "motion_crowding":
        return link_adjacent_timepoints_motion_crowding(previous, current, max_link_distance_um, predecessor_by_node_id)

    if not previous or not current:
        return []
    current_positions = np.array([d.position_um for d in current], dtype=float)
    candidate_pairs = []

    from scipy.spatial import cKDTree

    tree = cKDTree(current_positions)
    for source in previous:
        distance, idx = tree.query(source.position_um, k=1)
        if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
            candidate_pairs.append((float(distance), source, current[int(idx)]))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


def _recover_latent_edges(latent_tracks, current, used_target_ids, max_link_distance_um, latent_window_frames):
    if not latent_tracks:
        return [], set()

    available_targets = [detection for detection in current if detection.node_id not in used_target_ids]
    if not available_targets:
        return [], set()

    target_positions = np.array([detection.position_um for detection in available_targets], dtype=float)
    candidate_pairs = []
    for source_id, latent in latent_tracks.items():
        missing_frames = int(latent["missing_frames"])
        if missing_frames < 1 or missing_frames > latent_window_frames:
            continue

        source = latent["source"]
        predecessor = latent["predecessor"]
        source_position = np.array(source.position_um, dtype=float)
        predicted_position = source_position
        if predecessor is not None:
            predecessor_position = np.array(predecessor.position_um, dtype=float)
            velocity = source_position - predecessor_position
            predicted_position = source_position + velocity * float(missing_frames + 1)

        prediction_errors = np.linalg.norm(target_positions - predicted_position, axis=1)
        best_idx = int(np.argmin(prediction_errors))
        target = available_targets[best_idx]
        prediction_error = float(prediction_errors[best_idx])
        step_distance = float(np.linalg.norm(np.array(target.position_um, dtype=float) - source_position))
        if prediction_error > max_link_distance_um:
            continue
        if step_distance > max_link_distance_um * float(missing_frames + 1):
            continue
        candidate_pairs.append((prediction_error, source_id, target.node_id))

    candidate_pairs.sort(key=lambda item: item[0])
    recovered_source_ids = set()
    assigned_target_ids = set()
    recovered_edges = []
    for prediction_error, source_id, target_id in candidate_pairs:
        if source_id in recovered_source_ids or target_id in used_target_ids or target_id in assigned_target_ids:
            continue
        confidence = max(0.0, 1.0 - prediction_error / max_link_distance_um)
        recovered_edges.append(
            LineageEdge(source_id=source_id, target_id=target_id, confidence=confidence, relation="latent_recovery")
        )
        recovered_source_ids.add(source_id)
        assigned_target_ids.add(target_id)
    return recovered_edges, recovered_source_ids


def _age_and_prune_latent_tracks(latent_tracks, recovered_source_ids, latent_window_frames):
    for source_id in recovered_source_ids:
        latent_tracks.pop(source_id, None)
    for source_id, latent in list(latent_tracks.items()):
        latent["missing_frames"] = int(latent["missing_frames"]) + 1
        if int(latent["missing_frames"]) > latent_window_frames:
            del latent_tracks[source_id]


def _enqueue_new_latent_tracks(latent_tracks, previous, matched_source_ids, predecessor_by_node_id,
                               track_length_by_node_id, min_latent_track_length_edges):
    for source in previous:
        if source.node_id in matched_source_ids:
            continue
        predecessor = predecessor_by_node_id.get(source.node_id)
        if predecessor is None:
            continue
        if int(track_length_by_node_id.get(source.node_id, 0)) < int(min_latent_track_length_edges):
            continue
        latent_tracks[source.node_id] = {
            "source": source,
            "predecessor": predecessor,
            "missing_frames": 1,
        }


def build_baseline_graph(sample_path, max_timepoints=None, threshold=0.65, min_volume=4, max_link_distance_um=7.0,
                         link_strategy="greedy", detector="components", peak_min_distance_voxels=(1, 3, 3)):
    dataset = sample_id_from_zarr_path(sample_path)
    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))

    graph = LineageGraph(sample_id=dataset)
    previous = []
    detections_by_node_id = {}
    predecessor_by_node_id = {}
    latent_enabled = link_strategy == "motion_mutual_latent"
    adjacent_strategy = "motion_mutual" if latent_enabled else link_strategy
    latent_window_frames = 1
    min_latent_track_length_edges = 2
    latent_tracks = {}
    track_length_by_node_id = {}
    for t in range(total_timepoints):
        volume = read_timepoint(array, t)
        if detector == "components":
            current = threshold_connected_components(dataset, t, volume, threshold=threshold, min_volume=min_volume)
        elif detector == "local_maxima":
            current = threshold_local_maxima(dataset, t, volume, threshold=threshold, min_distance_voxels=peak_min_distance_voxels)
        else:
            raise ValueError(f"Unknown detector: {detector}")

        for detection in current:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection

        adjacent_edges = link_adjacent_timepoints(previous, current, max_link_distance_um, strategy=adjacent_strategy,
                                                  predecessor_by_node_id=predecessor_by_node_id)
        for edge in adjacent_edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
            track_length_by_node_id[edge.target_id] = int(track_length_by_node_id.get(edge.source_id, 0)) + 1

        if latent_enabled:
            matched_source_ids = {edge.source_id for edge in adjacent_edges}
            used_target_ids = {edge.target_id for edge in adjacent_edges}
            latent_edges, recovered_source_ids = _recover_latent_edges(
                latent_tracks,
                current,
                used_target_ids,
                max_link_distance_um,
                latent_window_frames,
            )
            for edge in latent_edges:
                graph.add_edge(edge)
                predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
                track_length_by_node_id[edge.target_id] = int(track_length_by_node_id.get(edge.source_id, 0)) + 1

            _age_and_prune_latent_tracks(latent_tracks, recovered_source_ids, latent_window_frames)
            _enqueue_new_latent_tracks(latent_tracks, previous, matched_source_ids, predecessor_by_node_id,
                                       track_length_by_node_id, min_latent_track_length_edges)
        previous = current
    return graph


def build_graph_cfar_sidelobe(sample_path, max_timepoints=None, threshold=0.50, min_volume=2,
                              max_link_distance_um=9.0, peak_min_distance_voxels=(1, 5, 5),
                              max_detections_per_timepoint=900,
                              cfar_training_radius_voxels=(1, 6, 6),
                              cfar_guard_radius_voxels=(0, 1, 1), cfar_k_sigma=1.1,
                              sidelobe_radius_voxels=(1, 12, 12), sidelobe_floor_ratio=0.85,
                              guardrail_spike_multiplier=DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier,
                              guardrail_min_history=DEFAULT_GUARDRAIL_SETTINGS.min_history,
                              guardrail_history_window=DEFAULT_GUARDRAIL_SETTINGS.history_window,
                              guardrail_min_absolute_count=DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count,
                              guardrail_fallback_threshold=DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold,
                              guardrail_fallback_max_detections=None):
    dataset = sample_id_from_zarr_path(sample_path)
    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))

    graph = LineageGraph(sample_id=dataset)
    previous = []
    detections_by_node_id = {}
    predecessor_by_node_id = {}
    recent_counts = []
    spike_fallback_count = 0
    if guardrail_fallback_max_detections is None:
        guardrail_fallback_max_detections = max_detections_per_timepoint
    for t in range(total_timepoints):
        volume = read_timepoint(array, t)
        current = threshold_local_maxima_cfar_sidelobe_watershed(
            dataset,
            t,
            volume,
            threshold=threshold,
            min_distance_voxels=peak_min_distance_voxels,
            max_detections=max_detections_per_timepoint,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_k_sigma=cfar_k_sigma,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
        )

        use_guardrail = False
        if len(recent_counts) >= int(guardrail_min_history):
            recent_window = recent_counts[-int(guardrail_history_window):]
            baseline_count = float(median(recent_window))
            spike_limit = max(
                int(guardrail_min_absolute_count),
                int(round(baseline_count * float(guardrail_spike_multiplier))),
            )
            use_guardrail = len(current) > spike_limit

        if use_guardrail:
            current = threshold_local_maxima(
                dataset,
                t,
                volume,
                threshold=guardrail_fallback_threshold,
                min_distance_voxels=(1, 5, 5),
                max_detections=guardrail_fallback_max_detections,
            )
            spike_fallback_count += 1

        recent_counts.append(len(current))
        for detection in current:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection

        edges = link_adjacent_timepoints(
            previous,
            current,
            max_link_distance_um,
            strategy="motion_mutual",
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
        previous = current
    return graph, spike_fallback_count


def _is_profile_6bba_like_for_cfar(profile):
    return (
        profile.median_largest_component_voxels >= 100_000
        and profile.median_largest_component_voxels <= 600_000
        and profile.median_foreground_fraction >= 0.05
        and profile.median_foreground_fraction <= 0.20
    )


def _use_cfar_route(profile, settings):
    if settings.detector != "local_maxima":
        return False
    return _is_profile_6bba_like_for_cfar(profile)


def _default_timepoints(total_timepoints):
    if total_timepoints <= 1:
        return (0,)
    anchors = [0, total_timepoints // 4, total_timepoints // 2, (3 * total_timepoints) // 4, total_timepoints - 1]
    return tuple(dict.fromkeys(anchors))


def profile_sample_foreground(sample_path, threshold=0.65, min_volume=2, sample_timepoints=None):
    from scipy import ndimage

    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    timepoints = sample_timepoints or _default_timepoints(total_timepoints)
    largest_components = []
    foreground_fractions = []
    component_counts = []
    kept_component_counts = []

    for t in timepoints:
        volume = read_timepoint(array, min(max(0, int(t)), total_timepoints - 1))
        normalized = robust_normalize(volume)
        mask = normalized >= threshold
        labels, component_count = ndimage.label(mask)
        counts = np.bincount(labels.ravel())[1:]
        largest_components.append(int(counts.max()) if counts.size else 0)
        foreground_fractions.append(float(mask.mean()))
        component_counts.append(int(component_count))
        kept_component_counts.append(int((counts >= min_volume).sum()) if counts.size else 0)

    return ForegroundProfile(
        sampled_timepoints=tuple(timepoints),
        median_largest_component_voxels=float(median(largest_components)),
        median_foreground_fraction=float(median(foreground_fractions)),
        median_component_count=float(median(component_counts)),
        median_kept_component_count=float(median(kept_component_counts)),
    )


def choose_adaptive_baseline_settings(profile, merged_component_voxels=100000, merged_foreground_fraction=0.05):
    if profile.median_largest_component_voxels >= merged_component_voxels or profile.median_foreground_fraction >= merged_foreground_fraction:
        return AdaptiveBaselineSettings(
            detector="local_maxima", threshold=0.65, min_volume=2, peak_min_distance_voxels=(1, 5, 5),
            link_strategy="motion_mutual_latent", max_link_distance_um=9.0,
            reason="merged foreground profile: large thresholded components or high foreground fraction, so use local maxima and strict motion+mutual linking with a bounded one-frame latent recovery bridge",
        )
    return AdaptiveBaselineSettings(
        detector="components", threshold=0.65, min_volume=2, peak_min_distance_voxels=(1, 5, 5),
        link_strategy="greedy", max_link_distance_um=7.0,
        reason="clean foreground profile: thresholded components are compact enough for component centroids and simple greedy linking",
    )


def choose_settings_for_sample(sample_path):
    profile = profile_sample_foreground(sample_path)
    return profile, choose_adaptive_baseline_settings(profile)


def discover_zarr_samples(input_dir):
    root = Path(input_dir)
    return sorted((path for path in root.iterdir() if path.is_dir() and path.name.endswith(".zarr")), key=lambda path: path.name)


def write_graph_rows(writer, graph, next_id):
    node_export_ids = {detection.node_id: idx + 1 for idx, detection in enumerate(graph.detections)}
    for detection in graph.detections:
        writer.writerow({
            "id": next_id,
            "dataset": graph.sample_id,
            "row_type": "node",
            "node_id": node_export_ids[detection.node_id],
            "t": int(detection.t),
            "z": int(round(detection.z)),
            "y": int(round(detection.y)),
            "x": int(round(detection.x)),
            "source_id": -1,
            "target_id": -1,
        })
        next_id += 1
    for edge in graph.edges:
        writer.writerow({
            "id": next_id,
            "dataset": graph.sample_id,
            "row_type": "edge",
            "node_id": -1,
            "t": -1,
            "z": -1,
            "y": -1,
            "x": -1,
            "source_id": node_export_ids[edge.source_id],
            "target_id": node_export_ids[edge.target_id],
        })
        next_id += 1
    return next_id


def parse_optional_int(name):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _contains_zarr_samples(path):
    return path.exists() and any(child.is_dir() and child.name.endswith(".zarr") for child in path.iterdir())


def default_input_dir():
    candidates = [
        Path("/kaggle/input/biohub-cell-tracking-during-development/test"),
        Path("/kaggle/input/biohub-cell-tracking-during-development"),
        Path("/kaggle/input/competitions/biohub-cell-tracking-during-development/test"),
        Path("/kaggle/input/competitions/biohub-cell-tracking-during-development"),
    ]
    input_root = Path("/kaggle/input")
    if input_root.exists():
        for child in sorted(input_root.iterdir(), key=lambda item: item.name):
            if child.is_dir():
                candidates.append(child / "test")
                candidates.append(child)
    candidates.append(Path("D:/Project-Atabey/test"))

    for candidate in candidates:
        if _contains_zarr_samples(candidate):
            return candidate

    available = []
    if input_root.exists():
        available = [str(path) for path in sorted(input_root.glob("**/*"))[:100]]
    raise FileNotFoundError(
        "Could not find .zarr samples under known Kaggle input paths. "
        f"Checked: {[str(candidate) for candidate in candidates]}. "
        f"Available input entries: {available}"
    )


def main():
    input_dir = Path(os.environ.get("ATABEY_INPUT_DIR", str(default_input_dir())))
    output_csv = Path(os.environ.get("ATABEY_OUTPUT_CSV", "/kaggle/working/submission.csv"))
    report_json = Path(os.environ.get("ATABEY_REPORT_JSON", "/kaggle/working/adaptive_runtime_report.json"))
    max_samples = parse_optional_int("ATABEY_MAX_SAMPLES")
    max_timepoints = parse_optional_int("ATABEY_MAX_TIMEPOINTS")

    sample_paths = discover_zarr_samples(input_dir)
    if max_samples is not None:
        sample_paths = sample_paths[:max_samples]
    if not sample_paths:
        raise FileNotFoundError(f"No .zarr samples found in {input_dir}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    records = []
    columns = ["id", "dataset", "row_type", "node_id", "t", "z", "y", "x", "source_id", "target_id"]
    next_id = 0
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for sample_path in sample_paths:
            profile, settings = choose_settings_for_sample(sample_path)
            use_cfar_route = _use_cfar_route(profile, settings)
            start = time.perf_counter()
            if use_cfar_route:
                route = "cfar_sidelobe"
                graph, cfar_spike_fallback_count = build_graph_cfar_sidelobe(
                    sample_path,
                    max_timepoints=max_timepoints,
                )
                detector = "cfar_sidelobe"
                threshold = 0.50
                link_strategy = "motion_mutual"
                max_link_distance_um = 9.0
                cfar_training_radius_voxels = (1, 6, 6)
                cfar_guard_radius_voxels = (0, 1, 1)
                cfar_k_sigma = 1.1
                sidelobe_radius_voxels = (1, 12, 12)
                sidelobe_floor_ratio = 0.85
                max_detections_per_timepoint = 900
            else:
                route = "v9_style_adaptive" if settings.detector == "local_maxima" else "adaptive_baseline"
                link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
                max_link_distance_um = settings.max_link_distance_um
                graph = build_baseline_graph(
                    sample_path,
                    max_timepoints=max_timepoints,
                    threshold=settings.threshold,
                    min_volume=settings.min_volume,
                    max_link_distance_um=max_link_distance_um,
                    link_strategy=link_strategy,
                    detector=settings.detector,
                    peak_min_distance_voxels=settings.peak_min_distance_voxels,
                )
                detector = settings.detector
                threshold = settings.threshold
                cfar_training_radius_voxels = None
                cfar_guard_radius_voxels = None
                cfar_k_sigma = None
                sidelobe_radius_voxels = None
                sidelobe_floor_ratio = None
                max_detections_per_timepoint = None
                cfar_spike_fallback_count = None
            elapsed = time.perf_counter() - start
            record = SampleRunRecord(
                sample_id=graph.sample_id,
                sample_path=str(sample_path),
                route=route,
                elapsed_seconds=round(elapsed, 2),
                predicted_nodes=len(graph.detections),
                predicted_edges=len(graph.edges),
                detector=detector,
                threshold=threshold,
                min_volume=settings.min_volume,
                peak_min_distance_voxels=settings.peak_min_distance_voxels,
                link_strategy=link_strategy,
                max_link_distance_um=max_link_distance_um,
                median_largest_component_voxels=profile.median_largest_component_voxels,
                median_foreground_fraction=profile.median_foreground_fraction,
                reason=settings.reason,
                cfar_training_radius_voxels=cfar_training_radius_voxels,
                cfar_guard_radius_voxels=cfar_guard_radius_voxels,
                cfar_k_sigma=cfar_k_sigma,
                sidelobe_radius_voxels=sidelobe_radius_voxels,
                sidelobe_floor_ratio=sidelobe_floor_ratio,
                max_detections_per_timepoint=max_detections_per_timepoint,
                cfar_spike_fallback_count=cfar_spike_fallback_count,
                max_timepoints=max_timepoints,
            )
            records.append(record)
            next_id = write_graph_rows(writer, graph, next_id)
            print(json.dumps(asdict(record)), flush=True)

    report_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")
    print(json.dumps({"submission_csv": str(output_csv), "report_json": str(report_json), "rows": next_id}), flush=True)


if __name__ == "__main__":
    main()