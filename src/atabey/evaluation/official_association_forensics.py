from __future__ import annotations

from dataclasses import dataclass

from atabey.evaluation.official_division_metric import (
    OFFICIAL_MAX_DISTANCE_UM,
    _ground_truth_to_tracksdata,
    _official_modules,
    _prediction_to_tracksdata,
)
from atabey.io.geff_reader import SparseGroundTruthGraph
from atabey.types import LineageGraph


@dataclass(frozen=True)
class OfficialNodeCorrespondence:
    prediction_node_id: str
    ground_truth_node_id: int | None


@dataclass(frozen=True)
class OfficialEdgeCorrespondence:
    prediction_source_id: str
    prediction_target_id: str
    ground_truth_source_id: int | None
    ground_truth_target_id: int | None
    officially_matched: bool


@dataclass(frozen=True)
class OfficialAssociationCorrespondence:
    nodes: tuple[OfficialNodeCorrespondence, ...]
    edges: tuple[OfficialEdgeCorrespondence, ...]


def extract_official_association_correspondence(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    *,
    max_distance_um: float = OFFICIAL_MAX_DISTANCE_UM,
) -> OfficialAssociationCorrespondence:
    """Extract pinned-host matching details while preserving Atabey graphs."""

    pl, td, _ = _official_modules()
    try:
        from tracking_cellmot.metrics import _evaluate_matched_graph, evaluate
    except ImportError as exc:
        raise RuntimeError(
            "The official tracking metric is required for association forensics"
        ) from exc

    prediction, prediction_ids = _prediction_to_tracksdata(graph, pl, td)
    gt_graph, gt_ids = _ground_truth_to_tracksdata(ground_truth, pl, td)
    evaluate(prediction, gt_graph, scale=None, max_distance=float(max_distance_um))

    prediction_by_host_id = {value: key for key, value in prediction_ids.items()}
    gt_by_host_id = {value: key for key, value in gt_ids.items()}
    matched_key = td.DEFAULT_ATTR_KEYS.MATCHED_NODE_ID
    node_id_key = td.DEFAULT_ATTR_KEYS.NODE_ID
    node_rows = prediction.node_attrs(attr_keys=[node_id_key, matched_key]).to_dicts()
    matched_gt_by_prediction: dict[str, int | None] = {}
    for row in node_rows:
        prediction_id = prediction_by_host_id[int(row[node_id_key])]
        matched_host_id = row[matched_key]
        matched_gt_by_prediction[prediction_id] = (
            None
            if matched_host_id is None or int(matched_host_id) == -1
            else gt_by_host_id[int(matched_host_id)]
        )

    source_key = td.DEFAULT_ATTR_KEYS.EDGE_SOURCE
    target_key = td.DEFAULT_ATTR_KEYS.EDGE_TARGET
    mask_key = td.DEFAULT_ATTR_KEYS.MATCHED_EDGE_MASK
    edge_rows = _evaluate_matched_graph(prediction, gt_graph).select(
        source_key, target_key, mask_key
    ).to_dicts()
    edges: list[OfficialEdgeCorrespondence] = []
    for row in edge_rows:
        source_id = prediction_by_host_id[int(row[source_key])]
        target_id = prediction_by_host_id[int(row[target_key])]
        edges.append(
            OfficialEdgeCorrespondence(
                prediction_source_id=source_id,
                prediction_target_id=target_id,
                ground_truth_source_id=matched_gt_by_prediction[source_id],
                ground_truth_target_id=matched_gt_by_prediction[target_id],
                officially_matched=bool(row[mask_key]),
            )
        )

    return OfficialAssociationCorrespondence(
        nodes=tuple(
            OfficialNodeCorrespondence(prediction_id, gt_id)
            for prediction_id, gt_id in sorted(matched_gt_by_prediction.items())
        ),
        edges=tuple(
            sorted(
                edges,
                key=lambda edge: (edge.prediction_source_id, edge.prediction_target_id),
            )
        ),
    )