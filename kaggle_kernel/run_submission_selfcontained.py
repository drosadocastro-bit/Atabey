import csv
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
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


def robust_normalize(volume, lower=1.0, upper=99.5):
    low, high = np.percentile(volume, [lower, upper])
    if high <= low:
        return np.zeros_like(volume, dtype=np.float32)
    normalized = (volume.astype(np.float32) - low) / (high - low)
    return np.clip(normalized, 0.0, 1.0)


def open_competition_array(sample_path):
    import zarr

    array_path = Path(sample_path) / "0"
    if not array_path.exists():
        raise FileNotFoundError(f"Expected competition array at {array_path}")
    return zarr.open(str(array_path), mode="r")


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


def link_adjacent_timepoints(previous, current, max_link_distance_um, strategy="greedy", predecessor_by_node_id=None):
    if not previous or not current:
        return []
    predecessor_by_node_id = predecessor_by_node_id or {}
    current_positions = np.array([d.position_um for d in current], dtype=float)
    candidate_pairs = []

    from scipy.spatial import cKDTree

    tree = cKDTree(current_positions)
    for source in previous:
        source_position = np.array(source.position_um, dtype=float)
        query_position = source_position
        if strategy == "motion":
            query_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
        distance, idx = tree.query(query_position, k=1)
        target = current[int(idx)]
        step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
        if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um and step_distance <= max_link_distance_um:
            candidate_pairs.append((float(distance), source, target))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


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
        for edge in link_adjacent_timepoints(previous, current, max_link_distance_um, strategy=link_strategy,
                                             predecessor_by_node_id=predecessor_by_node_id):
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
        previous = current
    return graph


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
            link_strategy="motion", max_link_distance_um=9.0,
            reason="merged foreground profile: large thresholded components or high foreground fraction, so use local maxima and motion linking",
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
            start = time.perf_counter()
            graph = build_baseline_graph(
                sample_path,
                max_timepoints=max_timepoints,
                threshold=settings.threshold,
                min_volume=settings.min_volume,
                max_link_distance_um=settings.max_link_distance_um,
                link_strategy=settings.link_strategy,
                detector=settings.detector,
                peak_min_distance_voxels=settings.peak_min_distance_voxels,
            )
            elapsed = time.perf_counter() - start
            record = SampleRunRecord(
                sample_id=graph.sample_id,
                sample_path=str(sample_path),
                elapsed_seconds=round(elapsed, 2),
                predicted_nodes=len(graph.detections),
                predicted_edges=len(graph.edges),
                detector=settings.detector,
                threshold=settings.threshold,
                min_volume=settings.min_volume,
                peak_min_distance_voxels=settings.peak_min_distance_voxels,
                link_strategy=settings.link_strategy,
                max_link_distance_um=settings.max_link_distance_um,
                median_largest_component_voxels=profile.median_largest_component_voxels,
                median_foreground_fraction=profile.median_foreground_fraction,
                reason=settings.reason,
            )
            records.append(record)
            next_id = write_graph_rows(writer, graph, next_id)
            print(json.dumps(asdict(record)), flush=True)

    report_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")
    print(json.dumps({"submission_csv": str(output_csv), "report_json": str(report_json), "rows": next_id}), flush=True)


if __name__ == "__main__":
    main()