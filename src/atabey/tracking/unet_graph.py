from __future__ import annotations

from collections.abc import Iterable, Sequence
import math

from atabey.constants import DEFAULT_VOXEL_SCALE_UM, VoxelScale
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageEdge, LineageGraph


NativeEdge = tuple[int, int, float, float]


def detections_from_predictor_coordinates(
    sample_id: str,
    coordinates: Sequence[Sequence[float]],
    *,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
) -> list[Detection]:
    """Convert public predictor `[t,z,y,x]` rows at original resolution."""

    detections: list[Detection] = []
    previous_t = -1
    for index, row in enumerate(coordinates):
        if len(row) != 4:
            raise ValueError(f"Coordinate row {index} must contain [t,z,y,x]")
        t_float, z, y, x = (float(value) for value in row)
        if not all(math.isfinite(value) for value in (t_float, z, y, x)):
            raise ValueError(f"Coordinate row {index} contains a non-finite value")
        t = int(t_float)
        if t_float != float(t) or t < 0:
            raise ValueError(f"Coordinate row {index} has invalid time {t_float}")
        if t < previous_t:
            raise ValueError("Predictor coordinates must be ordered by time")
        if min(z, y, x) < 0:
            raise ValueError(f"Coordinate row {index} contains a negative position")
        z_um, y_um, x_um = voxel_scale.voxel_to_um(z, y, x)
        detections.append(
            Detection(
                node_id=f"unet:{sample_id}:n{index:08d}",
                sample_id=sample_id,
                t=t,
                z=z,
                y=y,
                x=x,
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
            )
        )
        previous_t = t
    return detections


def native_graph_from_predictor_output(
    sample_id: str,
    coordinates: Sequence[Sequence[float]],
    native_edges: Iterable[NativeEdge],
    *,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
) -> LineageGraph:
    detections = detections_from_predictor_coordinates(
        sample_id,
        coordinates,
        voxel_scale=voxel_scale,
    )
    graph = LineageGraph(sample_id=sample_id)
    for detection in detections:
        graph.add_detection(detection)

    seen: set[tuple[int, int]] = set()
    for edge_index, edge in enumerate(native_edges):
        if len(edge) != 4:
            raise ValueError(f"Native edge {edge_index} must contain four values")
        source_index, target_index = int(edge[0]), int(edge[1])
        probability, distance = float(edge[2]), float(edge[3])
        if source_index < 0 or target_index < 0:
            raise ValueError(f"Native edge {edge_index} has a negative node index")
        if source_index >= len(detections) or target_index >= len(detections):
            raise ValueError(f"Native edge {edge_index} references a missing node")
        source = detections[source_index]
        target = detections[target_index]
        if target.t != source.t + 1:
            raise ValueError(f"Native edge {edge_index} is not adjacent in time")
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError(f"Native edge {edge_index} has invalid probability")
        if not math.isfinite(distance) or distance < 0.0:
            raise ValueError(f"Native edge {edge_index} has invalid distance")
        key = (source_index, target_index)
        if key in seen:
            raise ValueError(f"Native edge {edge_index} duplicates {key}")
        seen.add(key)
        graph.add_edge(
            LineageEdge(
                source_id=source.node_id,
                target_id=target.node_id,
                confidence=probability,
                relation="continuation",
            )
        )
    return graph


def relink_predictor_detections(
    sample_id: str,
    coordinates: Sequence[Sequence[float]],
    *,
    max_link_distance_um: float = 9.0,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
) -> LineageGraph:
    """Apply the frozen Atabey motion-mutual linker to predictor detections."""

    if max_link_distance_um <= 0:
        raise ValueError("max_link_distance_um must be positive")
    detections = detections_from_predictor_coordinates(
        sample_id,
        coordinates,
        voxel_scale=voxel_scale,
    )
    graph = LineageGraph(sample_id=sample_id)
    by_time: dict[int, list[Detection]] = {}
    for detection in detections:
        graph.add_detection(detection)
        by_time.setdefault(detection.t, []).append(detection)

    predecessor_by_node_id: dict[str, Detection] = {}
    previous: list[Detection] = []
    last_t = max(by_time, default=-1)
    for t in range(last_t + 1):
        current = by_time.get(t, [])
        edges = link_adjacent_timepoints(
            previous,
            current,
            max_link_distance_um,
            strategy="motion_mutual",
            predecessor_by_node_id=predecessor_by_node_id,
        )
        lookup = {detection.node_id: detection for detection in previous}
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = lookup[edge.source_id]
        previous = current
    return graph


def graph_signature(graph: LineageGraph) -> tuple[tuple[object, ...], tuple[object, ...]]:
    return (
        tuple(
            (node.node_id, node.t, node.z, node.y, node.x)
            for node in graph.detections
        ),
        tuple(
            (edge.source_id, edge.target_id, edge.confidence, edge.relation)
            for edge in graph.edges
        ),
    )
