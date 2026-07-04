from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atabey.constants import DEFAULT_VOXEL_SCALE_UM, VoxelScale


@dataclass(frozen=True)
class GroundTruthNode:
    node_id: int
    t: int
    z: int
    y: int
    x: int
    z_um: float
    y_um: float
    x_um: float

    @property
    def position_um(self) -> tuple[float, float, float]:
        return self.z_um, self.y_um, self.x_um


@dataclass(frozen=True)
class SparseGroundTruthGraph:
    sample_id: str
    nodes: list[GroundTruthNode]
    edges: list[tuple[int, int]]
    estimated_number_of_nodes: int | None

    def positions_um_at_time(self, t: int) -> list[tuple[float, float, float]]:
        return [node.position_um for node in self.nodes if node.t == t]


def read_geff_graph(
    path: str | Path,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
) -> SparseGroundTruthGraph:
    """Read the sparse GEFF graph used by the competition training labels."""

    try:
        import zarr
    except ImportError as exc:  # pragma: no cover - exercised when zarr is absent.
        raise RuntimeError("zarr is required to read competition GEFF labels") from exc

    root = Path(path)
    metadata = _read_geff_metadata(root)
    ids = zarr.open(str(root / "nodes" / "ids"), mode="r")[:]
    t_values = zarr.open(str(root / "nodes" / "props" / "t" / "values"), mode="r")[:]
    z_values = zarr.open(str(root / "nodes" / "props" / "z" / "values"), mode="r")[:]
    y_values = zarr.open(str(root / "nodes" / "props" / "y" / "values"), mode="r")[:]
    x_values = zarr.open(str(root / "nodes" / "props" / "x" / "values"), mode="r")[:]
    edge_values = zarr.open(str(root / "edges" / "ids"), mode="r")[:]

    nodes: list[GroundTruthNode] = []
    for node_id, t, z, y, x in zip(ids, t_values, z_values, y_values, x_values, strict=True):
        z_um, y_um, x_um = voxel_scale.voxel_to_um(float(z), float(y), float(x))
        nodes.append(
            GroundTruthNode(
                node_id=int(node_id),
                t=int(t),
                z=int(z),
                y=int(y),
                x=int(x),
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
            )
        )

    edges = [(int(source), int(target)) for source, target in edge_values]
    estimated = metadata.get("extra", {}).get("estimated_number_of_nodes")
    return SparseGroundTruthGraph(
        sample_id=root.name.removesuffix(".geff"),
        nodes=nodes,
        edges=edges,
        estimated_number_of_nodes=int(estimated) if estimated is not None else None,
    )


def _read_geff_metadata(root: Path) -> dict[str, Any]:
    with (root / "zarr.json").open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    return metadata.get("attributes", {}).get("geff", {})
