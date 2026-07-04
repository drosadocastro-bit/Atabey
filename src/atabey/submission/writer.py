from __future__ import annotations

from pathlib import Path

import pandas as pd

from atabey.types import LineageGraph


KAGGLE_SUBMISSION_COLUMNS = [
    "id",
    "dataset",
    "row_type",
    "node_id",
    "t",
    "z",
    "y",
    "x",
    "source_id",
    "target_id",
]


def graph_to_submission_rows(graph: LineageGraph, start_id: int = 0) -> pd.DataFrame:
    """Convert a lineage graph to the official Kaggle submission schema.

    Atabey keeps internal node identifiers as strings so tracking code can carry
    provenance. Kaggle rows receive stable per-dataset integer IDs, and edge
    rows reference those exported IDs.
    """

    node_export_ids = {detection.node_id: idx + 1 for idx, detection in enumerate(graph.detections)}
    rows: list[dict[str, object]] = []
    for idx, detection in enumerate(graph.detections):
        rows.append(
            {
                "id": start_id + idx,
                "dataset": graph.sample_id,
                "row_type": "node",
                "node_id": node_export_ids[detection.node_id],
                "t": int(detection.t),
                "z": int(round(detection.z)),
                "y": int(round(detection.y)),
                "x": int(round(detection.x)),
                "source_id": -1,
                "target_id": -1,
            }
        )

    offset = len(rows)
    for idx, edge in enumerate(graph.edges):
        if edge.source_id not in node_export_ids or edge.target_id not in node_export_ids:
            raise ValueError(
                "Submission edge references a node that is absent from the graph detections."
            )
        rows.append(
            {
                "id": start_id + offset + idx,
                "dataset": graph.sample_id,
                "row_type": "edge",
                "node_id": -1,
                "t": -1,
                "z": -1,
                "y": -1,
                "x": -1,
                "source_id": node_export_ids[edge.source_id],
                "target_id": node_export_ids[edge.target_id],
            }
        )
    return pd.DataFrame(rows, columns=KAGGLE_SUBMISSION_COLUMNS)


def graphs_to_submission_rows(graphs: list[LineageGraph]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    next_id = 0
    for graph in graphs:
        frame = graph_to_submission_rows(graph, start_id=next_id)
        next_id += len(frame)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=KAGGLE_SUBMISSION_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def write_submission(graphs: LineageGraph | list[LineageGraph], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph_list = [graphs] if isinstance(graphs, LineageGraph) else graphs
    graphs_to_submission_rows(graph_list).to_csv(output_path, index=False)
    return output_path


# Backward-compatible names for the initial scaffold tests and notebooks.
graph_to_internal_rows = graph_to_submission_rows
write_internal_submission = write_submission
